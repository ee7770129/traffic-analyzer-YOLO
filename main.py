# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：路口車流分析主程式
功能說明：
    組裝並執行分析流水線，本檔只負責「串接節點」與「流程控制」，
    所有業務邏輯皆位於各自的節點模組中。

流水線順序：
    影像讀取 → 偵測追蹤 → 軌跡維護 → 車流計數 → 畫面繪製 → 影片輸出 → 報表輸出

使用方式：
    python main.py                                   以預設設定執行
    python main.py pipeline.save_video=true          輸出成果影片
    python main.py video_reader.src=my_video.mp4     指定其他影片
    python main.py pipeline.show_window=false        關閉預覽視窗（批次處理用）
    python main.py hydra.job_logging.root.level=DEBUG  觀察各節點耗時

建立日期：2024-12-18
版本號：v1.0.0
"""

import logging
import os
from datetime import datetime

import cv2
import hydra

# 先載入 .env，讓設定檔中的 ${oc.env:...} 能取到使用者自訂值
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except ImportError:  # 未安裝 python-dotenv 時僅使用系統環境變數與預設值
    pass

from core.stream_end_element import StreamEndElement
from nodes.counting_node import CountingNode
from nodes.detection_tracking_node import DetectionTrackingNode
from nodes.render_node import RenderNode
from nodes.report_node import ReportNode
from nodes.track_update_node import TrackUpdateNode
from nodes.video_reader_node import VideoReaderNode
from nodes.video_writer_node import VideoWriterNode

logger = logging.getLogger("main")

_WINDOW_TITLE = "Traffic Analyzer TW"  # OpenCV 視窗標題不支援中文，故使用英文


def _build_run_dir(config) -> str:
    """建立本次執行的輸出資料夾（以啟動時間命名，不會覆蓋先前結果）。"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(str(config["output"]["folder"]), run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def _run_analysis_chain(element, detector, track_updater, counter, renderer, writer, reporter):
    """
    讓單一元素依序流經分析鏈。

    繪製、影片輸出、報表三個節點可依設定停用，因此需逐一判斷。
    """
    element = detector.process(element)
    element = track_updater.process(element)
    element = counter.process(element)

    if renderer is not None:
        element = renderer.process(element)
    if writer is not None:
        element = writer.process(element)
    if reporter is not None:
        element = reporter.process(element)

    return element


def _print_console_summary(statistics: dict, run_dir: str) -> None:
    """在主控台印出本次分析的重點結果，方便執行後立即檢視。"""
    if not statistics:
        logger.warning("本次執行沒有產生任何統計資料。")
        return

    print("")
    print("=" * 54)
    print("  路口車流分析結果")
    print("=" * 54)
    print(f"  累計車次　：{statistics.get('累計車次', 0)} 輛")
    print(f"  累計 PCU　：{statistics.get('累計PCU', 0)}")
    print(f"  轉向紀錄　：{statistics.get('轉向筆數', 0)} 筆")

    road_totals = statistics.get("各道路累計", {})
    if road_totals:
        print("  各道路進入量：")
        for road in sorted(road_totals):
            print(f"      道路 {road}：{road_totals[road]} 輛")

    composition = statistics.get("車種組成", {})
    if composition:
        print("  車種組成：")
        for label, count in sorted(composition.items(), key=lambda kv: -kv[1]):
            print(f"      {label}：{count} 輛")

    print("-" * 54)
    print(f"  輸出資料夾：{os.path.abspath(run_dir)}")
    print("=" * 54)
    print("")


@hydra.main(version_base=None, config_path="configs", config_name="app_config")
def main(config) -> None:
    """程式進入點：建立節點、執行流水線、收尾。"""
    pipeline_cfg = config["pipeline"]
    show_window = bool(pipeline_cfg["show_window"])
    save_video = bool(pipeline_cfg["save_video"])
    write_report = bool(pipeline_cfg["write_report"])

    run_dir = _build_run_dir(config)
    logger.info("本次執行的輸出資料夾：%s", os.path.abspath(run_dir))

    # ---- 建立節點 ----
    reader = VideoReaderNode(config["video_reader"])
    detector = DetectionTrackingNode(config)
    track_updater = TrackUpdateNode(config)
    counter = CountingNode(config)

    # 預覽或存檔任一啟用時才需要繪製，純批次統計可關閉以提升速度
    renderer = RenderNode(config) if (show_window or save_video) else None
    writer = VideoWriterNode(config["video_writer_node"], run_dir) if save_video else None
    reporter = ReportNode(config, run_dir) if write_report else None

    window_scale = float(config["render_node"]["window_scale"])
    last_statistics: dict = {}
    stopped_by_user = False

    try:
        for element in reader.process():
            element = _run_analysis_chain(
                element, detector, track_updater, counter, renderer, writer, reporter
            )

            # 影片讀完：報表已於 ReportNode 內完成輸出，可直接結束
            if isinstance(element, StreamEndElement):
                break

            last_statistics = element.statistics

            if show_window:
                display_frame = element.frame_result
                if display_frame is None:
                    display_frame = element.frame
                if window_scale != 1.0:
                    display_frame = cv2.resize(
                        display_frame, None, fx=window_scale, fy=window_scale,
                        interpolation=cv2.INTER_AREA,
                    )
                cv2.imshow(_WINDOW_TITLE, display_frame)

                # 按 Q 或 Esc 提前結束，仍會完成統計收尾
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    logger.info("使用者中止分析，進行統計收尾……")
                    stopped_by_user = True
                    break

        # 使用者提前結束時，補送結束訊號讓殘留軌跡完成結算與報表輸出
        if stopped_by_user:
            end_element = StreamEndElement(reader.source_name, reader.last_timestamp)
            end_element = _run_analysis_chain(
                end_element, detector, track_updater, counter, renderer, writer, reporter
            )
            last_statistics = end_element.statistics

    finally:
        # 無論正常結束或中途異常，都要釋放資源避免影片檔損毀
        reader.release()
        if writer is not None:
            writer.release()
        if show_window:
            cv2.destroyAllWindows()

    _print_console_summary(last_statistics, run_dir)


if __name__ == "__main__":
    main()
