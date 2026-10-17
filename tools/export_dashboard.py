# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：成果展示網頁資料匯出
功能說明：
    把一次分析的輸出資料夾，轉成成果展示網頁（web/）所需的檔案：

        web/data/summary.json            各路口的統計數字、越線計數、轉向矩陣、尖峰小時係數
        web/assets/heatmap_<路口>.jpg    各路口的軌跡熱力圖
        web/assets/result.jpg            代表畫面（多路口畫面，或成果影片中的一幀）

    網頁本身為純靜態頁面，不執行任何分析；分析需要 GPU，只能在本機進行。
    每次想更新網頁上的數據，重新執行本工具後再部署一次即可。

使用方式：
    python tools/export_dashboard.py --run outputs/20261009_120000
        多路口模式（run_multi.bat）的輸出，會自動辨識其中的各個路口
    python tools/export_dashboard.py --run outputs/20261008_233000 --camera wuquan_fuxing
        單路口模式的輸出，須指明是哪個路口

建立日期：2026-10-08
版本號：v1.2.0
"""

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime

import cv2
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.cctv_source import load_catalog  # noqa: E402  （需先設定匯入路徑）

_COUNTED_FLAG = "是"
_MOSAIC_NAME = "多路口畫面.jpg"   # 與 configs/app_config.yaml 的 multi_view.snapshot_name 相同


def read_csv(run_dir: str, filename: str) -> list:
    """讀取輸出資料夾中的一份 CSV；檔案不存在時回傳空串列。"""
    path = os.path.join(run_dir, filename)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file))


def summarize_vehicles(rows: list) -> dict:
    """由車輛明細彙總累計車次、各道路進入量、車種組成與觀測長度。"""
    if not rows:
        return {"total": 0, "by_road": {}, "by_type": {}, "duration_secs": 0.0}

    header, body = rows[0], rows[1:]
    records = [dict(zip(header, row)) for row in body]
    counted = [r for r in records if r.get("是否計入統計") == _COUNTED_FLAG]

    last_seen = [float(r["最後出現_秒"]) for r in records if r.get("最後出現_秒")]
    return {
        "total": len(counted),
        "by_road": dict(sorted(Counter(r["進入道路"] for r in counted).items())),
        "by_type": dict(Counter(r["車種"] for r in counted).most_common()),
        "duration_secs": round(max(last_seen), 1) if last_seen else 0.0,
    }


def build_camera_list(catalog: dict) -> list:
    """把路口目錄轉成網頁用的清單（含官方攝影機頁面連結）。"""
    cameras = []
    for key, camera in catalog["cameras"].items():
        cameras.append({
            "key": key,
            "name": camera.get("name", key),
            "resolution": camera.get("resolution", ""),
            "measured_fps": camera.get("measured_fps", ""),
            "page_url": str(catalog["page_url_template"]).format(camera_id=camera["camera_id"]),
        })
    return cameras


def find_intersection_dirs(run_dir: str, camera_key, catalog: dict) -> list:
    """
    找出輸出資料夾中各路口的資料位置，回傳 [(路口預設組名稱, 資料夾)]。

    多路口模式的輸出資料夾內，每個路口各有一個以預設組名稱命名的子資料夾；
    單路口模式則報表直接放在輸出資料夾，須以 camera_key 指明是哪個路口。
    """
    found = [
        (key, os.path.join(run_dir, key))
        for key in catalog["cameras"]
        if os.path.isdir(os.path.join(run_dir, key))
    ]
    if found:
        return found

    if not camera_key:
        raise ValueError("export_dashboard｜單路口的輸出資料夾須以 --camera 指定路口預設組")
    if camera_key not in catalog["cameras"]:
        raise ValueError(f"export_dashboard｜路口目錄中沒有「{camera_key}」")
    return [(camera_key, run_dir)]


def build_intersection(folder: str, camera: dict) -> dict:
    """組出單一路口的網頁資料。"""
    return {
        "camera": camera,
        "vehicles": summarize_vehicles(read_csv(folder, "車輛明細.csv")),
        "line_counts": read_csv(folder, "越線計數.csv"),
        "line_matrix": read_csv(folder, "越線轉向矩陣.csv"),
        "phf": read_csv(folder, "尖峰小時係數.csv"),
        "heatmap": f"assets/heatmap_{camera['key']}.jpg",
    }


def build_summary(run_dir: str, camera_key, catalog: dict) -> dict:
    """組出網頁所需的完整資料。"""
    cameras = {camera["key"]: camera for camera in build_camera_list(catalog)}
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "run_id": os.path.basename(os.path.normpath(run_dir)),
        "cameras": list(cameras.values()),
        "intersections": [
            build_intersection(folder, cameras[key])
            for key, folder in find_intersection_dirs(run_dir, camera_key, catalog)
        ],
    }


def read_image(path: str):
    """讀取圖片；路徑含中文時 cv2.imread 會失敗，故改以位元組解碼。"""
    if not os.path.isfile(path):
        return None
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def write_jpeg(image, path: str, quality: int) -> bool:
    """以 JPEG 寫出圖片；image 為 None 時不寫入並回傳 False。"""
    if image is None:
        return False
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        buffer.tofile(path)
    return bool(ok)


def grab_video_frame(video_path: str, position: float):
    """
    取出成果影片中指定位置（0～1）的一幀。

    OpenCV 在 Windows 無法開啟含中文的路徑，故先複製到暫存檔再讀取。
    """
    if not os.path.isfile(video_path):
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, "result.mp4")
        shutil.copyfile(video_path, temp_path)
        capture = cv2.VideoCapture(temp_path)
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(int(total * position) - 1, 0))
        ok, frame = capture.read()
        capture.release()
    return frame if ok else None


def export(run_dir: str, camera_key: str, catalog_path: str, web_dir: str,
           frame_position: float = 0.9, jpeg_quality: int = 85) -> dict:
    """執行匯出，回傳各檔案是否成功寫出。"""
    data_dir = os.path.join(web_dir, "data")
    assets_dir = os.path.join(web_dir, "assets")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    catalog = load_catalog(catalog_path)
    summary = build_summary(run_dir, camera_key, catalog)
    with open(os.path.join(data_dir, "summary.json"), "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    written = {"summary": True}
    for key, folder in find_intersection_dirs(run_dir, camera_key, catalog):
        heatmap = read_image(os.path.join(folder, "軌跡熱力圖.png"))
        written[f"heatmap_{key}"] = write_jpeg(
            heatmap, os.path.join(assets_dir, f"heatmap_{key}.jpg"), jpeg_quality
        )

    # 代表畫面：多路口模式有現成的多格畫面，單路口模式則由成果影片取一幀
    frame = read_image(os.path.join(run_dir, _MOSAIC_NAME))
    if frame is None:
        frame = grab_video_frame(os.path.join(run_dir, "分析結果.mp4"), frame_position)
    written["result"] = write_jpeg(frame, os.path.join(assets_dir, "result.jpg"), jpeg_quality)
    return written


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="匯出成果展示網頁所需的資料")
    parser.add_argument("--run", required=True, help="分析輸出資料夾，例如 outputs/20261008_233000")
    parser.add_argument("--camera", default=None,
                        help="路口預設組名稱；單路口的輸出資料夾必填，多路口的會自動辨識")
    parser.add_argument("--catalog", default=os.path.join(_PROJECT_ROOT, "configs", "cctv_cameras.yaml"))
    parser.add_argument("--web", default=os.path.join(_PROJECT_ROOT, "web"))
    parser.add_argument("--frame-position", type=float, default=0.9,
                        help="代表畫面取自成果影片的位置（0～1）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not os.path.isdir(args.run):
        print(f"找不到輸出資料夾：{args.run}")
        return 1

    written = export(args.run, args.camera, args.catalog, args.web, args.frame_position)
    for name, ok in written.items():
        print(f"  {name}：{'已輸出' if ok else '來源不存在，略過'}")
    print(f"網頁資料已更新：{os.path.abspath(args.web)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
