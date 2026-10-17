# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：單一路口分析流水線
功能說明：
    把「一個路口」所需的全部節點包成一個物件，供多路口模式重複建立。
    每個路口各自擁有獨立的偵測模型、追蹤器、計數器與輸出資料夾，
    彼此不共用任何狀態，一個路口出問題不會影響其他路口的統計。

    節點的串接順序直接沿用 main.py 的 _run_analysis_chain()，
    確保單路口與多路口模式的分析行為完全一致。

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging
import os

import cv2
from omegaconf import OmegaConf

from core.stream_end_element import StreamEndElement
from main import _run_analysis_chain
from nodes.counting_node import CountingNode
from nodes.detection_tracking_node import DetectionTrackingNode
from nodes.render_node import RenderNode
from nodes.report_node import ReportNode
from nodes.track_update_node import TrackUpdateNode
from nodes.video_reader_node import VideoReaderNode
from pipeline_builder import build_direction_gate, build_extra_nodes

logger = logging.getLogger(__name__)


def render_scale(frame_width: float, display_width: float) -> float:
    """
    計算繪製元素需要放大的倍率。

    高解析度影像放進較小的格子時會被縮小，原尺寸畫上去的文字與線條
    會小到看不清楚，因此先依縮小比例放大，縮小後才會是預期的大小。
    影像不需縮小時回傳 1.0（不縮小字級）。
    """
    if frame_width <= 0 or display_width <= 0:
        return 1.0
    return max(float(frame_width) / float(display_width), 1.0)


def scale_render_config(config, frame_width: float, display_width: float):
    """回傳字級與線寬已依顯示比例放大的設定；不需放大時原樣回傳。"""
    scale = render_scale(frame_width, display_width)
    if scale == 1.0:
        return config

    font_sizes = {
        name: int(round(size * scale)) for name, size in config["render_node"]["font_sizes"].items()
    }
    return OmegaConf.merge(config, {
        "render_node": {
            "font_sizes": font_sizes,
            "box_thickness": int(round(config["render_node"]["box_thickness"] * scale)),
        },
        "line_counting": {
            "line_thickness": int(round(config["line_counting"]["line_thickness"] * scale)),
        },
    })


class CameraPipeline:
    """單一路口的完整分析流水線。"""

    def __init__(self, config, camera: dict, run_dir: str, write_report: bool = True,
                 display_width: float = 0) -> None:
        """
        參數：
            config:        完整設定檔。
            camera:        utils.cctv_source.resolve_camera() 的回傳值。
            run_dir:       此路口專屬的輸出資料夾。
            write_report:  是否輸出報表。
            display_width: 畫面最終顯示的寬度（像素）；大於 0 時依縮小比例放大字級與線寬。
        """
        self.key = camera["key"]
        self.name = camera["name"]
        self.run_dir = run_dir
        os.makedirs(run_dir, exist_ok=True)

        reader_cfg = {key: config["video_reader"][key] for key in config["video_reader"]}
        reader_cfg["src"] = camera["src"]
        reader_cfg["roads_info"] = camera["roads_info"]

        self.reader = VideoReaderNode(reader_cfg)
        config = scale_render_config(
            config, self.reader.stream.get(cv2.CAP_PROP_FRAME_WIDTH), display_width
        )
        self.detector = DetectionTrackingNode(config)
        self.track_updater = TrackUpdateNode(
            config, build_direction_gate(config, camera.get("lines_file"))
        )
        self.counter = CountingNode(config)
        self.renderer = RenderNode(config)
        self.reporter = ReportNode(config, run_dir) if write_report else None
        self.extras = build_extra_nodes(
            config, run_dir, camera.get("lines_file"),
            with_render=True, with_report=write_report,
        )

        self._finished = False

    def _run(self, element):
        return _run_analysis_chain(
            element, self.detector, self.track_updater, self.counter,
            self.renderer, None, self.reporter, self.extras,
        )

    def frames(self):
        """逐幀分析並產生處理後的元素；來源自行結束時會一併完成收尾。"""
        for element in self.reader.process():
            element = self._run(element)
            if isinstance(element, StreamEndElement):
                self._finished = True
            yield element

    def finish(self) -> dict:
        """
        提前結束時的收尾：結算殘留軌跡並輸出報表。

        回傳：
            收尾後的最終統計；已經收尾過則回傳空字典。
        """
        if self._finished:
            return {}
        self._finished = True

        end_element = StreamEndElement(self.reader.source_name, self.reader.last_timestamp)
        return self._run(end_element).statistics

    def release(self) -> None:
        """釋放影像來源。"""
        self.reader.release()
