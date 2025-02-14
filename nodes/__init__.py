# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

套件名稱：nodes（流水線節點）
功能說明：
    每個節點只負責一件事，透過 process(element) 介面串接成處理流水線。
    節點之間僅透過 FrameElement 傳遞資料，彼此不直接呼叫，維持低耦合。

節點清單：
    VideoReaderNode        影像讀取
    DetectionTrackingNode  車輛偵測與追蹤（含車種還原）
    TrackUpdateNode        軌跡狀態維護
    CountingNode           車流計數與轉向統計
    RenderNode             畫面繪製
    ReportNode             統計報表輸出
    VideoWriterNode        成果影片輸出

建立日期：2024-12-20
最後更新：2025-02-14
版本號：v1.0.0
"""

from nodes.counting_node import CountingNode
from nodes.detection_tracking_node import DetectionTrackingNode
from nodes.render_node import RenderNode
from nodes.report_node import ReportNode
from nodes.track_update_node import TrackUpdateNode
from nodes.video_reader_node import VideoReaderNode
from nodes.video_writer_node import VideoWriterNode

__all__ = [
    "VideoReaderNode",
    "DetectionTrackingNode",
    "TrackUpdateNode",
    "CountingNode",
    "RenderNode",
    "ReportNode",
    "VideoWriterNode",
]
