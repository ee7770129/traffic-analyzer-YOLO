# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：多路口同步分析主程式
功能說明：
    同時分析多個路口的即時影像，並把各路口的成果畫面拼成一張多格畫面顯示。
    本檔只負責建立各路口的流水線、排版顯示與流程控制，
    分析邏輯位於各節點，單一路口的組裝位於 multiview/camera_pipeline.py。

    每個路口的報表各自輸出到 outputs/<執行時間>/<路口預設組名稱>/。

使用方式：
    python multi_view.py                                  以設定檔的路口清單執行
    python multi_view.py cctv.max_duration_secs=600       分析十分鐘後自動結束
    python multi_view.py multi_view.columns=4             改為橫向一排

    在畫面上按 Q 或 Esc 結束，各路口會完成結算並輸出報表。

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging
import os
import time
from datetime import datetime

import cv2
import hydra
import numpy as np
from omegaconf import OmegaConf

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
except ImportError:  # 未安裝 python-dotenv 時僅使用系統環境變數與預設值
    pass

from multiview.camera_pipeline import CameraPipeline
from multiview.camera_worker import STATUS_ENDED, STATUS_ERROR, CameraWorker
from multiview.detail_panel import DetailPanel
from multiview.flow_history import FlowHistory
from multiview.mosaic import build_cell, cell_origin, compose_grid, format_caption
from utils.cctv_source import load_catalog, resolve_camera
from utils.text_drawer import TextDrawer

logger = logging.getLogger("multi_view")

_WINDOW_TITLE = "Traffic Analyzer TW - Multi View"  # OpenCV 視窗標題不支援中文


def build_workers(config, run_dir: str) -> list:
    """依設定的路口清單建立各路口的流水線與執行緒（尚未啟動）。"""
    catalog = load_catalog(str(config["cctv"]["catalog"]))

    # 多格畫面空間有限，各格不顯示右側統計面板，改由標題列呈現重點數字
    cell_config = OmegaConf.merge(config, {"render_node": {"show_panel": False}})
    write_report = bool(config["pipeline"]["write_report"])

    workers = []
    for camera_key in config["multi_view"]["cameras"]:
        camera = resolve_camera(str(camera_key), catalog)
        pipeline = CameraPipeline(
            cell_config, camera, os.path.join(run_dir, camera["key"]), write_report,
            display_width=float(config["multi_view"]["cell_width"]),
        )
        workers.append(CameraWorker(pipeline))
    return workers


def render_mosaic(workers: list, view_cfg, text_drawer: TextDrawer, panel=None,
                  histories=None, elapsed_secs: float = 0.0):
    """
    取各路口的最新畫面拼成多格畫面，並加上各格的標題列。
    提供 panel 時，在右側接上詳細資料面板。
    """
    width = int(view_cfg["cell_width"])
    height = int(view_cfg["cell_height"])
    caption_height = int(view_cfg["caption_height"])
    columns = int(view_cfg["columns"])

    cells, captions, blocks = [], [], []
    for index, worker in enumerate(workers):
        frame, statistics, status = worker.snapshot()
        blocks.append(build_panel_block(
            worker, statistics, status, elapsed_secs, histories[index] if histories else None
        ))
        cells.append(build_cell(frame, width, height, caption_height))

        x, y = cell_origin(index, columns, width, caption_height + height)
        captions.append({
            "text": format_caption(worker.camera_name, status, statistics),
            "xy": (x + 10, y + 6),
            "color": (255, 255, 255),
            "size": "normal",
        })

    mosaic = text_drawer.draw(compose_grid(cells, columns), captions)
    if panel is None:
        return mosaic

    # 面板高度以「每個路口一個區塊」計算，多欄排列時可能與左側不等高，補底色對齊
    side = panel.render(blocks)
    height = max(mosaic.shape[0], side.shape[0])
    return np.hstack([pad_to_height(mosaic, height), pad_to_height(side, height)])


def pad_to_height(image, height: int):
    """在影像下方補底色到指定高度。"""
    missing = height - image.shape[0]
    if missing <= 0:
        return image
    filler = np.full((missing, image.shape[1], 3), 24, dtype=np.uint8)
    return np.vstack([image, filler])


