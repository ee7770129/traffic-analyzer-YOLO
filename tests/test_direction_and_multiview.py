# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：進入方向判定與多路口模式的單元測試
功能說明：
    1. 方向判定：朝路口內行駛才算進入，朝路口外行駛只記離開。
    2. 多格畫面排版：等比例縮放、格狀排列、標題文字。
    3. 路口執行緒：最新畫面的發布、提前結束的收尾、出錯時的隔離。

建立日期：2026-10-08
版本號：v1.2.0
"""

import json

import numpy as np
import pytest

import pipeline_builder
from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from multiview.camera_worker import (
    STATUS_CONNECTING,
    STATUS_ENDED,
    STATUS_ERROR,
    STATUS_RUNNING,
    CameraWorker,
)
from multiview.mosaic import build_cell, cell_origin, compose_grid, format_caption, letterbox
from nodes.track_update_node import TrackUpdateNode
from utils.direction_gate import DirectionGate

# 路口中心在 (150, 150)；square_roads 的區域 1 位於左上角 (0,0)~(100,100)
INSIDE = (150, 150)


def box(x, y):
    """以中心點產生邊界框。"""
    return [x - 5, y - 5, x + 5, y + 5]


class TestDirectionGate:
    def test_朝路口內行駛記為進入(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, 1, box(20, 20), 0.0)
        assert track.entry_road is None          # 還沒移動，先不下結論

        gate.observe(track, 1, box(60, 60), 1.0)
        assert track.entry_road == 1
        assert track.entry_timestamp == 0.0      # 以第一次出現的時間為準
        assert not track.entry_unseen

    def test_朝路口外行駛只記離開(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, 1, box(90, 90), 0.0)
        gate.observe(track, 1, box(40, 40), 1.0)

        assert track.entry_road is None
        assert track.exit_road == 1 and track.exit_timestamp == 0.0
        assert track.entry_unseen and track.zone_sequence == [1]
        assert not track.has_movement

    def test_只拍到離開的車之後不會被補記進入(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, 1, box(90, 90), 0.0)
        gate.observe(track, 1, box(40, 40), 1.0)
        gate.observe(track, 2, box(250, 50), 2.0)
        assert track.entry_road is None and track.exit_road == 1

    def test_停等中的車輛起步後才判定(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        for step in range(5):
            gate.observe(track, 1, box(20 + step, 20), float(step))   # 只有抖動
        assert track.entry_road is None

        gate.observe(track, 1, box(60, 60), 6.0)
        assert track.entry_road == 1

    def test_判定進入後照常推導離開道路(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, 1, box(20, 20), 0.0)
        gate.observe(track, None, box(120, 120), 1.0)
        gate.observe(track, 2, box(250, 50), 2.0)
        assert (track.entry_road, track.exit_road) == (1, 2)

    def test_尚未踩到區域時不建立判定狀態(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, None, box(150, 150), 0.0)
        assert gate._probes == {}

    def test_離場後清除狀態(self):
        gate, track = DirectionGate(INSIDE, 10), TrackElement(1, 0.0)
        gate.observe(track, 1, box(20, 20), 0.0)
        gate.forget(1)
        gate.forget(99)   # 不存在的編號不得出錯
        assert gate._probes == {} and gate._decided == set()


class TestTrackUpdateNodeWithGate:
    def make_frame(self, timestamp, xyxy, roads):
        element = FrameElement("test", np.zeros((300, 300, 3), dtype=np.uint8), timestamp, 1, roads)
        element.tracked_ids = [7]
        element.tracked_xyxy = [xyxy]
        element.tracked_cls = ["小客車"]
        return element

    def test_未提供判定器時維持原規則(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        element = node.process(self.make_frame(0.0, box(90, 90), square_roads))
        assert element.active_tracks[7].entry_road == 1

    def test_提供判定器時朝外行駛不算進入(self, base_config, square_roads):
        node = TrackUpdateNode(base_config, DirectionGate(INSIDE, 10))
        node.process(self.make_frame(0.0, box(90, 90), square_roads))
        element = node.process(self.make_frame(1.0, box(40, 40), square_roads))

        track = element.active_tracks[7]
        assert track.entry_road is None and track.exit_road == 1

    def test_軌跡離場時一併清除判定狀態(self, base_config, square_roads):
        gate = DirectionGate(INSIDE, 10)
        node = TrackUpdateNode(base_config, gate)
        node.process(self.make_frame(0.0, box(20, 20), square_roads))
        assert 7 in gate._probes

        empty = FrameElement("test", np.zeros((300, 300, 3), dtype=np.uint8), 10.0, 2, square_roads)
        node.process(empty)
        assert gate._probes == {}


class TestBuildDirectionGate:
    def make_lines(self, tmp_path):
        path = tmp_path / "lines.json"
        path.write_text(json.dumps({"inside_point": [5, 6], "lines": []}), encoding="utf-8")
        return str(path)

    def test_啟用且有計數線檔時建立判定器(self, tmp_path):
        config = {"general": {"direction_aware_entry": True, "direction_min_move_px": 20}}
        gate = pipeline_builder.build_direction_gate(config, self.make_lines(tmp_path))
        assert gate.inside_point == (5.0, 6.0) and gate.min_move_px == 20.0

    def test_沒有計數線檔或未啟用時回傳None(self, tmp_path):
        assert pipeline_builder.build_direction_gate(
            {"general": {"direction_aware_entry": True}}, None) is None
        assert pipeline_builder.build_direction_gate(
            {"general": {}}, self.make_lines(tmp_path)) is None


class TestMosaic:
    def test_等比例縮放後置中並留邊(self):
        frame = np.full((100, 200, 3), 255, dtype=np.uint8)   # 2:1 的影像放進正方形
        result = letterbox(frame, 100, 100)
        assert result.shape == (100, 100, 3)
        assert result[50, 50].tolist() == [255, 255, 255]
        assert result[5, 50].tolist() != [255, 255, 255]      # 上方為留邊

    def test_空影像回傳底色畫布(self):
        assert letterbox(np.zeros((0, 0, 3), dtype=np.uint8), 40, 30).shape == (30, 40, 3)

    def test_一格包含標題列與影像區(self):
        frame = np.full((50, 80, 3), 200, dtype=np.uint8)
        cell = build_cell(frame, 80, 50, 20)
        assert cell.shape == (70, 80, 3)
        assert cell[45, 40].tolist() == [200, 200, 200]
        assert cell[5, 40].tolist() != [200, 200, 200]        # 標題列不放影像

    def test_尚無影像時仍產生同樣大小的格子(self):
        assert build_cell(None, 80, 50, 20).shape == (70, 80, 3)

    def test_四格排成二乘二(self):
        cells = [np.full((10, 20, 3), value, dtype=np.uint8) for value in (10, 20, 30, 40)]
        grid = compose_grid(cells, 2)
        assert grid.shape == (20, 40, 3)
        assert grid[0, 0, 0] == 10 and grid[0, 39, 0] == 20
        assert grid[19, 0, 0] == 30 and grid[19, 39, 0] == 40

    def test_格數不足時以底色補齊(self):
        cells = [np.full((10, 20, 3), 99, dtype=np.uint8) for _ in range(3)]
        grid = compose_grid(cells, 2)
        assert grid.shape == (20, 40, 3) and grid[19, 39, 0] != 99

    def test_沒有任何格子時拋出錯誤(self):
        with pytest.raises(ValueError):
            compose_grid([], 2)

    def test_各格左上角座標(self):
        assert cell_origin(0, 2, 800, 516) == (0, 0)
        assert cell_origin(1, 2, 800, 516) == (800, 0)
        assert cell_origin(3, 2, 800, 516) == (800, 516)

    def test_標題文字加總越線進出量(self):
        statistics = {"累計車次": 12, "越線計數": {
            1: {"名稱": "北", "進入": 3, "離開": 1}, 2: {"名稱": "南", "進入": 2, "離開": 4}}}
        assert format_caption("示範路口", "分析中", statistics) == "示範路口　分析中　累計 12 輛　越線 進 5 出 5"

    def test_沒有統計時標題顯示零(self):
        assert format_caption("示範路口", "連線中", {}) == "示範路口　連線中　累計 0 輛　越線 進 0 出 0"


class FakePipeline:
    """流水線替身：依序吐出預先排定的元素。"""

    key = "demo"
    name = "示範路口"

    def __init__(self, elements, error=None):
        self._elements = elements
        self._error = error
        self.finished = False
        self.released = False

    def frames(self):
        for element in self._elements:
            yield element
        if self._error is not None:
            raise self._error

    def finish(self):
        self.finished = True
        return {"累計車次": 99}

    def release(self):
        self.released = True


def frame_element(value, total):
    element = FrameElement("test", np.zeros((4, 4, 3), dtype=np.uint8), 0.0, 1, {})
    element.frame_result = np.full((4, 4, 3), value, dtype=np.uint8)
    element.statistics = {"累計車次": total}
    return element


class TestCameraWorker:
    def test_啟動前的狀態為連線中(self):
        worker = CameraWorker(FakePipeline([]))
        frame, statistics, status = worker.snapshot()
        assert frame is None and statistics == {} and status == STATUS_CONNECTING

    def test_來源自行結束時保留最後畫面與最終統計(self):
        end = StreamEndElement("test", 1.0)
        end.statistics = {"累計車次": 5}
        pipeline = FakePipeline([frame_element(10, 1), frame_element(20, 2), end])

        worker = CameraWorker(pipeline)
        worker.run()

        frame, statistics, status = worker.snapshot()
        assert frame[0, 0, 0] == 20 and statistics == {"累計車次": 5} and status == STATUS_ENDED
        assert worker.frame_count == 2
        assert pipeline.released and not pipeline.finished   # 已由結束訊號收尾，不重複收尾

    def test_要求停止時處理完當前影格即收尾(self):
        pipeline = FakePipeline([frame_element(10, 1), frame_element(20, 2)])
        worker = CameraWorker(pipeline)
        worker.request_stop()
        worker.run()

        frame, statistics, status = worker.snapshot()
        assert worker.frame_count == 1 and frame[0, 0, 0] == 10
        assert pipeline.finished and statistics == {"累計車次": 99} and status == STATUS_ENDED

    def test_分析中的狀態(self):
        published = []
        pipeline = FakePipeline([frame_element(10, 1)])
        worker = CameraWorker(pipeline)
        original = worker._publish
        worker._publish = lambda *args: (published.append(args[2]), original(*args))
        worker.run()
        assert published[0] == STATUS_RUNNING

    def test_出錯時標示狀態並釋放資源(self):
        pipeline = FakePipeline([frame_element(10, 1)], error=RuntimeError("串流壞了"))
        worker = CameraWorker(pipeline)
        worker.run()

        frame, _, status = worker.snapshot()
        assert status == STATUS_ERROR and pipeline.released
        assert frame[0, 0, 0] == 10    # 出錯前的最後畫面仍保留
