# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：cython_bbox.py 的單元測試
功能說明：
    本模組是取代 C 擴充套件 cython-bbox 的純 NumPy 相容層，
    直接餵給 ByteTrack 使用。計算結果只要與原始實作有任何差異，
    追蹤配對行為就會改變，因此需逐一驗證數值。

    原始 cython-bbox 的寬高計算皆加 1（Faster R-CNN 慣例），
    這些測試以手算值確認該慣例有被正確保留。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np
import pytest

from cython_bbox import bbox_overlaps


class TestBboxOverlaps:
    """IoU 計算正確性。"""

    def test_完全重疊為一(self):
        box = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert bbox_overlaps(box, box)[0, 0] == pytest.approx(1.0)

    def test_完全沒有交集為零(self):
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[20.0, 20.0, 30.0, 30.0]])
        assert bbox_overlaps(a, b)[0, 0] == pytest.approx(0.0)

    def test_部分重疊符合加一慣例(self):
        """
        兩個 10x10 的框錯開 5 像素，依原始實作的 +1 慣例：
            交集 = (10-5+1)^2 = 36
            各框面積 = 11^2 = 121
            聯集 = 121 + 121 - 36 = 206
        """
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[5.0, 5.0, 15.0, 15.0]])
        assert bbox_overlaps(a, b)[0, 0] == pytest.approx(36.0 / 206.0)

    def test_相鄰但未重疊時仍有一像素交集(self):
        """
        +1 慣例下，x2=10 與 x1=10 視為共用一個像素，
        交集為 1x1。這是原始實作的行為，必須保留。
        """
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[10.0, 10.0, 20.0, 20.0]])
        assert bbox_overlaps(a, b)[0, 0] > 0.0

    def test_矩陣形狀為_N乘M(self):
        a = np.zeros((3, 4))
        b = np.zeros((5, 4))
        assert bbox_overlaps(a, b).shape == (3, 5)

    def test_空輸入回傳對應形狀的空矩陣(self):
        a = np.zeros((0, 4))
        b = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert bbox_overlaps(a, b).shape == (0, 1)
        assert bbox_overlaps(b, a).shape == (1, 0)

    def test_回傳型別為_float64(self):
        """ByteTrack 內部以 float64 運算，型別不符會造成精度問題。"""
        box = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert bbox_overlaps(box, box).dtype == np.float64

    def test_接受_python_串列輸入(self):
        assert bbox_overlaps([[0, 0, 10, 10]], [[0, 0, 10, 10]])[0, 0] == pytest.approx(1.0)

    def test_結果永遠落在零到一之間(self):
        rng = np.random.default_rng(42)
        a = rng.uniform(0, 100, size=(20, 2))
        b = rng.uniform(0, 100, size=(20, 2))
        boxes = np.hstack([np.minimum(a, b), np.maximum(a, b) + 1])
        result = bbox_overlaps(boxes, boxes)
        assert result.min() >= 0.0
        assert result.max() <= 1.0 + 1e-9

    def test_對稱性(self):
        """IoU(a,b) 必須等於 IoU(b,a)。"""
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        b = np.array([[3.0, 4.0, 12.0, 18.0]])
        assert bbox_overlaps(a, b)[0, 0] == pytest.approx(bbox_overlaps(b, a)[0, 0])

    def test_不產生_NaN(self):
        degenerate = np.array([[5.0, 5.0, 5.0, 5.0]])
        normal = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert not np.isnan(bbox_overlaps(degenerate, normal)).any()
