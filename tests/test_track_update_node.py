# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：nodes/track_update_node.py 的單元測試
功能說明：
    驗證軌跡生命週期管理：建立、更新、區域判定、離場結算。
    離場判定若出錯，車輛會被重複建立（重複計數）或永不結算（漏計），
    兩者都會直接破壞統計數字。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from nodes.track_update_node import TrackUpdateNode


def make_frame(timestamp, roads_info, ids, boxes, labels=None):
    """建立含追蹤結果的 FrameElement。"""
    element = FrameElement(
        source="test",
        frame=np.zeros((400, 400, 3), dtype=np.uint8),
        timestamp=timestamp,
        frame_num=1,
        roads_info=roads_info,
    )
    element.tracked_ids = ids
    element.tracked_xyxy = boxes
    element.tracked_cls = labels if labels is not None else ["小客車"] * len(ids)
    return element


# 中心點落在區域 1（0,0)~(100,100) 內的邊界框
BOX_ZONE1 = [40, 40, 60, 60]
# 中心點落在區域 2（200,0)~(300,100) 內
BOX_ZONE2 = [240, 40, 260, 60]
# 中心點不在任何區域
BOX_OUTSIDE = [350, 350, 370, 370]


class TestTrackCreation:
    """軌跡建立與更新。"""

    def test_首次出現會建立軌跡(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        element = node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))

        assert 7 in element.active_tracks
        assert element.active_tracks[7].track_id == 7

    def test_同一編號再次出現不會重建(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        first = node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        track_obj = first.active_tracks[7]
        second = node.process(make_frame(1.5, square_roads, [7], [BOX_ZONE1]))

        assert second.active_tracks[7] is track_obj
        assert track_obj.timestamp_first == pytest.approx(1.0)
        assert track_obj.timestamp_last == pytest.approx(1.5)

    def test_車種投票被累積(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1], ["機車"]))
        element = node.process(make_frame(1.5, square_roads, [7], [BOX_ZONE1], ["機車"]))

        assert element.active_tracks[7].vehicle_type == "機車"
        assert element.active_tracks[7].vote_count == 2

    def test_車種為_None_時不投票(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        element = node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1], [None]))
        assert element.active_tracks[7].vote_count == 0


class TestZoneDetection:
    """區域判定與進出道路推導。"""

    def test_進入道路由第一個區域決定(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        element = node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        assert element.active_tracks[7].entry_road == 1

    def test_之後不同區域成為離開道路(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        element = node.process(make_frame(2.0, square_roads, [7], [BOX_ZONE2]))

        track = element.active_tracks[7]
        assert track.entry_road == 1
        assert track.exit_road == 2

    def test_不在任何區域時不影響判定(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        element = node.process(make_frame(1.0, square_roads, [7], [BOX_OUTSIDE]))
        assert element.active_tracks[7].entry_road is None


class TestRetirement:
    """離場判定。"""

    def test_超過逾時未出現即判定離場(self, base_config, square_roads):
        """track_timeout_secs 為 2.0 秒。"""
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        element = node.process(make_frame(5.0, square_roads, [], []))

        assert len(element.retired_tracks) == 1
        assert element.retired_tracks[0].track_id == 7

    def test_未逾時不會被判定離場(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        element = node.process(make_frame(2.0, square_roads, [], []))

        assert element.retired_tracks == []

    def test_離場後不會重複交付(self, base_config, square_roads):
        """同一條軌跡只能被結算一次，否則會重複計數。"""
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        first = node.process(make_frame(5.0, square_roads, [], []))
        second = node.process(make_frame(6.0, square_roads, [], []))

        assert len(first.retired_tracks) == 1
        assert second.retired_tracks == []


class TestStreamEnd:
    """影片結束時的收尾。"""

    def test_結束時一次清空所有殘留軌跡(self, base_config, square_roads):
        """尾端仍在畫面上的車輛必須被交付結算，否則會漏計。"""
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7, 8, 9],
                                [BOX_ZONE1, BOX_ZONE2, BOX_OUTSIDE]))

        end = node.process(StreamEndElement("test", 10.0))
        assert len(end.retired_tracks) == 3

    def test_清空後內部不再保留軌跡(self, base_config, square_roads):
        node = TrackUpdateNode(base_config)
        node.process(make_frame(1.0, square_roads, [7], [BOX_ZONE1]))
        node.process(StreamEndElement("test", 10.0))
        second = node.process(StreamEndElement("test", 11.0))

        assert second.retired_tracks == []
