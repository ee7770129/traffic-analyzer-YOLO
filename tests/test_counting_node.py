# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：nodes/counting_node.py 的單元測試
功能說明：
    驗證精確累計計數與轉向 OD 矩陣。本節點是本專案相對參考專案
    最核心的改良，其正確性直接決定輸出數據能不能用。

    重點驗證三件事：
        1. 門檻過濾：未達存活時間或辨識幀數的軌跡不得計入。
        2. 去重保證：同一台車無論被處理幾次都只能計一次。
        3. 母體一致：轉向統計只來自已計入進入流量的車輛。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from core.track_element import TrackElement
from nodes.counting_node import CountingNode


def make_frame(timestamp, roads_info, active=None, retired=None):
    """建立一個僅含測試所需欄位的 FrameElement。"""
    element = FrameElement(
        source="test",
        frame=np.zeros((10, 10, 3), dtype=np.uint8),
        timestamp=timestamp,
        frame_num=1,
        roads_info=roads_info,
    )
    element.active_tracks = active or {}
    element.retired_tracks = retired or []
    return element


def make_track(track_id, entry=None, exit_=None, votes=3, label="小客車", lifetime=5.0):
    """建立一條已達指定狀態的軌跡。"""
    track = TrackElement(track_id, 0.0)
    if entry is not None:
        track.observe_zone(entry, 0.5)
    if exit_ is not None:
        track.observe_zone(exit_, 1.5)
    for _ in range(votes):
        track.vote_vehicle_type(label)
    track.update(lifetime)
    return track


class TestEntryCounting:
    """進入流量計數與門檻過濾。"""

    def test_符合門檻的軌跡被計入(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=2)
        element = node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.total_vehicles == 1
        assert node.entry_counts[2]["小客車"] == 1
        assert track.counted_entry is True
        assert len(element.count_events) == 1

    def test_存活時間不足不計入(self, base_config, square_roads):
        """min_track_life_secs 為 1.0，存活 0.5 秒的軌跡應被濾除。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=2, lifetime=0.5)
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.total_vehicles == 0
        assert track.counted_entry is False

    def test_辨識幀數不足不計入(self, base_config, square_roads):
        """min_vote_count 為 2，只有 1 票的破碎軌跡應被濾除。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=2, votes=1)
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.total_vehicles == 0

    def test_沒有進入道路不計入(self, base_config, square_roads):
        """停在圓環中央、從未踩進任何區域的車不應被計入。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=None)
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.total_vehicles == 0

    def test_同一台車重複處理只計一次(self, base_config, square_roads):
        """這是統計可重現的關鍵保證。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=2)
        for t in (5.0, 5.1, 5.2, 5.3):
            node.process(make_frame(t, square_roads, active={1: track}))

        assert node.total_vehicles == 1

    def test_離場軌跡也會被結算(self, base_config, square_roads):
        """車輛離開畫面時是最後的計數機會，不能漏。"""
        node = CountingNode(base_config)
        track = make_track(9, entry=3)
        node.process(make_frame(5.0, square_roads, retired=[track]))

        assert node.total_vehicles == 1
        assert node.entry_counts[3]["小客車"] == 1


class TestPcuAccumulation:
    """PCU 小客車當量累計。"""

    def test_依車種換算當量(self, base_config, square_roads):
        node = CountingNode(base_config)
        tracks = {
            1: make_track(1, entry=1, label="小客車"),   # 1.0
            2: make_track(2, entry=1, label="機車"),     # 0.5
            3: make_track(3, entry=2, label="大客車"),   # 2.0
        }
        node.process(make_frame(5.0, square_roads, active=tracks))

        assert node.total_vehicles == 3
        assert node.total_pcu == pytest.approx(3.5)

    def test_未知車種使用預設當量(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=1, votes=0)  # 沒有任何車種投票
        track.vote_vehicle_type("小客車")
        track.vote_vehicle_type("小客車")
        node.process(make_frame(5.0, square_roads, active={1: track}))
        assert node.total_pcu == pytest.approx(1.0)


