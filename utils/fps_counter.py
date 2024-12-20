# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：FPS 計數器
功能說明：
    以滑動視窗方式計算近 N 幀的平均處理速度，用於畫面上的效能顯示。
    視窗尚未填滿前回傳 0.0，避免初期數值劇烈跳動。

建立日期：2024-12-18
版本號：v1.0.0
"""

import time
from collections import deque


class FPSCounter:
    """滑動視窗 FPS 計算器。"""

    def __init__(self, window_frames: int = 15) -> None:
        """
        參數：
            window_frames: 用於平均的幀數視窗大小，越大數值越平滑。
        """
        # 至少保留 2 個時間點才能算出間隔
        self.window_frames = max(2, int(window_frames))
        self._timestamps: deque[float] = deque(maxlen=self.window_frames)

    def update(self) -> float:
        """記錄本幀時間並回傳目前的平均 FPS；視窗未滿時回傳 0.0。"""
        self._timestamps.append(time.perf_counter())

        if len(self._timestamps) < self.window_frames:
            return 0.0

        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return 0.0

        # 視窗內有 N 個時間點，代表經過 N-1 個間隔
        return (len(self._timestamps) - 1) / elapsed
