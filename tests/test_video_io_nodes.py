# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：影像讀取與影片輸出節點的單元測試
功能說明：
    以 cv2 即時合成一段極短的測試影片，驗證讀取、時間戳、抽幀與輸出。
    不依賴 repo 內的示範影片（該影片不隨儲存庫散布），
    因此這些測試在任何乾淨 clone 上都能執行。

建立日期：2026-10-03
版本號：v1.0.0
"""

import json
import os

import cv2
import numpy as np
import pytest

from core.frame_element import FrameElement
from core.stream_end_element import StreamEndElement
from nodes.video_reader_node import VideoReaderNode
from nodes.video_writer_node import VideoWriterNode


@pytest.fixture
def tiny_video(tmp_path):
    """合成一段 10 幀、64x48、10 fps 的測試影片。"""
    path = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(10):
        frame = np.full((48, 64, 3), i * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return str(path)


@pytest.fixture
def roads_file(tmp_path, square_roads):
    path = tmp_path / "roads.json"
    path.write_text(json.dumps(square_roads), encoding="utf-8")
    return str(path)


def reader_config(video, roads, skip=0):
    return {"src": video, "roads_info": roads, "skip_secs": skip}


class TestVideoReaderNode:
    """影像讀取。"""

    def test_讀出所有影格並以結束訊號收尾(self, tiny_video, roads_file):
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        elements = list(node.process())

        frames = [e for e in elements if isinstance(e, FrameElement)]
        assert len(frames) == 10
        assert isinstance(elements[-1], StreamEndElement)

    def test_影格編號由一開始遞增(self, tiny_video, roads_file):
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        frames = [e for e in node.process() if isinstance(e, FrameElement)]
        assert [f.frame_num for f in frames] == list(range(1, 11))

    def test_時間戳單調遞增且非負(self, tiny_video, roads_file):
        """首幀負時間曾造成報表出現負值，此處確認已修正。"""
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        stamps = [e.timestamp for e in node.process() if isinstance(e, FrameElement)]

        assert stamps[0] >= 0.0
        assert all(b > a for a, b in zip(stamps, stamps[1:]))

    def test_載入道路區域設定(self, tiny_video, roads_file):
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        assert set(node.roads_info.keys()) == {"1", "2", "3"}

    def test_總幀數可取得(self, tiny_video, roads_file):
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        assert node.total_frames == 10

    def test_抽幀會減少影格數(self, tiny_video, roads_file):
        """影片 1 秒長，每 0.3 秒取一幀應明顯少於 10 幀。"""
        node = VideoReaderNode(reader_config(tiny_video, roads_file, skip=0.3))
        frames = [e for e in node.process() if isinstance(e, FrameElement)]
        assert 0 < len(frames) < 10

    def test_影片不存在時拋出明確例外(self, roads_file):
        with pytest.raises(FileNotFoundError, match="找不到影片檔案"):
            VideoReaderNode(reader_config("不存在的影片.mp4", roads_file))

    def test_區域設定檔不存在時拋出明確例外(self, tiny_video):
        with pytest.raises(FileNotFoundError, match="找不到道路區域設定檔"):
            VideoReaderNode(reader_config(tiny_video, "不存在.json"))

    def test_last_timestamp_在讀取前為零(self, tiny_video, roads_file):
        """內部初始值為 -1，對外必須夾為 0 以免下游算出負的時間長度。"""
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        assert node.last_timestamp == 0.0

    def test_release_可重複呼叫(self, tiny_video, roads_file):
        node = VideoReaderNode(reader_config(tiny_video, roads_file))
        node.release()
        node.release()


class TestVideoWriterNode:
    """成果影片輸出。"""

    def writer_config(self):
        return {"fps": 10.0, "fourcc": "mp4v"}

    def make_frame(self, width=64, height=48, with_result=True):
        element = FrameElement(
            source="test",
            frame=np.zeros((height, width, 3), dtype=np.uint8),
            timestamp=0.0,
            frame_num=1,
            roads_info={},
        )
        if with_result:
            element.frame_result = np.full((height, width, 3), 128, dtype=np.uint8)
        return element

    def test_寫出影片檔(self, tmp_path):
        node = VideoWriterNode(self.writer_config(), str(tmp_path / "run"))
        for _ in range(5):
            node.process(self.make_frame())
        node.release()

        assert os.path.isfile(node.output_path)
        assert os.path.getsize(node.output_path) > 0

    def test_檔名固定為分析結果(self, tmp_path):
        node = VideoWriterNode(self.writer_config(), str(tmp_path / "run"))
        assert node.output_path.endswith("分析結果.mp4")

    def test_沒有成果影格時改寫原始影格(self, tmp_path):
        """繪製節點被停用時仍要能輸出，不得崩潰。"""
        node = VideoWriterNode(self.writer_config(), str(tmp_path / "run"))
        node.process(self.make_frame(with_result=False))
        node.release()
        assert os.path.isfile(node.output_path)

    def test_收到結束訊號會關檔(self, tmp_path):
        node = VideoWriterNode(self.writer_config(), str(tmp_path / "run"))
        node.process(self.make_frame())
        node.process(StreamEndElement("test", 1.0))
        assert node._writer is None

    def test_release_可重複呼叫(self, tmp_path):
        node = VideoWriterNode(self.writer_config(), str(tmp_path / "run"))
        node.process(self.make_frame())
        node.release()
        node.release()
