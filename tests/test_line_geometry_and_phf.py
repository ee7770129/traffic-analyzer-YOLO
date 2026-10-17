# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：計數線幾何、尖峰小時係數與 lap 相容層的單元測試
功能說明：
    三者皆為純函式，出錯會直接讓計數與指標失真，故集中驗證邊界情況。

建立日期：2026-10-08
版本號：v1.2.0
"""

import numpy as np
import pytest

import lap
from utils.line_geometry import (
    DIRECTION_IN,
    DIRECTION_OUT,
    anchor_point,
    crossing_direction,
    segments_intersect,
    side_of_line,
)
from utils.phf import bin_counts, compute_phf

# 一條水平計數線 y=100，路口內側在線的下方
LINE_START, LINE_END, INSIDE = (0, 100), (200, 100), (100, 300)


class TestAnchorPoint:
    def test_預設取底邊中點(self):
        assert anchor_point([10, 20, 30, 60]) == (20.0, 60.0)

    def test_可改取中心點(self):
        assert anchor_point([10, 20, 30, 60], "center") == (20.0, 40.0)


class TestSegments:
    def test_線兩側的點外積異號(self):
        above = side_of_line((50, 50), LINE_START, LINE_END)
        below = side_of_line((50, 150), LINE_START, LINE_END)
        assert above * below < 0

    def test_交叉線段判定為相交(self):
        assert segments_intersect((50, 50), (50, 150), LINE_START, LINE_END)

    def test_平行線段不相交(self):
        assert not segments_intersect((0, 50), (200, 50), LINE_START, LINE_END)

    def test_位移未延伸到線的範圍內不相交(self):
        assert not segments_intersect((300, 50), (300, 150), LINE_START, LINE_END)


class TestCrossingDirection:
    def test_由外側跨到內側為進入(self):
        assert crossing_direction((50, 50), (50, 150), LINE_START, LINE_END, INSIDE) == DIRECTION_IN

    def test_由內側跨到外側為離開(self):
        assert crossing_direction((50, 150), (50, 50), LINE_START, LINE_END, INSIDE) == DIRECTION_OUT

    def test_未跨線回傳None(self):
        assert crossing_direction((50, 110), (50, 150), LINE_START, LINE_END, INSIDE) is None

    def test_低幀率下一步跨越很遠仍能判定(self):
        assert crossing_direction((10, 0), (190, 290), LINE_START, LINE_END, INSIDE) == DIRECTION_IN

    def test_參考點在線上時不計數(self):
        assert crossing_direction((50, 50), (50, 150), LINE_START, LINE_END, (100, 100)) is None


class TestPhf:
    def test_區間彙總捨去尾端不完整區間(self):
        assert bin_counts([10, 20, 950, 1900], 900, 1900) == [2, 1]

    def test_區間長度不合法回傳空串列(self):
        assert bin_counts([1, 2], 0, 100) == []

    def test_觀測不足一小時回傳None(self):
        assert compute_phf([10, 20, 30], duration_secs=1800) is None

    def test_均勻車流的PHF為1(self):
        timestamps = [p * 900 + i for p in range(4) for i in range(10)]
        result = compute_phf(timestamps, duration_secs=3600)
        assert result["PHF"] == 1.0
        assert result["尖峰小時流量"] == 40

    def test_集中於單一區間的PHF為0點25(self):
        result = compute_phf(list(range(20)), duration_secs=3600)
        assert result["PHF"] == 0.25

    def test_手算案例(self):
        # 四個區間 10、20、30、20 輛：80 / (4 × 30) = 0.667
        timestamps = []
        for period, count in enumerate([10, 20, 30, 20]):
            timestamps += [period * 900 + i for i in range(count)]
        assert compute_phf(timestamps, duration_secs=3600)["PHF"] == pytest.approx(0.667)

    def test_超過一小時時取流量最大的連續一小時(self):
        timestamps = []
        for period, count in enumerate([1, 1, 10, 10, 10, 10]):
            timestamps += [period * 900 + i for i in range(count)]
        result = compute_phf(timestamps, duration_secs=5400)
        assert result["尖峰起始_秒"] == 1800
        assert result["尖峰小時流量"] == 40

    def test_整段沒有車回傳None(self):
        assert compute_phf([], duration_secs=7200) is None


class TestLapCompat:
    """相容層的結果需與原套件的語意一致，否則追蹤配對會改變。"""

    def test_選出總成本最低的配對(self):
        cost, x, y = lap.lapjv(np.array([[1.0, 5.0], [5.0, 1.0]]), extend_cost=True, cost_limit=10.0)
        assert list(x) == [0, 1] and list(y) == [0, 1]
        assert cost == pytest.approx(2.0)

    def test_成本高於上限者不配對(self):
        _, x, y = lap.lapjv(np.array([[0.2, 9.0], [9.0, 9.0]]), extend_cost=True, cost_limit=1.0)
        assert list(x) == [0, -1]
        assert list(y) == [0, -1]

    def test_非方陣時多出的欄位未配對(self):
        _, x, y = lap.lapjv(np.array([[0.1, 0.9, 0.5]]), extend_cost=True, cost_limit=1.0)
        assert list(x) == [0]
        assert list(y) == [0, -1, -1]

    def test_空矩陣回傳空結果(self):
        cost, x, y = lap.lapjv(np.empty((0, 3)), extend_cost=True, cost_limit=1.0)
        assert cost == 0.0 and len(x) == 0 and list(y) == [-1, -1, -1]

    def test_不設上限時全部配對(self):
        x, y = lap.lapjv(np.array([[3.0, 1.0], [1.0, 3.0]]), return_cost=False)
        assert list(x) == [1, 0] and list(y) == [1, 0]

    def test_非二維輸入拋出錯誤(self):
        with pytest.raises(ValueError):
            lap.lapjv(np.array([1.0, 2.0]))
