# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：詳細資料面板與每分鐘車流紀錄的單元測試
功能說明：
    1. 每分鐘車流：由累計車次推導各分鐘新增量、只保留最近數分鐘、小時流量推估。
    2. 面板：資料整理函式的數值正確性，以及各種資料狀態下都能畫出正確大小的面板。

建立日期：2026-10-09
版本號：v1.2.0
"""

import numpy as np
import pytest

from multiview.camera_pipeline import render_scale
from multiview.detail_panel import DetailPanel, composition_rows, format_elapsed, line_totals
from multiview.flow_history import FlowHistory
from utils.text_drawer import TextDrawer


class TestFlowHistory:
    def test_由累計車次推導每分鐘新增量(self):
        history = FlowHistory(10)
        history.update(10, 3)
        history.update(50, 5)
        history.update(70, 9)
        assert history.recent() == [5, 4]

    def test_沒有車通過的分鐘補零(self):
        history = FlowHistory(10)
        history.update(10, 2)
        history.update(190, 3)
        assert history.recent() == [2, 0, 0, 1]

    def test_只保留最近數分鐘(self):
        history = FlowHistory(3)
        for minute in range(6):
            history.update(minute * 60 + 1, (minute + 1) * 2)
        assert history.recent() == [2, 2, 2]

    def test_累計值回退時不產生負車流(self):
        history = FlowHistory(10)
        history.update(10, 5)
        history.update(20, 4)
        history.update(30, 6)
        assert history.recent() == [6]

    def test_尚未取樣時回傳單一零值(self):
        assert FlowHistory(5).recent() == [0]

    def test_小時流量推估(self):
        assert FlowHistory.hourly_rate(30, 600) == 180

    def test_觀測太短時不推估(self):
        assert FlowHistory.hourly_rate(5, 30) is None


class TestPanelHelpers:
    def test_時間格式(self):
        assert format_elapsed(75) == "01:15"
        assert format_elapsed(3725) == "1:02:05"
        assert format_elapsed(-5) == "00:00"

    def test_計數線加總(self):
        statistics = {"越線計數": {1: {"進入": 3, "離開": 1}, 2: {"進入": 2, "離開": 4}}}
        assert line_totals(statistics) == (5, 5)
        assert line_totals({}) == (0, 0)

    def test_車種組成依車次排序並計算占比(self):
        rows = composition_rows({"車種組成": {"機車": 1, "小客車": 3}})
        assert rows[0] == ("小客車", 3, 0.75)
        assert rows[1] == ("機車", 1, 0.25)

    def test_沒有車輛時車種組成為空(self):
        assert composition_rows({}) == []
        assert composition_rows({"車種組成": {"小客車": 0}}) == []

    def test_影像不需縮小時不放大字級(self):
        assert render_scale(640, 800) == 1.0
        assert render_scale(0, 800) == 1.0
        assert render_scale(1920, 0) == 1.0

    def test_影像縮小時依比例放大(self):
        assert render_scale(1600, 800) == 2.0


@pytest.fixture
def panel():
    drawer = TextDrawer(
        font_candidates=["C:/Windows/Fonts/msjh.ttc"],
        sizes={"small": 14, "normal": 18, "large": 24, "hero": 30},
    )
    return DetailPanel(drawer, width=900, block_height=480)


def full_block(per_minute):
    return {
        "name": "示範路口", "status": "分析中", "elapsed_secs": 185.0,
        "per_minute": per_minute, "history_slots": 10, "hourly_rate": 240,
        "statistics": {
            "累計車次": 12, "累計PCU": 10.5, "畫面車輛數": 3, "流率視窗秒": 30.0,
            "各道路累計": {1: 8, 2: 4}, "各道路流率": {1: 6.0, 2: 2.0},
            "車種組成": {"小客車": 9, "機車": 3},
            "越線計數": {1: {"名稱": "遠端道路", "進入": 5, "離開": 2},
                        2: {"名稱": "近端道路", "進入": 1, "離開": 4}},
        },
    }


class TestDetailPanel:
    def test_每個路口一個區塊(self, panel):
        image = panel.render([full_block([2, 5, 1]), full_block([0])])
        assert image.shape == (960, 900, 3)
        assert image.dtype == np.uint8

    def test_有資料時畫出圖形(self, panel):
        empty = panel.render([{"name": "示範路口", "status": "連線中", "statistics": {}}])
        filled = panel.render([full_block([2, 5, 1])])
        # 有資料的面板多了橫條、直條與數字，畫面必然不同
        assert not np.array_equal(empty, filled)

    def test_尚無任何統計時仍能繪製(self, panel):
        image = panel.render([{"name": "示範路口", "status": "連線中", "statistics": {}}])
        assert image.shape == (480, 900, 3)

    def test_沒有路口時回傳一個空區塊大小的畫布(self, panel):
        assert panel.render([]).shape == (480, 900, 3)

    def test_直條數超過保留欄位時不出錯(self, panel):
        block = full_block(list(range(15)))
        block["history_slots"] = 5
        assert panel.render([block]).shape == (480, 900, 3)

    def test_整段沒有車時直條圖不出錯(self, panel):
        assert panel.render([full_block([0, 0, 0])]).shape == (480, 900, 3)
