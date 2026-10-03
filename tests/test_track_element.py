# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：core/track_element.py 的單元測試
功能說明：
    驗證單一車輛軌跡的進出道路判定與車種多數決。
    這是整個系統最核心的邏輯：進出判定錯誤會讓 OD 矩陣全錯，
    車種多數決失準則會讓車種組成與 PCU 失真。

建立日期：2026-10-03
版本號：v1.0.0
"""

import pytest

from core.track_element import TrackElement


class TestObserveZone:
    """進入／離開道路判定。"""

    def test_第一個區域記為進入道路(self):
        track = TrackElement(1, 0.0)
        track.observe_zone(3, 1.0)
        assert track.entry_road == 3
        assert track.entry_timestamp == pytest.approx(1.0)
        assert track.exit_road is None

    def test_之後不同的區域記為離開道路(self):
        track = TrackElement(1, 0.0)
        track.observe_zone(3, 1.0)
        track.observe_zone(1, 5.0)
        assert track.entry_road == 3
        assert track.exit_road == 1
        assert track.exit_timestamp == pytest.approx(5.0)

    def test_重複踩到同一個進入區域不會變成離開(self):
        """車輛在進入區內停留多幀，不該被誤判為已離開。"""
        track = TrackElement(1, 0.0)
        for t in (1.0, 1.1, 1.2, 1.3):
            track.observe_zone(3, t)
        assert track.entry_road == 3
        assert track.exit_road is None

    def test_離開道路只記錄第一次(self):
        """車輛離開後若再踩到第三個區域，離開道路不應被覆寫。"""
        track = TrackElement(1, 0.0)
        track.observe_zone(3, 1.0)
        track.observe_zone(1, 5.0)
        track.observe_zone(2, 9.0)
        assert track.exit_road == 1

    def test_區域為_None_時完全略過(self):
        """車輛行駛在圓環中央（不屬任何區域）時不應改變任何狀態。"""
        track = TrackElement(1, 0.0)
        track.observe_zone(None, 1.0)
        assert track.entry_road is None
        assert track.zone_sequence == []

    def test_區域序列只在切換時累積(self):
        """
        連續踩在同一區域只記一次；中間的 None（圓環中央）不中斷連續性，
        因此 3,3,3,None,3 整段只會留下一個 3。
        """
        track = TrackElement(1, 0.0)
        for zone in (3, 3, 3, None, 3, 1, 1, 2):
            track.observe_zone(zone, 1.0)
        assert track.zone_sequence == [3, 1, 2]

    def test_離開後再回到進入區會記入序列(self):
        """序列用於除錯與人工驗證，往返行為必須看得出來。"""
        track = TrackElement(1, 0.0)
        for zone in (3, 1, 3):
            track.observe_zone(zone, 1.0)
        assert track.zone_sequence == [3, 1, 3]

    def test_has_movement_需同時有進出(self):
        track = TrackElement(1, 0.0)
        assert track.has_movement is False
        track.observe_zone(3, 1.0)
        assert track.has_movement is False
        track.observe_zone(1, 2.0)
        assert track.has_movement is True


class TestVehicleTypeVoting:
    """車種生命週期多數決。"""

    def test_多數決選出票數最高者(self):
        track = TrackElement(1, 0.0)
        for label in ("機車", "機車", "小客車", "機車"):
            track.vote_vehicle_type(label)
        assert track.vehicle_type == "機車"

    def test_None_不計入投票(self):
        """物件被遮擋時該幀沒有偵測框，不應影響車種判定。"""
        track = TrackElement(1, 0.0)
        track.vote_vehicle_type("機車")
        track.vote_vehicle_type(None)
        track.vote_vehicle_type(None)
        assert track.vehicle_type == "機車"
        assert track.vote_count == 1

    def test_空字串不計入投票(self):
        track = TrackElement(1, 0.0)
        track.vote_vehicle_type("")
        assert track.vote_count == 0

    def test_沒有任何票時回傳_None(self):
        assert TrackElement(1, 0.0).vehicle_type is None

    def test_vote_count_等於有效投票數(self):
        track = TrackElement(1, 0.0)
        for label in ("機車", "小客車", None, "機車"):
            track.vote_vehicle_type(label)
        assert track.vote_count == 3


class TestLifetime:
    """存活時間與狀態更新。"""

    def test_存活時間為首末時間差(self):
        track = TrackElement(1, 10.0)
        track.update(15.5)
        assert track.lifetime == pytest.approx(5.5)

    def test_初始存活時間為零(self):
        assert TrackElement(1, 10.0).lifetime == pytest.approx(0.0)

    def test_update_會記錄邊界框(self):
        track = TrackElement(1, 0.0)
        track.update(1.0, [10, 20, 30, 40])
        assert track.last_xyxy == [10, 20, 30, 40]

    def test_update_未給邊界框時保留前值(self):
        track = TrackElement(1, 0.0)
        track.update(1.0, [10, 20, 30, 40])
        track.update(2.0)
        assert track.last_xyxy == [10, 20, 30, 40]


class TestToRecord:
    """報表用紀錄輸出。"""

    def test_完整軌跡的欄位內容(self):
        track = TrackElement(7, 1.0)
        track.observe_zone(3, 2.0)
        track.observe_zone(1, 8.0)
        track.vote_vehicle_type("小客車")
        track.vote_vehicle_type("小客車")
        track.update(10.0)

        record = track.to_record()
        assert record["追蹤編號"] == 7
        assert record["車種"] == "小客車"
        assert record["進入道路"] == 3
        assert record["離開道路"] == 1
        assert record["區域序列"] == "3-1"
        assert record["辨識幀數"] == 2
        assert record["存活秒數"] == pytest.approx(9.0)

    def test_未判定的欄位輸出空字串而非_None(self):
        """CSV 不應出現 None 字樣，空值要以空字串呈現。"""
        record = TrackElement(1, 0.0).to_record()
        assert record["車種"] == ""
        assert record["進入道路"] == ""
        assert record["離開道路"] == ""
        assert record["離開時間_秒"] == ""

    def test_計數旗標預設為未計數(self):
        track = TrackElement(1, 0.0)
        assert track.counted_entry is False
        assert track.counted_movement is False