def build_panel_block(worker, statistics: dict, status: str, elapsed_secs: float, history) -> dict:
    """整理單一路口要顯示在詳細資料面板上的內容，並更新其每分鐘車流紀錄。"""
    total = int(statistics.get("累計車次", 0))
    per_minute = []
    if history is not None:
        history.update(elapsed_secs, total)
        per_minute = history.recent()
    return {
        "name": worker.camera_name,
        "status": status,
        "statistics": statistics,
        "elapsed_secs": elapsed_secs,
        "per_minute": per_minute,
        "history_slots": history.keep_minutes if history is not None else 0,
        "hourly_rate": FlowHistory.hourly_rate(total, elapsed_secs),
    }


def save_snapshot(image, path: str) -> None:
    """儲存多格畫面；路徑含中文時 cv2.imwrite 會失敗，故自行編碼寫檔。"""
    ok, buffer = cv2.imencode(os.path.splitext(path)[1] or ".jpg", image)
    if ok:
        buffer.tofile(path)
        logger.info("多格畫面已儲存：%s", os.path.abspath(path))


@hydra.main(version_base=None, config_path="configs", config_name="app_config")
def main(config) -> None:
    """程式進入點：啟動各路口的分析、顯示多格畫面、收尾。"""
    view_cfg = config["multi_view"]
    show_window = bool(config["pipeline"]["show_window"])
    max_duration_secs = float(config["cctv"]["max_duration_secs"] or 0)
    refresh_secs = float(view_cfg["refresh_ms"]) / 1000.0
    window_scale = float(view_cfg["window_scale"])

    run_dir = os.path.join(str(config["output"]["folder"]), datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    logger.info("本次執行的輸出資料夾：%s", os.path.abspath(run_dir))

    text_drawer = TextDrawer(
        font_candidates=list(config["render_node"]["font_candidates"]),
        sizes=dict(config["render_node"]["font_sizes"]),
    )

    workers = build_workers(config, run_dir)

    # 右側詳細資料面板：寬度設為 0 即停用，只顯示路口畫面
    panel = None
    histories = None
    if int(view_cfg["panel_width"]) > 0:
        panel_drawer = TextDrawer(
            font_candidates=list(config["render_node"]["font_candidates"]),
            sizes=dict(view_cfg["panel_font_sizes"]),
        )
        panel = DetailPanel(
            panel_drawer, int(view_cfg["panel_width"]),
            int(view_cfg["cell_height"]) + int(view_cfg["caption_height"]),
        )
        histories = [FlowHistory(int(view_cfg["flow_history_minutes"])) for _ in workers]

    def draw():
        return render_mosaic(workers, view_cfg, text_drawer, panel, histories,
                             time.time() - started_at)
    started_at = time.time()
    for worker in workers:
        worker.start()

    mosaic = None
    try:
        while True:
            mosaic = draw()

            if show_window:
                display = mosaic
                if window_scale != 1.0:
                    display = cv2.resize(mosaic, None, fx=window_scale, fy=window_scale,
                                         interpolation=cv2.INTER_AREA)
                cv2.imshow(_WINDOW_TITLE, display)
                key = cv2.waitKey(max(int(refresh_secs * 1000), 1)) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    logger.info("使用者中止分析，進行統計收尾……")
                    break
            else:
                time.sleep(refresh_secs)

            if max_duration_secs > 0 and time.time() - started_at >= max_duration_secs:
                logger.info("已達分析時間上限 %.0f 秒，進行統計收尾……", max_duration_secs)
                break

            # 所有路口都已結束或出錯時，沒有東西可看了
            if all(worker.snapshot()[2] in (STATUS_ENDED, STATUS_ERROR) for worker in workers):
                logger.info("所有路口皆已結束。")
                break
    finally:
        for worker in workers:
            worker.request_stop()
        for worker in workers:
            worker.join(timeout=float(view_cfg["stop_timeout_secs"]))
            if worker.is_alive():
                logger.warning("路口「%s」未在時限內完成收尾，其報表可能不完整。", worker.camera_name)
        if show_window:
            cv2.destroyAllWindows()

    if mosaic is not None:
        # 收尾後再取一次，讓存檔的畫面帶有最終統計
        save_snapshot(draw(),
                      os.path.join(run_dir, str(view_cfg["snapshot_name"])))

    print("")
    print("=" * 54)
    print("  多路口車流分析結果")
    print("=" * 54)
    for worker in workers:
        _, statistics, status = worker.snapshot()
        print(f"  {format_caption(worker.camera_name, status, statistics)}")
    print("-" * 54)
    print(f"  輸出資料夾：{os.path.abspath(run_dir)}")
    print("=" * 54)
    print("")


if __name__ == "__main__":
    main()
