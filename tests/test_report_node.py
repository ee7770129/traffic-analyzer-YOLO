# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：nodes/report_node.py 的單元測試
功能說明：
    驗證四份 CSV 報表的內容與編碼。報表是整個系統的最終產出，
    編碼錯誤會讓 Excel 顯示亂碼，數字錯誤則直接影響分析結論。

    四份報表一律由「已離場的軌跡紀錄」推導，因此測試也以軌跡為輸入，
    並特別驗證「四份報表數字必定一致」這項保證。

建立日期：2026-10-03
版本號：v1.1.0
"""

import csv
import os

import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from nodes.report_node import ReportNode


def make_track(track_id, road, vehicle_type="小客車", entry_time=10.0,
               counted=True, exit_road=None):
    """建立一條已結算的軌跡。"""
    track = TrackElement(track_id, entry_time)
    track.observe_zone(road, entry_time)
    if exit_road is not None:
        track.observe_zone(exit_road, entry_time + 5.0)
    for _ in range(5):
        track.vote_vehicle_type(vehicle_type)
    track.update(entry_time + 8.0)
    track.counted_entry = counted
    if counted:
        track.counted_vehicle_type = vehicle_type
        track.counted_movement = exit_road is not None
    return track


def make_frame(timestamp, retired=None):
    element = FrameElement(
        source="test",
        frame=np.zeros((10, 10, 3), dtype=np.uint8),
        timestamp=timestamp,
        frame_num=1,
        roads_info={},
    )
    element.retired_tracks = retired or []
    return element


def read_csv(path):
    """以 utf-8-sig 讀回報表，BOM 會被自動去除。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def report(base_config, tmp_path):
    return ReportNode(base_config, str(tmp_path / "run"))


class TestOutputFiles:
    """輸出檔案與編碼。"""

    def test_輸出四份報表(self, report):
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.finalize()

        for name in ("車輛明細.csv", "時段流量.csv", "轉向矩陣.csv", "統計總表.csv"):
            assert os.path.isfile(os.path.join(report.run_dir, name))

    def test_編碼含_BOM(self, report):
        """Excel 需要 BOM 才會正確判讀 UTF-8，否則中文變亂碼。"""
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.finalize()

        with open(os.path.join(report.run_dir, "統計總表.csv"), "rb") as f:
            assert f.read(3) == b"\xef\xbb\xbf"

    def test_中文欄位可正確讀回(self, report):
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.finalize()
        assert "小客車" in read_csv(os.path.join(report.run_dir, "統計總表.csv"))[0]

    def test_收到結束訊號時自動輸出(self, report):
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.process(StreamEndElement("test", 30.0))
        assert os.path.isfile(os.path.join(report.run_dir, "統計總表.csv"))

    def test_不會重複輸出(self, report):
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.process(StreamEndElement("test", 30.0))
        assert report._finalized is True


class TestVehicleDetails:
    """車輛明細——人工核對的依據。"""

    def test_每台離場車輛一列(self, report):
        report.process(make_frame(20.0, [make_track(i, 1) for i in range(3)]))
        report.finalize()
        assert len(read_csv(os.path.join(report.run_dir, "車輛明細.csv"))) == 3

    def test_標示是否計入統計(self, report):
        report.process(make_frame(20.0, [
            make_track(1, 1, counted=True),
            make_track(2, 1, counted=False),
        ]))
        report.finalize()

        rows = {int(r["追蹤編號"]): r["是否計入統計"] for r in
                read_csv(os.path.join(report.run_dir, "車輛明細.csv"))}
        assert rows[1] == "是"
        assert rows[2] == "否"

    def test_未計入者不進入統計母體(self, report):
        """明細會列出所有軌跡，但統計只能採計通過門檻的。"""
        report.process(make_frame(20.0, [
            make_track(1, 1, counted=True),
            make_track(2, 1, counted=False),
        ]))
        report.finalize()

        total = [r for r in read_csv(os.path.join(report.run_dir, "統計總表.csv"))
                 if r["道路"] == "全部合計"][0]
        assert total["車次合計"] == "1"

    def test_依追蹤編號排序(self, report):
        report.process(make_frame(20.0, [make_track(i, 1) for i in (5, 1, 3)]))
        report.finalize()

        ids = [int(r["追蹤編號"]) for r in
               read_csv(os.path.join(report.run_dir, "車輛明細.csv"))]
        assert ids == sorted(ids)


class TestIntervalFlow:
    """時段流量。"""

    def test_依進入時間分桶(self, report):
        """interval_seconds 為 60，兩台車應落在不同區間。"""
        report.process(make_frame(100.0, [
            make_track(1, 1, entry_time=30.0),
            make_track(2, 1, entry_time=90.0),
        ]))
        report.finalize()

        rows = read_csv(os.path.join(report.run_dir, "時段流量.csv"))
        bucket0 = [r for r in rows if r["時段起_秒"] == "0.0" and r["道路"] == "1"][0]
        bucket1 = [r for r in rows if r["時段起_秒"] == "60.0" and r["道路"] == "1"][0]
        assert bucket0["小計"] == "1"
        assert bucket1["小計"] == "1"

    def test_PCU_小計依車種換算(self, report):
        report.process(make_frame(20.0, [
            make_track(1, 1, "機車"),      # 0.5
            make_track(2, 1, "大客車"),    # 2.0
        ]))
        report.finalize()

        row = [r for r in read_csv(os.path.join(report.run_dir, "時段流量.csv"))
               if r["道路"] == "1"][0]
        assert float(row["PCU小計"]) == pytest.approx(2.5)


