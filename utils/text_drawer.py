# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：中文文字繪製工具
功能說明：
    OpenCV 的 cv2.putText() 僅支援 ASCII，無法顯示中日韓文字。
    本模組以 Pillow 在 BGR 影像上繪製繁體中文，讓畫面 UI 能符合中文化要求。

    為兼顧效能，採「整張影像單次轉換」策略：
    呼叫端先用 cv2 完成所有圖形繪製，最後一次性把所有文字交給本模組，
    避免每段文字都做一次 BGR 與 PIL 之間的格式轉換。

建立日期：2025-02-14
版本號：v1.0.0
"""

import logging
import os
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class TextDrawer:
    """以 Pillow 在 OpenCV 影像上繪製中文字。"""

    def __init__(self, font_candidates: list, sizes: dict) -> None:
        """
        參數：
            font_candidates: 字型檔候選路徑串列，依序嘗試，第一個存在者勝出。
            sizes:           字級設定，如 {"small": 16, "normal": 20, "large": 26}。
        """
        self.font_path = self._resolve_font(font_candidates)
        self._fonts: dict = {}

        for name, size in sizes.items():
            self._fonts[name] = self._load_font(int(size))

        # 沒有任何字級設定時給一個保底值，避免呼叫端取不到字型
        if not self._fonts:
            self._fonts["normal"] = self._load_font(20)

    @staticmethod
    def _resolve_font(font_candidates: list) -> Optional[str]:
        """從候選清單中找出第一個實際存在的字型檔。"""
        for path in font_candidates or []:
            if path and os.path.isfile(str(path)):
                return str(path)

        logger.warning(
            "找不到可用的中文字型，畫面文字將以 Pillow 預設字型顯示（中文可能變成方框）。"
            "請於設定檔 render_node.font_candidates 指定有效的字型檔路徑。"
        )
        return None

    def _load_font(self, size: int):
        """載入指定字級的字型物件；無可用字型時回傳 Pillow 預設字型。"""
        if self.font_path is None:
            return ImageFont.load_default()
        try:
            return ImageFont.truetype(self.font_path, size)
        except OSError:
            logger.warning("字型載入失敗：%s（字級 %d），改用預設字型", self.font_path, size)
            return ImageFont.load_default()

    def font(self, name: str = "normal"):
        """取得指定名稱的字型物件，找不到時回退到 normal。"""
        return self._fonts.get(name) or self._fonts.get("normal")

    def draw(self, image_bgr: np.ndarray, items: list) -> np.ndarray:
        """
        在 BGR 影像上一次繪製多段文字。

        參數：
            image_bgr: OpenCV 的 BGR 影像
            items:     文字項目串列，每項為 dict：
                       {
                           "text":   文字內容,
                           "xy":     (x, y) 左上角座標,
                           "color":  (B, G, R) 文字顏色,
                           "size":   字級名稱（預設 "normal"）,
                           "bg":     (B, G, R) 背景底色，None 表示不畫底色,
                           "padding": 底色內距（預設 2）,
                       }

        回傳：
            繪製後的 BGR 影像（新陣列，不修改輸入）。
        """
        if not items:
            return image_bgr

        # OpenCV 為 BGR、Pillow 為 RGB，轉換一次即可處理所有文字。
        # 使用 cv2.cvtColor 而非 numpy 的 [:, :, ::-1] 切片：
        # 後者產生負步長檢視，Pillow 需額外複製一次，實測明顯較慢。
        pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        for item in items:
            text = str(item.get("text", ""))
            if not text:
                continue

            font = self.font(item.get("size", "normal"))
            x, y = item.get("xy", (0, 0))
            color_bgr = item.get("color", (255, 255, 255))
            color_rgb = (int(color_bgr[2]), int(color_bgr[1]), int(color_bgr[0]))

            background = item.get("bg")
            if background is not None:
                padding = int(item.get("padding", 2))
                left, top, right, bottom = draw.textbbox((x, y), text, font=font)
                bg_rgb = (int(background[2]), int(background[1]), int(background[0]))
                draw.rectangle(
                    [left - padding, top - padding, right + padding, bottom + padding],
                    fill=bg_rgb,
                )

            draw.text((x, y), text, font=font, fill=color_rgb)

        return cv2.cvtColor(np.asarray(pil_image), cv2.COLOR_RGB2BGR)

    def text_size(self, text: str, size: str = "normal") -> tuple:
        """量測文字的像素寬高，供版面計算使用。"""
        font = self.font(size)
        left, top, right, bottom = font.getbbox(str(text))
        return (right - left, bottom - top)
