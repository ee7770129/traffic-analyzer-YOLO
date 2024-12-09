# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：cython_bbox（Windows 相容替代層）
功能說明：
    原始專案的 ByteTrack 追蹤器（byte_tracker/utils/matching.py）相依於
    C 擴充套件 `cython-bbox`，該套件在 Windows 上需要 Microsoft Visual C++
    Build Tools 才能編譯安裝，對一般使用者門檻過高。

    本模組以純 NumPy 向量化運算重新實作唯一被使用到的函式 `bbox_overlaps`，
    讓 `from cython_bbox import bbox_overlaps` 可在未安裝 C 編譯器的 Windows
    環境下正常運作，且不需要修改原始專案的任何既有程式碼。

    計算結果與原始 cython-bbox 完全一致（含 Faster R-CNN 慣用的 +1 像素修正），
    以確保追蹤行為不會因替換而改變。

使用方式：
    本檔案置於專案根目錄，Python 匯入時會優先於未安裝的同名套件被找到，
    原始程式無須任何調整。

建立日期：2024-12-09
版本號：v1.0.0
"""

import numpy as np

__all__ = ["bbox_overlaps"]


def bbox_overlaps(boxes: np.ndarray, query_boxes: np.ndarray) -> np.ndarray:
    """
    計算兩組邊界框之間的 IoU（Intersection over Union）重疊度矩陣。

    參數：
        boxes:       形狀 (N, 4) 的陣列，格式為 [x1, y1, x2, y2]
        query_boxes: 形狀 (K, 4) 的陣列，格式為 [x1, y1, x2, y2]

    回傳：
        形狀 (N, K) 的 float64 陣列，overlaps[n, k] 為第 n 個框
        與第 k 個框的 IoU 值。

    備註：
        寬高計算皆加 1，與原始 cython-bbox 的實作保持一致，
        避免替換後造成追蹤配對結果的細微差異。
    """
    boxes = np.ascontiguousarray(boxes, dtype=np.float64)
    query_boxes = np.ascontiguousarray(query_boxes, dtype=np.float64)

    n = boxes.shape[0]
    k = query_boxes.shape[0]

    # 任一組為空時直接回傳空矩陣，避免後續廣播運算出錯
    if n == 0 or k == 0:
        return np.zeros((n, k), dtype=np.float64)

    # 各自的面積（+1 為 Faster R-CNN 慣例，與原始實作一致）
    boxes_area = (boxes[:, 2] - boxes[:, 0] + 1.0) * (boxes[:, 3] - boxes[:, 1] + 1.0)
    query_area = (query_boxes[:, 2] - query_boxes[:, 0] + 1.0) * (
        query_boxes[:, 3] - query_boxes[:, 1] + 1.0
    )

    # 以廣播方式一次算出所有配對的交集寬高，(N, 1) 對 (1, K) → (N, K)
    inter_w = (
        np.minimum(boxes[:, None, 2], query_boxes[None, :, 2])
        - np.maximum(boxes[:, None, 0], query_boxes[None, :, 0])
        + 1.0
    )
    inter_h = (
        np.minimum(boxes[:, None, 3], query_boxes[None, :, 3])
        - np.maximum(boxes[:, None, 1], query_boxes[None, :, 1])
        + 1.0
    )

    # 沒有重疊時寬或高會是負值，需截斷為 0
    np.clip(inter_w, 0.0, None, out=inter_w)
    np.clip(inter_h, 0.0, None, out=inter_h)

    intersection = inter_w * inter_h

    # 聯集面積 = 兩框面積總和 - 交集面積
    union = boxes_area[:, None] + query_area[None, :] - intersection

    # 聯集理論上不會為 0（面積至少為 1），仍加上保護避免除零產生 NaN
    with np.errstate(divide="ignore", invalid="ignore"):
        overlaps = np.where(union > 0.0, intersection / union, 0.0)

    return overlaps.astype(np.float64, copy=False)
