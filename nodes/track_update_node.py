# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：軌跡狀態維護節點
功能說明：
    維護所有車輛軌跡的生命週期，是計數統計的前置作業：
        1. 為每個追蹤編號建立／更新對應的 TrackElement。
        2. 判定車輛中心點所在區域，推導進入道路與離開道路。
        3. 累積車種投票。
        4. 將超過逾時秒數未再出現的軌跡標記為「已離場」，交由計數節點結算。

    與原始專案的差異：原專案僅依「緩衝區時間」粗略刪除舊軌跡，
    本節點改以「最後出現時間」判定離場，並把離場軌跡完整交給下游，
    確保每一台車都會被結算且只結算一次。

建立日期：2025-01-15
版本號：v1.0.0
"""

import logging

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from utils.geometry import build_polygons, locate_zone
from utils.profiler import profile_time

logger = logging.getLogger(__name__)


class TrackUpdateNode:
    """車輛軌跡生命週期管理。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 完整設定檔，使用 general 區段的 track_timeout_secs。
        """
        general_cfg = config["general"]

        # 超過此秒數未再被偵測到，即視為車輛已離開畫面
        self.track_timeout_secs = float(general_cfg["track_timeout_secs"])

        self._tracks: dict = {}       # {追蹤編號: TrackElement} 全部尚未離場的軌跡
        self._polygons: dict = {}     # 道路區域多邊形，首幀建立後重複使用

    @profile_time
    def process(self, element):
        """更新軌跡狀態，並把作用中與已離場的軌跡寫入元素。"""
        if isinstance(element, StreamEndElement):
            # 影片結束：把所有殘留軌跡一次性交給下游結算，避免尾端車輛漏計
            element.retired_tracks = list(self._tracks.values())
            logger.info("影片結束，清空殘留軌跡 %d 筆", len(element.retired_tracks))
            self._tracks = {}
            return element

        assert isinstance(element, FrameElement), (
            f"TrackUpdateNode｜輸入型別錯誤：{type(element)}"
        )

        # 多邊形只需建立一次，避免每幀重複解析座標
        if not self._polygons:
            self._polygons = build_polygons(element.roads_info)
            logger.info("已載入道路區域 %d 個：%s", len(self._polygons), sorted(self._polygons))

        timestamp = element.timestamp
        active_tracks = {}

        for index, track_id in enumerate(element.tracked_ids):
            xyxy = element.tracked_xyxy[index]
            label = element.tracked_cls[index] if index < len(element.tracked_cls) else None

            track = self._tracks.get(track_id)
            if track is None:
                track = TrackElement(track_id, timestamp)
                self._tracks[track_id] = track

            track.update(timestamp, xyxy)
            track.vote_vehicle_type(label)
            track.observe_zone(locate_zone(xyxy, self._polygons), timestamp)

            active_tracks[track_id] = track

        element.active_tracks = active_tracks
        element.retired_tracks = self._retire_stale_tracks(timestamp)

        return element

    def _retire_stale_tracks(self, timestamp: float) -> list:
        """
        將超過逾時秒數未出現的軌跡移出管理清單並回傳。

        參數：
            timestamp: 目前影格時間（秒）

        回傳：
            本幀判定為已離場的 TrackElement 串列。
        """
        stale_ids = [
            track_id
            for track_id, track in self._tracks.items()
            if timestamp - track.timestamp_last > self.track_timeout_secs
        ]

        retired = []
        for track_id in stale_ids:
            retired.append(self._tracks.pop(track_id))

        if retired:
            logger.debug("軌跡離場 %d 筆：%s", len(retired), [t.track_id for t in retired])

        return retired
