# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：路口影像來源、熱力圖、尖峰小時係數報表、串流重連與節點組裝的單元測試
功能說明：
    網路連線一律以替身取代，測試不會真的連到交通局的伺服器。

建立日期：2026-10-08
版本號：v1.2.0
"""

import csv
import os

import cv2
import numpy as np
import pytest

import pipeline_builder
from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from nodes.heatmap_node import HeatmapNode
from nodes.phf_report_node import PhfReportNode
from nodes.video_reader_node import VideoReaderNode
from utils.cctv_source import (
    CctvSourceError,
    extract_stream_url,
    fetch_stream_url,
    load_catalog,
    resolve_camera,
)

_PAGE_HTML = '<html><body><img style="x" width=\'352\' src="https://nvr.example/abc123"></body></html>'

_CATALOG_TEXT = """
page_url_template: "https://example.test/show?id={camera_id}"
request_timeout_secs: 3
cameras:
  demo:
    name: 示範路口
    camera_id: C000001
    roads_info: zones.json
    lines_file: lines.json
"""


class FakeResponse:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_opener(text=_PAGE_HTML, calls=None):
    def opener(url, timeout=None):
        if calls is not None:
            calls.append((url, timeout))
        return FakeResponse(text)
    return opener


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "cameras.yaml"
    path.write_text(_CATALOG_TEXT, encoding="utf-8")
    return str(path)


class TestCctvSource:
    def test_由頁面取出串流網址(self):
        assert extract_stream_url(_PAGE_HTML) == "https://nvr.example/abc123"

    def test_頁面沒有影像標籤回傳None(self):
        assert extract_stream_url("<html></html>") is None
        assert extract_stream_url(None) is None

    def test_解析路口預設組(self, catalog_file):
        calls = []
        camera = resolve_camera("demo", load_catalog(catalog_file), fake_opener(calls=calls))
        assert camera == {
            "key": "demo", "name": "示範路口", "src": "https://nvr.example/abc123",
            "roads_info": "zones.json", "lines_file": "lines.json",
        }
        assert calls == [("https://example.test/show?id=C000001", 3.0)]

    def test_預設組不存在時列出可用名稱(self, catalog_file):
        with pytest.raises(CctvSourceError, match="demo"):
            resolve_camera("nope", load_catalog(catalog_file), fake_opener())

    def test_頁面格式改變時拋出錯誤(self):
        with pytest.raises(CctvSourceError, match="找不到串流網址"):
            fetch_stream_url("https://example.test", 3, fake_opener("<html></html>"))

    def test_連線失敗時轉為本模組的錯誤(self):
        def broken(url, timeout=None):
            raise OSError("網路不通")
        with pytest.raises(CctvSourceError, match="無法連線"):
            fetch_stream_url("https://example.test", 3, broken)

    def test_目錄檔不存在或沒有路口時拋出錯誤(self, tmp_path):
        with pytest.raises(CctvSourceError):
            load_catalog(str(tmp_path / "missing.yaml"))
        empty = tmp_path / "empty.yaml"
        empty.write_text("cameras: {}", encoding="utf-8")
        with pytest.raises(CctvSourceError):
            load_catalog(str(empty))

    def test_專案內附的目錄檔格式正確(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        catalog = load_catalog(os.path.join(root, "configs", "cctv_cameras.yaml"))
        assert len(catalog["cameras"]) >= 2
        for camera in catalog["cameras"].values():
            assert os.path.isfile(os.path.join(root, camera["roads_info"]))
            assert os.path.isfile(os.path.join(root, camera["lines_file"]))


def frame_with_track(timestamp, xyxy, shape=(60, 80, 3)):
    element = FrameElement("test", np.full(shape, 50, dtype=np.uint8), timestamp, 1, {})
    track = TrackElement(1, 0.0)
    track.update(timestamp, xyxy)
    element.active_tracks = {1: track}
    return element


@pytest.fixture
def heatmap_config():
    return {"anchor": "center", "blur_sigma": 3.0, "alpha": 0.6,
            "clip_percentile": 99.0, "output_name": "軌跡熱力圖.png"}


class TestHeatmapNode:
    def test_累積位置並輸出圖檔(self, heatmap_config, tmp_path):
        node = HeatmapNode(heatmap_config, str(tmp_path))
        for i in range(5):
            node.process(frame_with_track(i, [30, 20, 50, 40]))
        node.process(StreamEndElement("test", 5.0))

        assert os.path.isfile(node.output_path)
        image = cv2.imdecode(np.fromfile(node.output_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (60, 80, 3)
        # 車輛所在位置被疊色，遠處角落維持底圖原色
        assert not np.array_equal(image[30, 40], [50, 50, 50])
        assert np.array_equal(image[0, 0], [50, 50, 50])

    def test_畫面外的點被忽略(self, heatmap_config, tmp_path):
        node = HeatmapNode(heatmap_config, str(tmp_path))
        node.process(frame_with_track(0.0, [500, 500, 520, 520]))
        assert float(node._accumulator.sum()) == 0.0
        assert node.render() is None

    def test_沒有資料時不輸出檔案(self, heatmap_config, tmp_path):
        node = HeatmapNode(heatmap_config, str(tmp_path))
        node.process(StreamEndElement("test", 0.0))
        assert not os.path.exists(node.output_path)

    def test_沒有邊界框的軌跡被略過(self, heatmap_config, tmp_path):
        node = HeatmapNode(heatmap_config, str(tmp_path))
        element = FrameElement("test", np.zeros((60, 80, 3), dtype=np.uint8), 0.0, 1, {})
        element.active_tracks = {1: TrackElement(1, 0.0)}
        node.process(element)
        assert float(node._accumulator.sum()) == 0.0


def counted_track(track_id, road, entry_time, counted=True):
    track = TrackElement(track_id, entry_time)
    track.observe_zone(road, entry_time)
    track.counted_entry = counted
    return track


class TestPhfReportNode:
    def make_node(self, base_config, tmp_path):
        config = dict(base_config)
        config["phf_node"] = {"period_secs": 900, "periods_per_hour": 4}
        return PhfReportNode(config, str(tmp_path))

    def read(self, node):
        with open(node.output_path, encoding="utf-8-sig") as file:
            return list(csv.reader(file))

    def test_滿一小時輸出全路口與各道路的PHF(self, base_config, tmp_path):
        node = self.make_node(base_config, tmp_path)
        end = StreamEndElement("test", 3600.0)
        end.retired_tracks = [
            counted_track(i, 1 if i % 2 else 2, period * 900 + i)
            for period in range(4) for i in range(1, 11)
        ]
        node.process(end)

        rows = self.read(node)
        assert rows[1][0] == "全路口" and rows[1][1] == "40" and rows[1][5] == "1.0"
        assert {row[0] for row in rows[2:]} == {"道路 1", "道路 2"}

    def test_不足一小時時寫明無法計算(self, base_config, tmp_path):
        node = self.make_node(base_config, tmp_path)
        end = StreamEndElement("test", 600.0)
        end.retired_tracks = [counted_track(1, 1, 10.0)]
        node.process(end)

        rows = self.read(node)
        assert rows[1][5] == "" and "無法計算" in rows[1][6]

    def test_未計入統計的軌跡不採計(self, base_config, tmp_path):
        node = self.make_node(base_config, tmp_path)
        element = FrameElement("test", np.zeros((4, 4, 3), dtype=np.uint8), 1.0, 1, {})
        element.retired_tracks = [counted_track(1, 1, 5.0, counted=False), TrackElement(2, 0.0)]
        node.process(element)
        assert node._entries == []


class FakeCapture:
    """可程式化的影像來源替身：依序回傳預先排定的讀取結果。"""

    def __init__(self, results, opened=True):
        self._results = list(results)
        self._opened = opened

    def isOpened(self):
        return self._opened

    def read(self):
        if self._results:
            return self._results.pop(0)
        return False, None

    def get(self, prop):
        return 0

    def set(self, prop, value):
        return True

    def release(self):
        self._opened = False


class TestStreamReconnect:
    def make_reader(self, monkeypatch, tmp_path, captures, attempts):
        roads = tmp_path / "roads.json"
        roads.write_text('{"1": [0, 0, 10, 0, 10, 10]}', encoding="utf-8")
        queue = list(captures)
        monkeypatch.setattr(cv2, "VideoCapture", lambda src: queue.pop(0))
        return VideoReaderNode({
            "src": "https://nvr.example/stream", "roads_info": str(roads),
            "reconnect_attempts": attempts, "reconnect_wait_secs": 0,
        })

    def test_斷線後重連並繼續讀取(self, monkeypatch, tmp_path):
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        reader = self.make_reader(monkeypatch, tmp_path, [
            FakeCapture([(True, frame)]),
            FakeCapture([(True, frame), (True, frame)]),
            FakeCapture([], opened=False),
        ], attempts=1)

        elements = list(reader.process())
        assert sum(isinstance(e, FrameElement) for e in elements) == 3
        assert isinstance(elements[-1], StreamEndElement)
        assert reader.reconnect_count == 1

    def test_預設不重連維持原行為(self, monkeypatch, tmp_path):
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        reader = self.make_reader(monkeypatch, tmp_path, [FakeCapture([(True, frame)])], attempts=0)
        elements = list(reader.process())
        assert sum(isinstance(e, FrameElement) for e in elements) == 1
        assert reader.reconnect_count == 0

    def test_連續失敗達上限後結束(self, monkeypatch, tmp_path):
        reader = self.make_reader(monkeypatch, tmp_path, [
            FakeCapture([]), FakeCapture([]), FakeCapture([]),
        ], attempts=2)
        elements = list(reader.process())
        assert len(elements) == 1 and isinstance(elements[0], StreamEndElement)


class TestPipelineBuilder:
    def make_config(self, base_config, camera=None, lines_file=None):
        config = dict(base_config)
        config.update({
            "video_reader": {"src": "video.mp4", "roads_info": "roads.json", "skip_secs": 0},
            "cctv": {"camera": camera, "catalog": "unused.yaml", "max_duration_secs": 0},
            "line_counting": {"enabled": True, "lines_file": lines_file, "anchor": "center",
                              "line_color": [0, 255, 255], "line_thickness": 2},
            "heatmap_node": {"enabled": True, "anchor": "center", "blur_sigma": 3.0,
                             "alpha": 0.6, "output_name": "heat.png"},
            "phf_node": {"enabled": True, "period_secs": 900, "periods_per_hour": 4},
            "render_node": {"font_candidates": ["C:/Windows/Fonts/msjh.ttc"],
                            "font_sizes": {"small": 12, "normal": 16, "large": 20}},
        })
        return config

    def test_未指定路口時沿用原本的影像來源(self, base_config):
        reader_cfg, lines_file, label = pipeline_builder.resolve_reader_config(
            self.make_config(base_config)
        )
        assert reader_cfg["src"] == "video.mp4" and lines_file is None and label == "video.mp4"

    def test_指定路口時套用串流與專屬設定(self, base_config, monkeypatch):
        monkeypatch.setattr(pipeline_builder, "load_catalog", lambda path: {})
        monkeypatch.setattr(pipeline_builder, "resolve_camera", lambda key, catalog: {
            "key": key, "name": "示範路口", "src": "https://nvr.example/x",
            "roads_info": "zones.json", "lines_file": "lines.json",
        })
        reader_cfg, lines_file, label = pipeline_builder.resolve_reader_config(
            self.make_config(base_config, camera="demo")
        )
        assert reader_cfg["src"] == "https://nvr.example/x"
        assert reader_cfg["roads_info"] == "zones.json"
        assert lines_file == "lines.json" and label == "示範路口"

    def test_沒有計數線時只建立熱力圖與PHF(self, base_config, tmp_path):
        extras = pipeline_builder.build_extra_nodes(
            self.make_config(base_config), str(tmp_path), None, with_render=True, with_report=True
        )
        assert extras["analysis"] == [] and extras["render"] == []
        assert [type(n).__name__ for n in extras["report"]] == ["HeatmapNode", "PhfReportNode"]

    def test_有計數線時建立完整的越線節點(self, base_config, tmp_path):
        lines = tmp_path / "lines.json"
        lines.write_text('{"inside_point": [5, 5], "lines": [{"id": 1, "p1": [0, 0], "p2": [9, 0]}]}',
                         encoding="utf-8")
        extras = pipeline_builder.build_extra_nodes(
            self.make_config(base_config), str(tmp_path), str(lines),
            with_render=True, with_report=True,
        )
        assert [type(n).__name__ for n in extras["analysis"]] == ["LineCountingNode"]
        assert [type(n).__name__ for n in extras["render"]] == ["LineRenderNode"]
        assert type(extras["report"][0]).__name__ == "LineReportNode"

    def test_關閉報表時不建立輸出節點(self, base_config, tmp_path):
        extras = pipeline_builder.build_extra_nodes(
            self.make_config(base_config), str(tmp_path), None, with_render=False, with_report=False
        )
        assert extras == {"analysis": [], "render": [], "report": []}
