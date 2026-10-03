# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：tools/zone_editor.py 的單元測試
功能說明：
    驗證區域編輯器的狀態管理與座標換算（不含 cv2 的互動主迴圈）。

    其中最關鍵的是滑鼠座標的縮放換算：畫面被縮小顯示時，
    若未換算回原始解析度，存出來的座標會整組偏移，
    導致之後所有計數都對應到錯誤的位置。

建立日期：2026-10-03
版本號：v1.0.0
"""

import json

import cv2
import numpy as np
import pytest

from tools.zone_editor import ZoneEditor, load_existing, load_frame


@pytest.fixture
def frame():
    return np.full((300, 400, 3), 80, dtype=np.uint8)


@pytest.fixture
def editor(frame, tmp_path):
    return ZoneEditor(frame, {}, str(tmp_path / "roads.json"))


def click(editor, x, y):
    """模擬在顯示座標 (x, y) 按下左鍵。"""
    editor.on_mouse(cv2.EVENT_LBUTTONDOWN, x, y, 0, None)


def add_polygon(editor, points):
    for x, y in points:
        click(editor, x, y)
    return editor.finish_polygon()


class TestInitialScale:
    """初始顯示縮放。"""

    def test_小圖不縮放(self):
        assert ZoneEditor._initial_scale(800, 600) == 1.0

    def test_大圖會被縮小(self):
        assert ZoneEditor._initial_scale(3840, 2160) < 1.0

    def test_縮放不低於下限(self):
        assert ZoneEditor._initial_scale(100000, 100000) >= 0.2


class TestPolygonEditing:
    """頂點與區域的編輯操作。"""

    def test_新增頂點(self, editor):
        click(editor, 10, 20)
        assert editor.current == [(10, 20)]
        assert editor.dirty is True

    def test_三點以上才能完成區域(self, editor):
        click(editor, 0, 0)
        click(editor, 10, 0)
        message = editor.finish_polygon()
        assert "至少要三個頂點" in message
        assert editor.polygons == []

    def test_完成區域後清空編輯中頂點(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10)])
        assert len(editor.polygons) == 1
        assert editor.current == []

    def test_復原頂點(self, editor):
        click(editor, 10, 10)
        click(editor, 20, 20)
        editor.undo_point()
        assert editor.current == [(10, 10)]

    def test_沒有頂點時復原不會崩潰(self, editor):
        assert "沒有可復原" in editor.undo_point()

    def test_刪除最後一個區域(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10)])
        add_polygon(editor, [(50, 50), (60, 50), (60, 60)])
        editor.delete_last_polygon()
        assert len(editor.polygons) == 1

    def test_沒有區域時刪除不會崩潰(self, editor):
        assert "沒有可刪除" in editor.delete_last_polygon()

    def test_清空全部(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10)])
        click(editor, 99, 99)
        editor.clear_all()
        assert editor.polygons == []
        assert editor.current == []


class TestCoordinateScaling:
    """滑鼠座標換算——出錯會讓所有區域整組偏移。"""

    def test_縮放時座標換算回原始解析度(self, editor):
        editor.scale = 0.5
        click(editor, 100, 60)
        # 顯示座標 (100, 60) 在 0.5 倍縮放下對應原圖 (200, 120)
        assert editor.current == [(200, 120)]

    def test_未縮放時座標不變(self, editor):
        editor.scale = 1.0
        click(editor, 123, 45)
        assert editor.current == [(123, 45)]

    def test_放大時座標也正確換算(self, editor):
        editor.scale = 2.0
        click(editor, 200, 100)
        assert editor.current == [(100, 50)]


class TestSaveAndLoad:
    """存檔與載入。"""

    def test_存成扁平座標格式(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10), (0, 10)])
        editor.save()

        with open(editor.output_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data == {"1": [0, 0, 10, 0, 10, 10, 0, 10]}

    def test_道路編號由一開始連續編號(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10)])
        add_polygon(editor, [(50, 50), (60, 50), (60, 60)])
        editor.save()

        with open(editor.output_path, encoding="utf-8") as f:
            data = json.load(f)

        assert sorted(data.keys()) == ["1", "2"]

    def test_存檔後清除未存檔標記(self, editor):
        add_polygon(editor, [(0, 0), (10, 0), (10, 10)])
        assert editor.dirty is True
        editor.save()
        assert editor.dirty is False

    def test_沒有區域時不會寫出空檔(self, editor):
        assert "沒有任何區域" in editor.save()

    def test_存檔與載入可往返(self, frame, tmp_path):
        """存出去再讀回來，區域數量與座標必須完全相同。"""
        path = str(tmp_path / "roads.json")
        first = ZoneEditor(frame, {}, path)
        add_polygon(first, [(5, 5), (50, 5), (50, 50), (5, 50)])
        first.save()

        second = ZoneEditor(frame, load_existing(path), path)
        assert second.polygons == first.polygons

    def test_載入既有區域(self, frame, tmp_path):
        existing = {"1": [0, 0, 10, 0, 10, 10], "2": [20, 20, 30, 20, 30, 30]}
        editor = ZoneEditor(frame, existing, str(tmp_path / "x.json"))
        assert len(editor.polygons) == 2

    def test_載入時略過點數不足的區域(self, frame, tmp_path):
        editor = ZoneEditor(frame, {"1": [0, 0, 10, 10]}, str(tmp_path / "x.json"))
        assert editor.polygons == []


class TestLoadExisting:
    """既有設定檔讀取。"""

    def test_檔案不存在時回傳空字典(self, tmp_path):
        assert load_existing(str(tmp_path / "沒有這個檔.json")) == {}

    def test_檔案損毀時回傳空字典而不崩潰(self, tmp_path):
        """設定檔壞掉只應從空白開始，不得讓工具無法啟動。"""
        path = tmp_path / "壞掉.json"
        path.write_text("{ 這不是合法的 JSON", encoding="utf-8")
        assert load_existing(str(path)) == {}


class TestLoadFrame:
    """影格讀取。"""

    def test_讀出指定影格(self, tmp_path):
        video = tmp_path / "tiny.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
        for i in range(5):
            writer.write(np.full((48, 64, 3), i * 40, dtype=np.uint8))
        writer.release()

        frame = load_frame(str(video), 0)
        assert frame.shape == (48, 64, 3)

    def test_影片不存在時拋出明確例外(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="找不到影片檔案"):
            load_frame(str(tmp_path / "無.mp4"), 0)


class TestRender:
    """畫面繪製。"""

    def test_輸出高度包含說明列(self, editor, frame):
        canvas = editor.render("測試訊息")
        # 說明列 92 px，且會再套用顯示縮放
        assert canvas.shape[0] > frame.shape[0]

    def test_有區域時仍可繪製(self, editor):
        add_polygon(editor, [(10, 10), (100, 10), (100, 100), (10, 100)])
        assert editor.render("").shape[2] == 3

    def test_編輯中的頂點也會被畫出(self, editor):
        click(editor, 50, 50)
        assert editor.render("").size > 0

    def test_縮放會改變輸出尺寸(self, editor):
        normal = editor.render("")
        editor.scale = 0.5
        smaller = editor.render("")
        assert smaller.shape[1] < normal.shape[1]