class TestMovementCounting:
    """轉向 OD 矩陣。"""

    def test_有完整進出時計入_OD(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=3, exit_=1)
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.od_matrix[(3, 1)] == 1
        assert track.counted_movement is True

    def test_只有進入道路時不計入_OD(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=3)
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert sum(node.od_matrix.values()) == 0

    def test_未計入進入流量者不計_OD(self, base_config, square_roads):
        """母體必須一致：沒被計為進入的車，也不能出現在轉向統計裡。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=3, exit_=1, lifetime=0.3)  # 存活不足
        node.process(make_frame(5.0, square_roads, active={1: track}))

        assert node.total_vehicles == 0
        assert sum(node.od_matrix.values()) == 0

    def test_OD_只計一次(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=3, exit_=1)
        for t in (5.0, 5.1, 5.2):
            node.process(make_frame(t, square_roads, active={1: track}))

        assert node.od_matrix[(3, 1)] == 1

    def test_轉向筆數必然不大於累計車次(self, base_config, square_roads):
        node = CountingNode(base_config)
        tracks = {
            1: make_track(1, entry=1, exit_=2),
            2: make_track(2, entry=2),
            3: make_track(3, entry=3),
        }
        element = node.process(make_frame(5.0, square_roads, active=tracks))
        stats = element.statistics
        assert stats["轉向筆數"] <= stats["累計車次"]


class TestStatistics:
    """統計輸出內容。"""

    def test_統計欄位齊全(self, base_config, square_roads):
        node = CountingNode(base_config)
        element = node.process(make_frame(5.0, square_roads, active={1: make_track(1, entry=1)}))
        stats = element.statistics

        for key in ("累計車次", "累計PCU", "各道路累計", "各道路流率",
                    "車種組成", "轉向筆數", "畫面車輛數", "流率視窗秒"):
            assert key in stats

    def test_各道路累計涵蓋所有設定的道路(self, base_config, square_roads):
        """即使某條路一台車都沒有，也要出現在統計中並為 0。"""
        node = CountingNode(base_config)
        element = node.process(make_frame(5.0, square_roads, active={1: make_track(1, entry=1)}))

        assert set(element.statistics["各道路累計"].keys()) == {1, 2, 3}
        assert element.statistics["各道路累計"][2] == 0

    def test_畫面車輛數等於作用中軌跡數(self, base_config, square_roads):
        node = CountingNode(base_config)
        tracks = {i: make_track(i, entry=1) for i in range(1, 5)}
        element = node.process(make_frame(5.0, square_roads, active=tracks))
        assert element.statistics["畫面車輛數"] == 4

    def test_流率依視窗換算為每分鐘(self, base_config, square_roads):
        """視窗 60 秒內有 2 筆進入事件，流率應為 2 輛/分。"""
        node = CountingNode(base_config)
        tracks = {1: make_track(1, entry=1), 2: make_track(2, entry=1)}
        element = node.process(make_frame(5.0, square_roads, active=tracks))
        assert element.statistics["各道路流率"][1] == pytest.approx(2.0)

    def test_視窗外的舊事件會被移除(self, base_config, square_roads):
        node = CountingNode(base_config)
        node.process(make_frame(5.0, square_roads, active={1: make_track(1, entry=1)}))
        # 時間推進到遠超過 60 秒的視窗之外
        element = node.process(make_frame(500.0, square_roads))
        assert element.statistics["各道路流率"][1] == pytest.approx(0.0)
        # 但累計值不受影響
        assert element.statistics["累計車次"] == 1


class TestVehicleTypeReconciliation:
    """車種修正——離場時以最完整的票數回頭修正統計。"""

    def test_離場時以最終多數決修正車種(self, base_config, square_roads):
        """
        計數發生在票數還少的時候。若之後票數翻轉了多數決結果，
        統計必須跟著修正，否則總表採用的會是最不可靠的判定。
        """
        node = CountingNode(base_config)
        track = make_track(1, entry=1, votes=2, label="小客車")

        # 先以「小客車」計入
        node.process(make_frame(5.0, square_roads, active={1: track}))
        assert node.entry_counts[1]["小客車"] == 1
        assert track.counted_vehicle_type == "小客車"

        # 之後累積大量「大貨車」票數，多數決翻轉
        for _ in range(50):
            track.vote_vehicle_type("大貨車")
        node.process(make_frame(9.0, square_roads, retired=[track]))

        assert node.entry_counts[1].get("小客車", 0) == 0
        assert node.entry_counts[1]["大貨車"] == 1
        assert track.counted_vehicle_type == "大貨車"

    def test_修正時_PCU_一併調整(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=1, votes=2, label="機車")  # PCU 0.5
        node.process(make_frame(5.0, square_roads, active={1: track}))
        assert node.total_pcu == pytest.approx(0.5)

        for _ in range(50):
            track.vote_vehicle_type("大客車")  # PCU 2.0
        node.process(make_frame(9.0, square_roads, retired=[track]))
        assert node.total_pcu == pytest.approx(2.0)

    def test_車種未變時不產生修正(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=1, label="小客車")
        node.process(make_frame(5.0, square_roads, active={1: track}))
        element = node.process(make_frame(9.0, square_roads, retired=[track]))

        assert not [e for e in element.count_events if e["事件"] == "車種修正"]

    def test_修正不改變總車次(self, base_config, square_roads):
        """修正的是分類，不是數量。"""
        node = CountingNode(base_config)
        track = make_track(1, entry=1, votes=2, label="小客車")
        node.process(make_frame(5.0, square_roads, active={1: track}))
        for _ in range(50):
            track.vote_vehicle_type("大貨車")
        node.process(make_frame(9.0, square_roads, retired=[track]))

        assert node.total_vehicles == 1

    def test_未計入統計者不做修正(self, base_config, square_roads):
        node = CountingNode(base_config)
        track = make_track(1, entry=1, lifetime=0.2)  # 未達門檻
        element = node.process(make_frame(5.0, square_roads, retired=[track]))

        assert node.total_vehicles == 0
        assert not [e for e in element.count_events if e["事件"] == "車種修正"]


class TestStreamEnd:
    """影片結束時的收尾結算。"""

    def test_結束訊號仍會結算殘留軌跡(self, base_config, square_roads):
        node = CountingNode(base_config)
        node.process(make_frame(1.0, square_roads))  # 先讓節點取得道路清單

        end = StreamEndElement("test", 60.0)
        end.retired_tracks = [make_track(1, entry=1), make_track(2, entry=2)]
        result = node.process(end)

        assert node.total_vehicles == 2
        assert result.statistics["累計車次"] == 2
