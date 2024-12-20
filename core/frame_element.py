# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：單幀資料容器
功能說明：
    流水線上傳遞的核心物件。每個節點依序在同一個 FrameElement 上附加
    自己產出的資訊，讓後續節點取用，避免節點之間直接互相呼叫而產生耦合。

    資料累積順序：
        VideoReaderNode        -> frame / timestamp / frame_num / roads_info
        DetectionTrackingNode  -> detected_* / tracked_*
        TrackUpdateNode        -> active_tracks / retired_tracks
        CountingNode           -> count_events / statistics
        RenderNode             -> frame_result

建立日期：2024-12-18
版本號：v1.0.0
"""

from typing import Optional

import numpy as np


class FrameElement:
    """單一影格及其分析結果。"""

    def __init__(
        self,
        source: str,
        frame: np.ndarray,
        timestamp: float,
        frame_num: int,
        roads_info: dict,
        total_frames: int = 0,
    ) -> None:
        """
        參數：
            source:       影像來源描述（檔名、攝影機編號或串流網址）
            frame:        BGR 格式影格
            timestamp:    自影片起算的秒數
            frame_num:    影格序號（從 1 開始）
            roads_info:   道路區域座標字典
            total_frames: 影片總幀數，串流來源為 0（未知）
        """
        # ---- 來源資訊 ----
        self.source = source
        self.frame = frame
        self.timestamp = float(timestamp)
        self.frame_num = int(frame_num)
        self.total_frames = int(total_frames)
        self.roads_info = roads_info

        # ---- YOLO 偵測結果 ----
        self.detected_conf: list = []
        self.detected_cls: list = []   # 中文車種名稱
        self.detected_xyxy: list = []

        # ---- 追蹤結果（與 detected_* 不同，已通過 ByteTrack 過濾與補償）----
        self.tracked_ids: list = []
        self.tracked_conf: list = []
        self.tracked_cls: list = []    # 由偵測框比對還原的中文車種名稱
        self.tracked_xyxy: list = []

        # ---- 軌跡狀態 ----
        self.active_tracks: dict = {}   # {追蹤編號: TrackElement} 目前畫面上的車
        self.retired_tracks: list = []  # 本幀判定為已離場的 TrackElement

        # ---- 統計結果 ----
        self.count_events: list = []    # 本幀新產生的計數事件
        self.statistics: dict = {}      # 供繪圖與報表使用的彙總資訊

        # ---- 輸出 ----
        self.frame_result: Optional[np.ndarray] = None  # 疊加圖層後的成果影格
