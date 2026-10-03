# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：core/frame_element.py 與 core/stream_end_element.py 的單元測試
功能說明：
    這兩個類別是流水線的資料契約。欄位缺漏或預設值不對，
    下游節點就會在存取時拋出 AttributeError，因此需逐一確認。

建立日期：2026-10-03
版本號：v1.0.0
"""

import numpy as np

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement


class TestFrameElement:
    """單幀資料容器。"""

    def make(self):
        return FrameElement(
            source="影片.mp4",
            frame=np.zeros((20, 30, 3), dtype=np.uint8),
            timestamp=1.5,
            frame_num=7,
            roads_info={"1": [0, 0, 1, 1, 2, 2]},
            total_frames=100,
        )

    def test_來源資訊正確保存(self):
        element = self.make()
        assert element.source == "影片.mp4"
        assert element.timestamp == 1.5
        assert element.frame_num == 7
        assert element.total_frames == 100
        assert element.frame.shape == (20, 30, 3)

    def test_時間與幀號會轉型(self):
        """設定檔或 cv2 可能傳入字串或浮點數，建構時應統一型別。"""
        element = FrameElement("x", np.zeros((1, 1, 3)), "2.5", "3", {})
        assert isinstance(element.timestamp, float)
        assert isinstance(element.frame_num, int)

    def test_偵測與追蹤欄位預設為空串列(self):
        element = self.make()
        for field in ("detected_conf", "detected_cls", "detected_xyxy",
                      "tracked_ids", "tracked_conf", "tracked_cls", "tracked_xyxy"):
            assert getattr(element, field) == []

    def test_統計欄位預設為空容器(self):
        element = self.make()
        assert element.active_tracks == {}
        assert element.retired_tracks == []
        assert element.count_events == []
        assert element.statistics == {}

    def test_成果影格預設為_None(self):
        assert self.make().frame_result is None

    def test_total_frames_可省略(self):
        """串流來源取不到總幀數時應為 0，不得缺少此欄位。"""
        element = FrameElement("x", np.zeros((1, 1, 3)), 0.0, 1, {})
        assert element.total_frames == 0


class TestStreamEndElement:
    """串流結束訊號。"""

    def test_基本欄位(self):
        end = StreamEndElement("影片.mp4", 66.8, 1591)
        assert end.source == "影片.mp4"
        assert end.timestamp == 66.8
        assert end.frame_num == 1591

    def test_保留與_FrameElement_同名的統計欄位(self):
        """
        收尾路徑（軌跡清空 → 計數 → 報表）直接沿用同一組欄位名稱，
        下游節點才不需要為結束訊號寫特例分支。
        """
        end = StreamEndElement("x", 0.0)
        assert end.active_tracks == {}
        assert end.retired_tracks == []
        assert end.count_events == []
        assert end.statistics == {}

    def test_幀號可省略(self):
        assert StreamEndElement("x", 1.0).frame_num == 0
