# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：越線計數、越線報表與計數線繪製的單元測試
功能說明：
    以人工構造的軌跡驗證進出方向、計數門檻、去重、轉向配對與報表內容。

建立日期：2026-10-08
版本號：v1.2.0
"""

import csv
import json
import os

import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from nodes.line_counting_node import LineCountingNode, load_lines
from nodes.line_render_node import LineRenderNode
from nodes.line_report_node import LineReportNode, build_line_movements


@pytest.fixture
def lines_file(tmp_path):
    """兩條水平計數線：北線 y=100、南線 y=300，路口中心在兩線之間。"""
    path = tmp_path / "lines.json"
    path.write_text(json.dumps({
        "inside_point": [100, 200],
        "lines": [
            {"id": 1, "name": "北側", "p1": [0, 100], "p2": [200, 100]},
            {"id": 2, "name": "南側", "p1": [0, 300], "p2": [200, 300]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return str(path)


@pytest.fixture
def line_config(base_config):
    config = dict(base_config)
    config["line_counting"] = {
        "anchor": "center", "line_color": [0, 255, 255], "line_thickness": 2,
    }
    config["render_node"] = {
        "font_candidates": ["C:/Windows/Fonts/msjh.ttc"],
        "font_sizes": {"small": 12, "normal": 16, "large": 20},
    }
    return config


def make_frame(timestamp, tracks, retired=()):
    element = FrameElement("test", np.zeros((400, 200, 3), dtype=np.uint8), timestamp, 1, {})
    element.active_tracks = {t.track_id: t for t in tracks}
    element.retired_tracks = list(retired)
    return element


def drive(node, track, path, label="小客車", start=0.0, step=0.5):
    """讓一台車依序經過 path 上的各點（以中心點表示），回傳最後的時間。"""
    timestamp = start
    for x, y in path:
        track.update(timestamp, [x - 5, y - 5, x + 5, y + 5])
        track.vote_vehicle_type(label)
        node.process(make_frame(timestamp, [track]))
        timestamp += step
    return timestamp


def retire(node, track, timestamp):
    return node.process(make_frame(timestamp, [], [track]))


class TestLoadLines:
    def test_讀出參考點與計數線(self, lines_file):
        loaded = load_lines(lines_file)
        assert loaded["inside_point"] == (100.0, 200.0)
        assert loaded["lines"][2]["name"] == "南側"

    def test_檔案不存在時拋出錯誤(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_lines(str(tmp_path / "missing.json"))


class TestLineCountingNode:
    def test_直行車輛記為北進南出(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        end = drive(node, track, [(100, 50), (100, 150), (100, 250), (100, 350)])

        stats = node.process(make_frame(end, [track])).statistics["越線計數"]
        assert stats[1]["進入"] == 1 and stats[1]["離開"] == 0
        assert stats[2]["離開"] == 1 and stats[2]["進入"] == 0

        records = retire(node, track, end).line_events
        assert [(r["計數線名稱"], r["方向"]) for r in records] == [("北側", "進入"), ("南側", "離開")]
        assert records[0]["車種"] == "小客車" and records[0]["PCU"] == 1.0

    def test_在線上來回抖動只計一次(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        end = drive(node, track, [(100, 90), (100, 110), (100, 90), (100, 110), (100, 120)])

        assert node.live_counts[1]["進入"] == 1
        assert node.live_counts[1]["離開"] == 1
        assert len(retire(node, track, end).line_events) == 2

    def test_未達門檻的軌跡不計入也不產生紀錄(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        # 只有兩幀、存活 0.5 秒，低於 min_track_life_secs=1.0
        end = drive(node, track, [(100, 50), (100, 150)])

        assert node.live_counts[1]["進入"] == 0
        assert retire(node, track, end).line_events == []

    def test_越線後才達門檻會補計(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        drive(node, track, [(100, 50), (100, 150)])
        assert node.live_counts[1]["進入"] == 0

        drive(node, track, [(100, 160), (100, 170)], start=1.0)
        assert node.live_counts[1]["進入"] == 1

    def test_最終紀錄採用離場時的車種(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        end = drive(node, track, [(100, 50), (100, 150), (100, 160)], label="小客車")
        for _ in range(10):
            track.vote_vehicle_type("機車")

        records = retire(node, track, end).line_events
        assert records[0]["車種"] == "機車" and records[0]["PCU"] == 0.5

    def test_結束訊號會結算殘留軌跡(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        track = TrackElement(1, 0.0)
        drive(node, track, [(100, 50), (100, 150), (100, 160)])

        end_element = StreamEndElement("test", 2.0)
        end_element.retired_tracks = [track]
        assert len(node.process(end_element).line_events) == 1

    def test_沒有邊界框的軌跡被略過(self, line_config, lines_file):
        node = LineCountingNode(line_config, lines_file)
        node.process(make_frame(0.0, [TrackElement(1, 0.0)]))
        assert node._states == {}


def record(track_id, timestamp, line, direction, vehicle="小客車", pcu=1.0):
    names = {1: "北側", 2: "南側"}
    return {"追蹤編號": track_id, "時間_秒": timestamp, "計數線": line,
            "計數線名稱": names[line], "方向": direction, "車種": vehicle, "PCU": pcu}


class TestLineMovements:
    def test_第一次進入配最後一次離開(self):
        records = [record(1, 1.0, 1, "進入"), record(1, 5.0, 2, "離開")]
        assert build_line_movements(records) == {(1, 2): 1}

    def test_只有進入或只有離開不構成轉向(self):
        records = [record(1, 1.0, 1, "進入"), record(2, 2.0, 2, "離開")]
        assert build_line_movements(records) == {}

    def test_進入之前的離開不採計(self):
        records = [record(1, 1.0, 2, "離開"), record(1, 3.0, 1, "進入")]
        assert build_line_movements(records) == {}

    def test_迴轉記為同一條線進出(self):
        records = [record(1, 1.0, 1, "進入"), record(1, 4.0, 1, "離開")]
        assert build_line_movements(records) == {(1, 1): 1}


class TestLineReportNode:
    def run_report(self, base_config, tmp_path, records):
        node = LineReportNode(base_config, str(tmp_path))
        end = StreamEndElement("test", 10.0)
        end.line_events = records
        end.statistics = {"越線計數": {1: {"名稱": "北側", "進入": 0, "離開": 0},
                                      2: {"名稱": "南側", "進入": 0, "離開": 0}}}
        node.process(end)

        def read(name):
            with open(os.path.join(str(tmp_path), name), encoding="utf-8-sig") as file:
                return list(csv.reader(file))
        return read

    def test_三份報表內容正確(self, base_config, tmp_path):
        read = self.run_report(base_config, tmp_path, [
            record(1, 1.0, 1, "進入"), record(1, 5.0, 2, "離開"),
            record(2, 2.0, 1, "進入", "機車", 0.5),
        ])

        detail = read("越線明細.csv")
        assert len(detail) == 4 and detail[1][1] == "1.0"

        summary = read("越線計數.csv")
        assert ["1", "北側", "進入", "合計", "2", "1.5"] in summary
        assert ["2", "南側", "進入", "合計", "0", "0"] in summary

        matrix = read("越線轉向矩陣.csv")
        assert matrix[0] == ["進入＼離開", "北側", "南側", "合計"]
        assert matrix[1] == ["北側", "0", "1", "1"]
        assert matrix[-1] == ["合計", "0", "1", "1"]

    def test_沒有任何越線也能輸出空報表(self, base_config, tmp_path):
        read = self.run_report(base_config, tmp_path, [])
        assert len(read("越線明細.csv")) == 1
        assert read("越線轉向矩陣.csv")[-1] == ["合計", "0", "0", "0"]

    def test_一般影格只累積不輸出(self, base_config, tmp_path):
        node = LineReportNode(base_config, str(tmp_path))
        element = make_frame(0.0, [])
        element.line_events = [record(1, 1.0, 1, "進入")]
        node.process(element)
        assert not os.path.exists(os.path.join(str(tmp_path), "越線明細.csv"))
        assert len(node._records) == 1


class TestLineRenderNode:
    def test_在成果影格上畫出計數線(self, line_config, lines_file):
        node = LineRenderNode(line_config, load_lines(lines_file)["lines"])
        element = make_frame(0.0, [])
        element.frame_result = np.zeros((400, 200, 3), dtype=np.uint8)
        element.statistics = {"越線計數": {1: {"名稱": "北側", "進入": 3, "離開": 1}}}

        result = node.process(element).frame_result
        assert result.shape == (400, 200, 3)
        # 北側計數線經過此點（線段中點會被文字標籤蓋住，故取靠近端點處）
        assert result[100, 20].any()

    def test_沒有成果影格或結束訊號時原樣回傳(self, line_config, lines_file):
        node = LineRenderNode(line_config, load_lines(lines_file)["lines"])
        element = make_frame(0.0, [])
        assert node.process(element).frame_result is None

        end = StreamEndElement("test", 1.0)
        assert node.process(end) is end
