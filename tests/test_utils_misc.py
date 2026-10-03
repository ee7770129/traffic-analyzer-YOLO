# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：FPS 計數器、效能裝飾器、中文繪字工具的單元測試
功能說明：
    這三個工具模組各自很小，合併於同一個測試檔，
    避免產生過多檔案數量相近但內容極少的測試檔。

建立日期：2026-10-03
版本號：v1.0.0
"""

import logging

import numpy as np
import pytest

from utils.fps_counter import FPSCounter
from utils.profiler import profile_time
from utils.text_drawer import TextDrawer


class TestFPSCounter:
    """滑動視窗 FPS 計算。"""

    def test_視窗未滿時回傳零(self):
        """初期數值不穩定，應回傳 0 而非跳動的假數值。"""
        counter = FPSCounter(window_frames=5)
        for _ in range(4):
            assert counter.update() == 0.0

    def test_視窗滿了之後回傳正值(self):
        counter = FPSCounter(window_frames=3)
        results = [counter.update() for _ in range(5)]
        assert results[0] == 0.0
        assert results[-1] > 0.0

    def test_視窗大小至少為二(self):
        """只有一個時間點算不出間隔，建構時應自動提升為 2。"""
        counter = FPSCounter(window_frames=1)
        assert counter.window_frames == 2


class TestProfileTime:
    """效能量測裝飾器。"""

    def test_回傳值原樣傳遞(self):
        class Dummy:
            @profile_time
            def work(self, value):
                return value * 2

        assert Dummy().work(21) == 42

    def test_例外不會被吞掉(self):
        class Dummy:
            @profile_time
            def boom(self):
                raise ValueError("預期的錯誤")

        with pytest.raises(ValueError):
            Dummy().boom()

    def test_保留原函式名稱(self):
        class Dummy:
            @profile_time
            def named(self):
                return None

        assert Dummy().named.__name__ == "named"

    def test_以_DEBUG_等級輸出耗時(self, caplog):
        class Dummy:
            @profile_time
            def work(self):
                return 1

        with caplog.at_level(logging.DEBUG, logger="profile"):
            Dummy().work()
        assert any("Dummy.work" in r.getMessage() for r in caplog.records)
        assert all(r.levelno == logging.DEBUG for r in caplog.records)


class TestTextDrawer:
    """中文文字繪製。"""

    @pytest.fixture
    def drawer(self):
        return TextDrawer(
            font_candidates=["C:/Windows/Fonts/msjh.ttc"],
            sizes={"small": 12, "normal": 16},
        )

    def test_找不到字型時退回預設而不崩潰(self):
        """字型缺失只應降級顯示，不得讓整個程式中斷。"""
        drawer = TextDrawer(font_candidates=["不存在的字型.ttf"], sizes={"normal": 16})
        assert drawer.font_path is None
        assert drawer.font("normal") is not None

    def test_候選清單為空也能建構(self):
        drawer = TextDrawer(font_candidates=[], sizes={})
        assert drawer.font("normal") is not None

    def test_繪製後尺寸與型別不變(self, drawer):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        result = drawer.draw(image, [{"text": "測試中文", "xy": (10, 10)}])
        assert result.shape == image.shape
        assert result.dtype == np.uint8

    def test_實際有畫上東西(self, drawer):
        """全黑底圖畫上白字後，必須有像素被改變。"""
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        result = drawer.draw(image, [{"text": "測試", "xy": (10, 10), "color": (255, 255, 255)}])
        assert result.sum() > 0

    def test_沒有文字項目時原樣回傳(self, drawer):
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        assert drawer.draw(image, []) is image

    def test_空字串項目被略過(self, drawer):
        image = np.zeros((50, 50, 3), dtype=np.uint8)
        result = drawer.draw(image, [{"text": "", "xy": (0, 0)}])
        assert result.sum() == 0

    def test_背景底色會被填上(self, drawer):
        image = np.zeros((60, 120, 3), dtype=np.uint8)
        result = drawer.draw(
            image, [{"text": "字", "xy": (10, 10), "color": (255, 255, 255), "bg": (0, 0, 255)}]
        )
        # 底色為紅色（BGR 的 R 通道），應有像素被填上
        assert result[:, :, 2].max() > 0

    def test_量測文字尺寸為正值(self, drawer):
        width, height = drawer.text_size("測試文字", "normal")
        assert width > 0 and height > 0

    def test_未知字級退回_normal(self, drawer):
        assert drawer.font("不存在的字級") is drawer.font("normal")
