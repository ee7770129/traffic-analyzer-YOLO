# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：軌跡熱力圖節點
功能說明：
    累積所有車輛在畫面上出現過的位置，分析結束時輸出一張熱力圖，
    疊加在路口畫面上，用來觀察車流動線集中在哪裡。

    每台車每幀在其代表點累加一次，因此顏色越亮代表「車輛停留的總幀數」越多：
    車多的動線會亮，停等的位置也會亮。解讀時須留意這兩者會混在一起。

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging
import os
from typing import Optional

import cv2
import numpy as np

from core.stream_end_element import StreamEndElement
from utils.line_geometry import ANCHOR_BOTTOM_CENTER, anchor_point
from utils.profiler import profile_time

logger = logging.getLogger(__name__)


class HeatmapNode:
    """車輛位置累積與熱力圖輸出。"""

    def __init__(self, config: dict, run_dir: str) -> None:
        """
        參數：
            config:  設定檔 heatmap_node 區段。
            run_dir: 本次執行的輸出資料夾。
        """
        self.run_dir = run_dir
        self.anchor_mode = str(config.get("anchor", ANCHOR_BOTTOM_CENTER))
        self.blur_sigma = float(config["blur_sigma"])
        self.alpha = float(config["alpha"])
        self.clip_percentile = float(config.get("clip_percentile", 99.0))
        self.output_name = str(config["output_name"])

        self._accumulator: Optional[np.ndarray] = None
        self._background: Optional[np.ndarray] = None
        self.output_path = os.path.join(self.run_dir, self.output_name)

    @profile_time
    def process(self, element):
        """累積本幀車輛位置；收到結束訊號時輸出熱力圖。"""
        if isinstance(element, StreamEndElement):
            self.write_heatmap()
            return element

        if self._accumulator is None:
            height, width = element.frame.shape[:2]
            self._accumulator = np.zeros((height, width), dtype=np.float32)

        # 保留最新一幀當底圖；只存參照不複製，避免每幀額外的記憶體配置
        self._background = element.frame

        height, width = self._accumulator.shape
        for track in element.active_tracks.values():
            if track.last_xyxy is None:
                continue
            x, y = anchor_point(track.last_xyxy, self.anchor_mode)
            col, row = int(round(x)), int(round(y))
            if 0 <= row < height and 0 <= col < width:
                self._accumulator[row, col] += 1.0

        return element

    def render(self) -> Optional[np.ndarray]:
        """把累積結果轉成疊加在底圖上的彩色熱力圖；沒有資料時回傳 None。"""
        if self._accumulator is None or self._background is None:
            return None
        if float(self._accumulator.max()) <= 0:
            return None

        # 單點累積太稀疏，先以高斯模糊擴散成連續的熱區
        blurred = cv2.GaussianBlur(self._accumulator, (0, 0), self.blur_sigma)

        # 一台長時間停等的車會讓單點數值遠高於其他位置，若以最大值正規化，
        # 整張圖只會剩那一個亮點；改以百分位數為上限，讓行駛動線也看得見
        positive = blurred[blurred > 0]
        ceiling = float(np.percentile(positive, self.clip_percentile))
        normalized = np.clip(blurred / max(ceiling, 1e-9), 0.0, 1.0)
        colored = cv2.applyColorMap((normalized * 255).astype(np.uint8), cv2.COLORMAP_JET)

        # 沒有車經過的地方保持底圖原貌，只在有熱度處疊色
        weight = (np.clip(normalized * 4.0, 0.0, 1.0) * self.alpha)[..., None]
        blended = self._background.astype(np.float32) * (1.0 - weight) + colored.astype(np.float32) * weight
        return blended.astype(np.uint8)

    def write_heatmap(self) -> None:
        """輸出熱力圖檔案。"""
        image = self.render()
        if image is None:
            logger.warning("沒有任何車輛位置資料，略過熱力圖輸出。")
            return

        os.makedirs(self.run_dir, exist_ok=True)
        extension = os.path.splitext(self.output_name)[1] or ".png"

        # cv2.imwrite 在 Windows 無法寫入含中文的路徑，改以編碼後自行寫檔
        ok, buffer = cv2.imencode(extension, image)
        if not ok:
            raise RuntimeError(f"HeatmapNode｜熱力圖編碼失敗：{self.output_path}")
        buffer.tofile(self.output_path)
        logger.info("軌跡熱力圖已儲存：%s", os.path.abspath(self.output_path))
