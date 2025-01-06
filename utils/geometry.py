# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：幾何運算工具
功能說明：
    1. 將設定檔中的區域座標（扁平陣列）轉換為 Shapely 多邊形。
    2. 判定車輛邊界框中心點落在哪一個區域（進出道路判定的基礎）。
    3. 計算兩組邊界框的 IoU 矩陣，供「追蹤結果還原車種」使用。

建立日期：2025-01-06
版本號：v1.0.0
"""

from typing import Optional

import numpy as np
from shapely.geometry import Point, Polygon


def build_polygons(roads_info: dict) -> dict:
    """
    將設定檔的扁平座標陣列轉為 Shapely 多邊形物件，啟動時只做一次，
    避免每幀重複建立造成效能浪費。

    參數：
        roads_info: {"1": [x1, y1, x2, y2, ...], ...}

    回傳：
        {1: Polygon, 2: Polygon, ...}，鍵值轉為 int 方便後續統計。
    """
    polygons = {}
    for key, flat_coords in roads_info.items():
        points = [
            (float(flat_coords[i]), float(flat_coords[i + 1]))
            for i in range(0, len(flat_coords) - 1, 2)
        ]
        # 少於三個點無法構成多邊形，直接略過並避免後續運算出錯
        if len(points) < 3:
            continue
        polygons[int(key)] = Polygon(points)
    return polygons


def bbox_center(xyxy) -> tuple:
    """回傳邊界框 [x1, y1, x2, y2] 的中心點座標 (x, y)。"""
    return ((xyxy[0] + xyxy[2]) / 2.0, (xyxy[1] + xyxy[3]) / 2.0)


def locate_zone(xyxy, polygons: dict) -> Optional[int]:
    """
    判定邊界框中心點位於哪一個區域。

    參數：
        xyxy:     邊界框座標 [x1, y1, x2, y2]
        polygons: build_polygons() 產生的多邊形字典

    回傳：
        區域編號（int）；不在任何區域內則回傳 None。
    """
    point = Point(bbox_center(xyxy))
    for zone_id, polygon in polygons.items():
        if polygon.contains(point):
            return zone_id
    return None


def iou_matrix(boxes_a, boxes_b) -> np.ndarray:
    """
    計算兩組邊界框之間的 IoU 矩陣，用於把追蹤框對回原始偵測框，
    以還原被追蹤器抹除的車種資訊。

    參數：
        boxes_a: 形狀 (N, 4) 的座標串列或陣列
        boxes_b: 形狀 (M, 4) 的座標串列或陣列

    回傳：
        形狀 (N, M) 的 float 陣列，元素為對應兩框的 IoU。
    """
    a = np.asarray(boxes_a, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(boxes_b, dtype=np.float64).reshape(-1, 4)

    if a.shape[0] == 0 or b.shape[0] == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float64)

    area_a = np.clip(a[:, 2] - a[:, 0], 0, None) * np.clip(a[:, 3] - a[:, 1], 0, None)
    area_b = np.clip(b[:, 2] - b[:, 0], 0, None) * np.clip(b[:, 3] - b[:, 1], 0, None)

    # 以廣播一次算出所有配對的交集區域
    inter_w = np.clip(
        np.minimum(a[:, None, 2], b[None, :, 2]) - np.maximum(a[:, None, 0], b[None, :, 0]),
        0,
        None,
    )
    inter_h = np.clip(
        np.minimum(a[:, None, 3], b[None, :, 3]) - np.maximum(a[:, None, 1], b[None, :, 1]),
        0,
        None,
    )
    intersection = inter_w * inter_h
    union = area_a[:, None] + area_b[None, :] - intersection

    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(union > 0, intersection / union, 0.0)
