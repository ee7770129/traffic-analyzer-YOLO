# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：流水線擴充節點組裝
功能說明：
    v1.2.0 新增的節點（越線計數、熱力圖、尖峰小時係數）皆可個別開關。
    本模組依設定決定要建立哪些節點，並回傳影像來源的最終設定，
    讓 main.py 維持「只負責串接」的單純角色。

    回傳的三組節點對應主流程中的三個插入位置：
        analysis：計數之後、繪製之前（需要軌跡與統計）
        render：  RenderNode 之後（在成果影格上加畫）
        report：  ReportNode 之後（輸出檔案）

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging

from nodes.heatmap_node import HeatmapNode
from nodes.line_counting_node import LineCountingNode, load_lines
from nodes.line_render_node import LineRenderNode
from nodes.line_report_node import LineReportNode
from nodes.phf_report_node import PhfReportNode
from utils.cctv_source import load_catalog, resolve_camera
from utils.direction_gate import DirectionGate

logger = logging.getLogger(__name__)


def resolve_reader_config(config) -> tuple:
    """
    決定影像讀取節點實際使用的設定。

    指定路口預設組時，以目錄檔中的串流網址與區域座標取代 video_reader 的對應項目。

    回傳：
        (讀取節點設定字典, 計數線設定檔路徑或 None, 來源顯示名稱)
    """
    reader_cfg = {key: config["video_reader"][key] for key in config["video_reader"]}
    lines_file = config["line_counting"].get("lines_file")
    camera_key = config["cctv"].get("camera")

    if not camera_key:
        return reader_cfg, lines_file, str(reader_cfg["src"])

    camera = resolve_camera(str(camera_key), load_catalog(str(config["cctv"]["catalog"])))
    reader_cfg["src"] = camera["src"]
    reader_cfg["roads_info"] = camera["roads_info"]

    # 命令列或 .env 明確指定的計數線檔優先於目錄檔
    return reader_cfg, lines_file or camera["lines_file"], camera["name"]


def build_direction_gate(config, lines_file):
    """
    建立進入方向判定器。

    需要路口內側的參考點才能判定方向，該點記錄在計數線設定檔中，
    因此沒有計數線設定檔、或設定檔關閉此功能時回傳 None（沿用原規則）。
    """
    general_cfg = config["general"]
    if not lines_file or not bool(general_cfg.get("direction_aware_entry", False)):
        return None

    inside_point = load_lines(str(lines_file))["inside_point"]
    return DirectionGate(inside_point, float(general_cfg.get("direction_min_move_px", 12)))


def build_extra_nodes(config, run_dir: str, lines_file, with_render: bool, with_report: bool) -> dict:
    """
    依設定建立擴充節點。

    參數：
        lines_file:  計數線設定檔路徑；為 None 時不建立越線相關節點。
        with_render: 主流程是否啟用繪製（預覽或存檔）。
        with_report: 主流程是否輸出報表。
    """
    analysis, render, report = [], [], []

    if bool(config["line_counting"]["enabled"]) and lines_file:
        line_counter = LineCountingNode(config, str(lines_file))
        analysis.append(line_counter)
        if with_render:
            render.append(LineRenderNode(config, line_counter.lines))
        if with_report:
            report.append(LineReportNode(config, run_dir))
    else:
        logger.info("未指定計數線設定檔，越線計數停用。")

    if with_report and bool(config["heatmap_node"]["enabled"]):
        report.append(HeatmapNode(config["heatmap_node"], run_dir))

    if with_report and bool(config["phf_node"]["enabled"]):
        report.append(PhfReportNode(config, run_dir))

    return {"analysis": analysis, "render": render, "report": report}
