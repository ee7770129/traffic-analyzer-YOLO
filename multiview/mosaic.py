# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：多格畫面排版
功能說明：
    把多個路口的成果影格排成格狀畫面。
    各路口攝影機的解析度與長寬比都不同，因此每格以「等比例縮放＋留黑邊」
    的方式放入固定大小的格子，畫面不會被拉伸變形。

    本模組只做排版，不含任何分析邏輯，也不持有狀態。

建立日期：2026-10-08
版本號：v1.2.0
"""

import math
from typing import Optional

import cv2
import numpy as np

_BACKGROUND = (24, 24, 24)   # 黑邊與空格的底色（BGR）


def letterbox(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """把影格等比例縮放後置中放入指定大小的畫布，不足處留底色。"""
    canvas = np.full((height, width, 3), _BACKGROUND, dtype=np.uint8)
    source_height, source_width = frame.shape[:2]
    if source_height == 0 or source_width == 0:
        return canvas

    scale = min(width / source_width, height / source_height)
    new_width = max(int(round(source_width * scale)), 1)
    new_height = max(int(round(source_height * scale)), 1)
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    left = (width - new_width) // 2
    top = (height - new_height) // 2
    canvas[top:top + new_height, left:left + new_width] = resized
    return canvas


def build_cell(frame: Optional[np.ndarray], width: int, height: int, caption_height: int) -> np.ndarray:
    """
    組出一格畫面：上方保留標題列的空間，下方放縮放後的影格。

    frame 為 None（尚未取得影像）時，影像區維持底色。
    """
    cell = np.full((caption_height + height, width, 3), _BACKGROUND, dtype=np.uint8)
    if frame is not None:
        cell[caption_height:] = letterbox(frame, width, height)
    return cell


def compose_grid(cells: list, columns: int) -> np.ndarray:
    """
    把大小相同的格子由左至右、由上至下排成格狀畫面。
    格子數不足以填滿最後一列時，以底色補齊。
    """
    if not cells:
        raise ValueError("mosaic｜至少需要一格畫面")

    columns = max(int(columns), 1)
    rows = math.ceil(len(cells) / columns)
    blank = np.full_like(cells[0], _BACKGROUND)

    padded = list(cells) + [blank] * (rows * columns - len(cells))
    return np.vstack([
        np.hstack(padded[row * columns:(row + 1) * columns]) for row in range(rows)
    ])


def cell_origin(index: int, columns: int, width: int, cell_total_height: int) -> tuple:
    """回傳第 index 格左上角在整張多格畫面中的座標。"""
    columns = max(int(columns), 1)
    return ((index % columns) * width, (index // columns) * cell_total_height)


def format_caption(name: str, status: str, statistics: dict) -> str:
    """組出一格的標題文字：路口名稱、狀態、累計車次與越線進出量。"""
    total = statistics.get("累計車次", 0)
    line_stats = statistics.get("越線計數") or {}
    entered = sum(info.get("進入", 0) for info in line_stats.values())
    left = sum(info.get("離開", 0) for info in line_stats.values())
    return f"{name}　{status}　累計 {total} 輛　越線 進 {entered} 出 {left}"