class TestOdMatrix:
    """轉向矩陣。"""

    def test_矩陣數值與合計(self, report):
        report.process(make_frame(20.0, [
            make_track(1, 1, exit_road=2),
            make_track(2, 2, exit_road=1),
        ]))
        report.finalize()

        rows = read_csv(os.path.join(report.run_dir, "轉向矩陣.csv"))
        row1 = [r for r in rows if r["進入道路＼離開道路"] == "道路1"][0]
        assert row1["往道路2"] == "1"
        assert row1["合計"] == "1"
        assert rows[-1]["進入道路＼離開道路"] == "合計"
        assert rows[-1]["合計"] == "2"

    def test_只有進入道路者不列入轉向(self, report):
        report.process(make_frame(20.0, [make_track(1, 1)]))
        report.finalize()
        assert read_csv(os.path.join(report.run_dir, "轉向矩陣.csv"))[-1]["合計"] == "0"


class TestSummary:
    """統計總表。"""

    def test_各道路車次與合計(self, report):
        report.process(make_frame(20.0, [
            make_track(1, 1), make_track(2, 1), make_track(3, 2),
        ]))
        report.finalize()

        rows = read_csv(os.path.join(report.run_dir, "統計總表.csv"))
        by_road = {r["道路"]: r for r in rows if r["道路"].startswith("道路")}
        assert by_road["道路1"]["車次合計"] == "2"
        assert by_road["道路2"]["車次合計"] == "1"
        assert [r for r in rows if r["道路"] == "全部合計"][0]["車次合計"] == "3"

    def test_組成佔比加總為百分之百(self, report):
        report.process(make_frame(20.0, [make_track(1, 1), make_track(2, 2)]))
        report.finalize()

        shares = [float(r["組成佔比"].rstrip("%")) for r in
                  read_csv(os.path.join(report.run_dir, "統計總表.csv"))
                  if r["道路"].startswith("道路")]
        assert sum(shares) == pytest.approx(100.0, abs=0.2)

    def test_無車輛時不會除以零(self, report):
        """空影片或全部被濾除時，報表仍要能產生而不崩潰。"""
        report.process(make_frame(20.0))
        report.finalize()

        total = [r for r in read_csv(os.path.join(report.run_dir, "統計總表.csv"))
                 if r["道路"] == "全部合計"][0]
        assert total["車次合計"] == "0"
        assert total["組成佔比"] == "0.0%"


class TestConsistency:
    """四份報表的一致性保證——這是本節點最重要的契約。"""

    @pytest.fixture
    def filled(self, report):
        tracks = [
            make_track(1, 1, "小客車", entry_time=10.0, exit_road=2),
            make_track(2, 1, "機車", entry_time=20.0),
            make_track(3, 2, "小客車", entry_time=70.0, exit_road=1),
            make_track(4, 3, "大貨車", entry_time=80.0),
            make_track(5, 3, "小客車", entry_time=90.0, counted=False),
        ]
        report.process(make_frame(120.0, tracks))
        report.finalize()
        return report

    def test_時段流量加總等於統計總表(self, filled):
        interval_total = sum(int(r["小計"]) for r in
                             read_csv(os.path.join(filled.run_dir, "時段流量.csv")))
        summary = [r for r in read_csv(os.path.join(filled.run_dir, "統計總表.csv"))
                   if r["道路"] == "全部合計"][0]
        assert interval_total == int(summary["車次合計"]) == 4

    def test_車輛明細計入數等於統計總表(self, filled):
        counted = sum(1 for r in read_csv(os.path.join(filled.run_dir, "車輛明細.csv"))
                      if r["是否計入統計"] == "是")
        summary = [r for r in read_csv(os.path.join(filled.run_dir, "統計總表.csv"))
                   if r["道路"] == "全部合計"][0]
        assert counted == int(summary["車次合計"])

    def test_車種分布一致(self, filled):
        """明細的車種分布必須與總表逐欄相符，不能各自採用不同版本的判定。"""
        from collections import Counter
        detail = Counter(r["車種"] for r in
                         read_csv(os.path.join(filled.run_dir, "車輛明細.csv"))
                         if r["是否計入統計"] == "是")
        summary = [r for r in read_csv(os.path.join(filled.run_dir, "統計總表.csv"))
                   if r["道路"] == "全部合計"][0]

        for label, count in detail.items():
            assert int(summary[label]) == count

    def test_轉向筆數不大於累計車次(self, filled):
        od_total = int(read_csv(os.path.join(filled.run_dir, "轉向矩陣.csv"))[-1]["合計"])
        summary = [r for r in read_csv(os.path.join(filled.run_dir, "統計總表.csv"))
                   if r["道路"] == "全部合計"][0]
        assert od_total <= int(summary["車次合計"])
