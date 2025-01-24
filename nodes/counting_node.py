# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：車流計數節點
功能說明：
    本專案相對原始專案最重要的新增功能，提供可重現、可驗證的車流數據：

        1. 精確累計計數：每台車只計一次，得到「第 N 條路共進入 X 輛」的絕對值。
        2. 車種分類統計：依中文車種分別累計，並換算小客車當量（PCU）。
        3. 轉向 OD 矩陣：統計「由第 i 條路進入、由第 j 條路離開」的車輛數。
        4. 即時流率：以實際計數事件在滑動視窗內的數量換算輛/分鐘。

    與原始專案的差異：
        原專案的流率為「緩衝區內存活軌跡數 ÷ 緩衝分鐘數」，是瞬時估計值，
        會隨視窗內容跳動且無法累加，不適合作為正式統計數據。
        本節點改為事件驅動的絕對計數，統計結果可重現、可與人工計數逐筆核對。

計數門檻：
    軌跡必須同時滿足「存活時間 >= min_track_life_secs」與
    「成功辨識幀數 >= min_vote_count」才會被計入，
    用以濾除誤偵測與一閃即逝的破碎軌跡。

建立日期：2025-01-24
版本號：v1.0.0
"""

import itertools
import logging
from collections import Counter, defaultdict, deque

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from utils.profiler import profile_time
from utils.vehicle_types import VehicleTypeRegistry

logger = logging.getLogger(__name__)


class CountingNode:
    """車流累計計數與轉向統計。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 完整設定檔，使用 general 與 vehicle_types 區段。
        """
        general_cfg = config["general"]

        self.min_track_life_secs = float(general_cfg["min_track_life_secs"])
        self.min_vote_count = int(general_cfg["min_vote_count"])
        self.flow_window_secs = float(general_cfg["flow_window_secs"])

        self.vehicle_types = VehicleTypeRegistry(config["vehicle_types"])

        # ---- 累計統計 ----
        self.entry_counts: dict = defaultdict(Counter)  # {道路: Counter(車種)}
        self.od_matrix: dict = defaultdict(int)         # {(進入道路, 離開道路): 車輛數}
        self.total_vehicles = 0
        self.total_pcu = 0.0

        # ---- 即時流率用的事件時間佇列 ----
        self._entry_events: deque = deque()  # [(時間, 道路), ...]

        self.road_ids: list = []  # 首幀由區域設定推導，確保報表欄位順序固定

    @profile_time
    def process(self, element):
        """結算本幀可計數的軌跡，產生計數事件並更新統計。"""
        is_stream_end = isinstance(element, StreamEndElement)
        if not is_stream_end:
            assert isinstance(element, FrameElement), (
                f"CountingNode｜輸入型別錯誤：{type(element)}"
            )
            if not self.road_ids:
                self.road_ids = sorted(int(k) for k in element.roads_info)

        events = []
        timestamp = element.timestamp

        # 作用中與已離場的軌跡都要檢查：
        # 作用中的車可能已滿足計數門檻，已離場的車則是最後結算機會
        candidates = itertools.chain(element.active_tracks.values(), element.retired_tracks)

        for track in candidates:
            events.extend(self._count_entry(track, timestamp))
            events.extend(self._count_movement(track, timestamp))

        self._trim_flow_window(timestamp)

        element.count_events = events
        element.statistics = self._build_statistics(element)

        return element

    # ------------------------------------------------------------------
    # 計數邏輯
    # ------------------------------------------------------------------
    def _count_entry(self, track, timestamp: float) -> list:
        """若軌跡符合門檻且尚未計數，計入進入流量並回傳事件。"""
        if track.counted_entry:
            return []
        if track.entry_road is None:
            return []
        if track.lifetime < self.min_track_life_secs:
            return []
        if track.vote_count < self.min_vote_count:
            return []

        track.counted_entry = True

        vehicle_type = track.vehicle_type or self.vehicle_types.unknown_label
        pcu = self.vehicle_types.pcu_of(vehicle_type)

        self.entry_counts[track.entry_road][vehicle_type] += 1
        self.total_vehicles += 1
        self.total_pcu += pcu
        self._entry_events.append((timestamp, track.entry_road))

        return [
            {
                "事件": "進入",
                "時間": timestamp,
                "追蹤編號": track.track_id,
                "道路": track.entry_road,
                "車種": vehicle_type,
                "PCU": pcu,
            }
        ]

    def _count_movement(self, track, timestamp: float) -> list:
        """若軌跡已取得完整進出道路且尚未計入 OD，計入轉向矩陣並回傳事件。"""
        if track.counted_movement:
            return []
        if not track.has_movement:
            return []
        # 僅結算已計入進入流量的車輛，確保兩份統計的母體一致
        if not track.counted_entry:
            return []

        track.counted_movement = True

        vehicle_type = track.vehicle_type or self.vehicle_types.unknown_label
        self.od_matrix[(track.entry_road, track.exit_road)] += 1

        return [
            {
                "事件": "轉向",
                "時間": timestamp,
                "追蹤編號": track.track_id,
                "進入道路": track.entry_road,
                "離開道路": track.exit_road,
                "車種": vehicle_type,
            }
        ]

    # ------------------------------------------------------------------
    # 統計輸出
    # ------------------------------------------------------------------
    def _trim_flow_window(self, timestamp: float) -> None:
        """移除滑動視窗外的舊事件，使即時流率只反映近期車流。"""
        cutoff = timestamp - self.flow_window_secs
        while self._entry_events and self._entry_events[0][0] < cutoff:
            self._entry_events.popleft()

    def _current_flow_rates(self) -> dict:
        """
        計算各道路的即時流率（輛/分鐘）。

        與原專案的估計值不同，此處分子為視窗內「實際發生的計數事件數」，
        因此數值可直接對應到報表中的累計車次。
        """
        if self.flow_window_secs <= 0:
            return {road: 0.0 for road in self.road_ids}

        window_minutes = self.flow_window_secs / 60.0
        window_counts = Counter(road for _, road in self._entry_events)

        return {
            road: window_counts.get(road, 0) / window_minutes for road in self.road_ids
        }

    def _build_statistics(self, element) -> dict:
        """彙整供繪圖與報表使用的統計資訊。"""
        road_totals = {road: sum(self.entry_counts[road].values()) for road in self.road_ids}

        type_totals = Counter()
        for counter in self.entry_counts.values():
            type_totals.update(counter)

        return {
            "累計車次": self.total_vehicles,
            "累計PCU": round(self.total_pcu, 1),
            "各道路累計": road_totals,
            "各道路流率": self._current_flow_rates(),
            "車種組成": dict(type_totals),
            "轉向筆數": sum(self.od_matrix.values()),
            "畫面車輛數": len(element.active_tracks),
            "流率視窗秒": self.flow_window_secs,
        }
