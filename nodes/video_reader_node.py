# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：影像讀取節點
功能說明：
    流水線的第一個節點。負責開啟影像來源（影片檔、攝影機或 RTSP／m3u8 串流），
    逐幀產生 FrameElement，並在來源結束時送出 StreamEndElement 作為收尾訊號。

    同時負責載入道路區域座標設定檔，讓後續節點不必再處理檔案 I/O。

建立日期：2024-12-20
版本號：v1.0.0
"""

import json
import logging
import os
import time
from typing import Generator, Union

import cv2

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement

logger = logging.getLogger(__name__)


class VideoReaderNode:
    """影像來源讀取節點。"""

    def __init__(self, config: dict) -> None:
        """
        參數：
            config: 設定檔 video_reader 區段，包含
                    src（來源）、skip_secs（抽幀間隔）、roads_info（區域座標檔）。
        """
        self.source_path: Union[str, int] = config["src"]
        self.source_name = str(self.source_path)

        # 來源型態判定：整數為攝影機編號，含 :// 為網路串流，其餘視為本機檔案
        self.is_camera = isinstance(self.source_path, int)
        self.is_stream = isinstance(self.source_path, str) and "://" in self.source_path
        self.is_realtime = self.is_camera or self.is_stream

        if not self.is_realtime:
            if not os.path.isfile(self.source_path):
                raise FileNotFoundError(
                    f"VideoReaderNode｜找不到影片檔案：{self.source_path}"
                )

        self.stream = cv2.VideoCapture(self.source_path)
        if not self.stream.isOpened():
            raise RuntimeError(f"VideoReaderNode｜無法開啟影像來源：{self.source_path}")

        # 攝影機來源需主動指定解析度，否則可能取得過低的預設值
        if self.is_camera:
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, int(config.get("camera_width", 1920)))
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, int(config.get("camera_height", 1080)))

        self.skip_secs = float(config.get("skip_secs", 0))

        # 影片總幀數用於顯示處理進度；串流來源取不到時為 0
        self.total_frames = int(self.stream.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.source_fps = float(self.stream.get(cv2.CAP_PROP_FPS) or 0.0)

        # 載入道路區域座標
        roads_info_path = config["roads_info"]
        if not os.path.isfile(roads_info_path):
            raise FileNotFoundError(
                f"VideoReaderNode｜找不到道路區域設定檔：{roads_info_path}"
            )
        with open(roads_info_path, "r", encoding="utf-8") as file:
            raw_roads = json.load(file)
        self.roads_info = {
            str(key): [float(v) for v in values] for key, values in raw_roads.items()
        }

        self._last_timestamp = -1.0
        self._stream_start_time = 0.0

        logger.info(
            "影像來源已開啟：%s（總幀數 %d、來源 FPS %.2f、道路區域 %d 個）",
            self.source_name,
            self.total_frames,
            self.source_fps,
            len(self.roads_info),
        )

    def process(self) -> Generator[Union[FrameElement, StreamEndElement], None, None]:
        """逐幀產生 FrameElement，來源結束時產生一個 StreamEndElement 後停止。"""
        frame_number = 0

        while True:
            ok, frame = self.stream.read()

            if not ok:
                logger.info("影像來源已讀取完畢，共處理 %d 幀", frame_number)
                yield StreamEndElement(self.source_name, self._last_timestamp, frame_number)
                break

            timestamp = self._current_timestamp(frame_number)

            # 依設定抽幀：兩幀時間差不足 skip_secs 時直接跳過，不進入後續運算
            if self.skip_secs > 0 and abs(timestamp - self._last_timestamp) < self.skip_secs:
                continue

            self._last_timestamp = timestamp
            frame_number += 1

            yield FrameElement(
                source=self.source_name,
                frame=frame,
                timestamp=timestamp,
                frame_num=frame_number,
                roads_info=self.roads_info,
                total_frames=self.total_frames,
            )

        self.release()

    def _current_timestamp(self, frame_number: int) -> float:
        """
        取得本幀的時間戳（自來源起算的秒數）。

        即時來源以系統時間計算；影片檔以 cv2 的 POS_MSEC 為準，
        並處理 cv2 在影片尾端可能回傳 0 的已知問題。
        """
        if self.is_realtime:
            if frame_number == 0:
                self._stream_start_time = time.time()
            return time.time() - self._stream_start_time

        timestamp = self.stream.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        # 部分編碼格式的首幀會回傳負的 POS_MSEC，直接夾為 0 避免報表出現負時間
        timestamp = max(timestamp, 0.0)

        # cv2 在部分影片尾端會回傳 0，導致時間倒退，此處以遞增值補償
        if frame_number > 0 and timestamp <= self._last_timestamp:
            fallback_step = 1.0 / self.source_fps if self.source_fps > 0 else 0.04
            timestamp = self._last_timestamp + fallback_step

        return timestamp

    @property
    def last_timestamp(self) -> float:
        """最後一幀的時間（秒）；尚未讀取任何影格時為 0。"""
        return max(self._last_timestamp, 0.0)

    def release(self) -> None:
        """釋放影像來源資源。"""
        if self.stream is not None and self.stream.isOpened():
            self.stream.release()
