# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：繪製節點與車種還原邏輯的單元測試
功能說明：
    1. RenderNode：以合成影格驗證疊圖尺寸與不改動原始影像。
    2. DetectionTrackingNode：只測不需要模型的純邏輯部分
       （追蹤器輸入組裝、IoU 回溯配對還原車種），
       以 object.__new__ 繞過建構子，避免測試時載入 YOLO 權重。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from nodes.detection_tracking_node import DetectionTrackingNode
from nodes.render_node import RenderNode
from utils.vehicle_types import VehicleTypeRegistry


@pytest.fixture
def render_config(general_config):
    return {
        "general": general_config,
        "render_node": {
            "show_roi": True,
            "show_labels": True,
            "show_panel": True,
            "draw_fps": True,
            "panel_width": 120,
            "box_thickness": 2,
            "fps_window_frames": 5,
            "window_scale": 1.0,
            "font_candidates": ["C:/Windows/Fonts/msjh.ttc"],
            "font_sizes": {"small": 10, "normal": 12, "large": 16},
        },
    }


def make_frame(square_roads, with_tracks=True):
    element = FrameElement(
        source="test",
        frame=np.full((320, 400, 3), 60, dtype=np.uint8),
        timestamp=5.0,
        frame_num=10,
        roads_info=square_roads,
        total_frames=100,
    )
    if with_tracks:
        track = TrackElement(1, 0.0)
        track.observe_zone(1, 0.5)
        track.vote_vehicle_type("小客車")
        element.tracked_ids = [1]
        element.tracked_xyxy = [[40, 40, 90, 90]]
        element.tracked_cls = ["小客車"]
        element.active_tracks = {1: track}
    element.statistics = {
        "累計車次": 12,
        "累計PCU": 13.5,
        "各道路累計": {1: 7, 2: 3, 3: 2},
        "各道路流率": {1: 4.0, 2: 1.5, 3: 0.5},
        "車種組成": {"小客車": 10, "機車": 2},
        "轉向筆數": 5,
        "畫面車輛數": 1,
        "流率視窗秒": 30.0,
    }
    return element


class TestRenderNode:
    """畫面繪製。"""

    def test_輸出影格寬度等於原寬加面板寬(self, render_config, square_roads):
        node = RenderNode(render_config)
        element = node.process(make_frame(square_roads))
        assert element.frame_result.shape == (320, 400 + 120, 3)

    def test_關閉面板時寬度不變(self, render_config, square_roads):
        render_config["render_node"]["show_panel"] = False
        node = RenderNode(render_config)
        element = node.process(make_frame(square_roads))
        assert element.frame_result.shape == (320, 400, 3)

    def test_不修改原始影格(self, render_config, square_roads):
        """原始影格後續還要寫入影片，不能被疊圖污染。"""
        node = RenderNode(render_config)
        element = make_frame(square_roads)
        original = element.frame.copy()
        node.process(element)
        assert np.array_equal(element.frame, original)

    def test_確實畫上了東西(self, render_config, square_roads):
        node = RenderNode(render_config)
        element = node.process(make_frame(square_roads))
        # 底圖為均勻灰階，疊圖後畫面內容必定改變
        assert not np.all(element.frame_result[:, :400] == 60)

    def test_沒有追蹤結果也能繪製(self, render_config, square_roads):
        node = RenderNode(render_config)
        element = node.process(make_frame(square_roads, with_tracks=False))
        assert element.frame_result is not None

    def test_關閉區域與標籤仍可執行(self, render_config, square_roads):
        render_config["render_node"]["show_roi"] = False
        render_config["render_node"]["show_labels"] = False
        render_config["render_node"]["draw_fps"] = False
        node = RenderNode(render_config)
        assert node.process(make_frame(square_roads)).frame_result is not None

    def test_統計為空時不崩潰(self, render_config, square_roads):
        node = RenderNode(render_config)
        element = make_frame(square_roads)
        element.statistics = {}
        assert node.process(element).frame_result is not None

    def test_結束訊號原樣回傳(self, render_config):
        node = RenderNode(render_config)
        end = StreamEndElement("test", 1.0)
        assert node.process(end) is end


