# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：utils/geometry.py 的單元測試
功能說明：
    驗證多邊形建立、區域內含判定與 IoU 矩陣計算。
    區域判定是進出道路推導的基礎，計算錯誤會讓所有統計失真，
    因此邊界情況（恰在邊線上、空輸入、退化多邊形）都要覆蓋。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np
import pytest

from utils.geometry import bbox_center, build_polygons, iou_matrix, locate_zone


class TestBuildPolygons:
    """多邊形建立。"""

    def test_鍵值轉為整數且數量正確(self, square_roads):
        polygons = build_polygons(square_roads)
        assert set(polygons.keys()) == {1, 2, 3}
        assert all(isinstance(k, int) for k in polygons)

    def test_多邊形面積正確(self, square_roads):
        polygons = build_polygons(square_roads)
        # 100 x 100 的方形，面積應為 10000
        assert polygons[1].area == pytest.approx(10000.0)

    def test_略過點數不足的退化多邊形(self):
        # 只有兩個點無法構成多邊形，應被略過而非拋出例外
        polygons = build_polygons({"1": [0, 0, 10, 10]})
        assert polygons == {}

    def test_空輸入回傳空字典(self):
        assert build_polygons({}) == {}


class TestBboxCenter:
    """邊界框中心點。"""

    def test_中心點計算(self):
        assert bbox_center([0, 0, 10, 20]) == (5.0, 10.0)

    def test_負座標也能處理(self):
        assert bbox_center([-10, -20, 10, 20]) == (0.0, 0.0)


class TestLocateZone:
    """區域判定。"""

    def test_中心點落在區域內(self, square_roads):
        polygons = build_polygons(square_roads)
        # 中心點 (50, 50) 落在區域 1
        assert locate_zone([40, 40, 60, 60], polygons) == 1

    def test_中心點落在另一個區域(self, square_roads):
        polygons = build_polygons(square_roads)
        # 中心點 (250, 50) 落在區域 2
        assert locate_zone([240, 40, 260, 60], polygons) == 2

    def test_不在任何區域內回傳_None(self, square_roads):
        polygons = build_polygons(square_roads)
        # 中心點 (500, 500) 不在任何區域
        assert locate_zone([490, 490, 510, 510], polygons) is None

    def test_判定依據是中心點而非邊界框重疊(self, square_roads):
        """
        邊界框雖與區域 1 重疊，但中心點 (150, 50) 在區域外，
        應判定為不在任何區域。這是刻意的設計：以中心點為準較不易誤判。
        """
        polygons = build_polygons(square_roads)
        assert locate_zone([50, 40, 250, 60], polygons) is None

    def test_沒有任何區域時回傳_None(self):
        assert locate_zone([10, 10, 20, 20], {}) is None


class TestIouMatrix:
    """IoU 矩陣，用於把追蹤框對回偵測框以還原車種。"""

    def test_完全重疊為一(self):
        box = [[0, 0, 10, 10]]
        assert iou_matrix(box, box)[0, 0] == pytest.approx(1.0)

    def test_完全沒有交集為零(self):
        assert iou_matrix([[0, 0, 10, 10]], [[20, 20, 30, 30]])[0, 0] == pytest.approx(0.0)

    def test_部分重疊的數值正確(self):
        # 兩個 10x10 的框錯開 5 像素：交集 25、聯集 175
        result = iou_matrix([[0, 0, 10, 10]], [[5, 5, 15, 15]])
        assert result[0, 0] == pytest.approx(25.0 / 175.0)

    def test_矩陣形狀為_N乘M(self):
        a = [[0, 0, 10, 10], [20, 20, 30, 30]]
        b = [[0, 0, 10, 10], [5, 5, 15, 15], [100, 100, 110, 110]]
        assert iou_matrix(a, b).shape == (2, 3)

    def test_空輸入回傳對應形狀的空矩陣(self):
        assert iou_matrix([], [[0, 0, 10, 10]]).shape == (0, 1)
        assert iou_matrix([[0, 0, 10, 10]], []).shape == (1, 0)

    def test_零面積框不會產生_NaN(self):
        """退化框（寬高為 0）不應讓除法產生 NaN，否則配對會整個壞掉。"""
        result = iou_matrix([[5, 5, 5, 5]], [[0, 0, 10, 10]])
        assert not np.isnan(result).any()

    def test_接受_numpy_陣列輸入(self):
        a = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert iou_matrix(a, a)[0, 0] == pytest.approx(1.0)