class TestRestoreVehicleTypes:
    """車種還原——本專案相對參考專案的關鍵改良。"""

    def make_node(self, vehicle_types_config, match_iou=0.45):
        """繞過建構子，只組出車種還原所需的屬性，避免載入 YOLO。"""
        node = object.__new__(DetectionTrackingNode)
        node.class_match_iou = match_iou
        node.vehicle_types = VehicleTypeRegistry(vehicle_types_config)
        return node

    def test_高重疊時取得偵測框的車種(self, vehicle_types_config):
        node = self.make_node(vehicle_types_config)
        tracked = [[0, 0, 10, 10]]
        detected = np.array([[0.0, 0.0, 10.0, 10.0]])
        assert node._restore_vehicle_types(tracked, detected, ["機車"]) == ["機車"]

    def test_低重疊時回傳_None_不投票(self, vehicle_types_config):
        """
        物件被遮擋時追蹤器以卡爾曼濾波預測位置，該幀沒有對應偵測框。
        此時必須回傳 None 讓該幀不投票，這正是需要多數決的原因。
        """
        node = self.make_node(vehicle_types_config)
        tracked = [[0, 0, 10, 10]]
        detected = np.array([[100.0, 100.0, 110.0, 110.0]])
        assert node._restore_vehicle_types(tracked, detected, ["機車"]) == [None]

    def test_多個追蹤框各自配對最相近的偵測框(self, vehicle_types_config):
        node = self.make_node(vehicle_types_config)
        tracked = [[0, 0, 10, 10], [100, 100, 110, 110]]
        detected = np.array([[100.0, 100.0, 110.0, 110.0], [0.0, 0.0, 10.0, 10.0]])
        labels = ["大貨車", "機車"]
        assert node._restore_vehicle_types(tracked, detected, labels) == ["機車", "大貨車"]

    def test_沒有偵測框時全部回傳_None(self, vehicle_types_config):
        node = self.make_node(vehicle_types_config)
        result = node._restore_vehicle_types([[0, 0, 10, 10]], np.zeros((0, 4)), [])
        assert result == [None]

    def test_沒有追蹤框時回傳空串列(self, vehicle_types_config):
        node = self.make_node(vehicle_types_config)
        assert node._restore_vehicle_types([], np.array([[0.0, 0.0, 10.0, 10.0]]), ["機車"]) == []

    def test_門檻可調整(self, vehicle_types_config):
        """提高門檻後，原本勉強配上的框應被判定為失敗。"""
        tracked = [[0, 0, 10, 10]]
        detected = np.array([[5.0, 5.0, 15.0, 15.0]])  # IoU 約 0.14

        loose = self.make_node(vehicle_types_config, match_iou=0.1)
        strict = self.make_node(vehicle_types_config, match_iou=0.9)
        assert loose._restore_vehicle_types(tracked, detected, ["機車"]) == ["機車"]
        assert strict._restore_vehicle_types(tracked, detected, ["機車"]) == [None]


class TestBuildTrackerInput:
    """追蹤器輸入組裝。"""

    def make_node(self):
        return object.__new__(DetectionTrackingNode)

    def test_輸出形狀為_N乘六(self):
        node = self.make_node()
        xyxy = np.array([[0.0, 0.0, 10.0, 10.0], [5.0, 5.0, 20.0, 20.0]])
        conf = np.array([0.9, 0.8])
        assert node._build_tracker_input(xyxy, conf).shape == (2, 6)

    def test_類別欄位統一為二(self):
        """統一類別是為了維持追蹤器的穩定配對行為，車種另行還原。"""
        node = self.make_node()
        xyxy = np.array([[0.0, 0.0, 10.0, 10.0]])
        result = node._build_tracker_input(xyxy, np.array([0.9]))
        assert result[0, 5] == pytest.approx(2.0)

    def test_座標與信心值被保留(self):
        node = self.make_node()
        xyxy = np.array([[1.0, 2.0, 3.0, 4.0]])
        result = node._build_tracker_input(xyxy, np.array([0.75]))
        assert result[0, :4].tolist() == [1.0, 2.0, 3.0, 4.0]
        assert result[0, 4] == pytest.approx(0.75)

    def test_無偵測時回傳空的六欄陣列(self):
        """空陣列形狀不對會讓追蹤器取用時崩潰。"""
        node = self.make_node()
        result = node._build_tracker_input(np.zeros((0, 4)), np.zeros((0,)))
        assert result.shape == (0, 6)
