# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：成果網頁短片剪輯
功能說明：
    從一次分析的錄影中，剪出一段適合放在成果展示網頁的短片（web/assets/result.mp4）。

    1. 讀取各路口的 越線明細.csv，找出越線車次最多的一段時間（預設 30 秒），
       讓短片盡量拍到車流最熱鬧的片段
    2. 以 ffmpeg 轉為 H.264（yuv420p、無音訊、faststart），瀏覽器與手機皆可直接播放
    3. 依大小上限估算位元率，仍超過時自動降低位元率重試

    錄影來源：多路口模式的 多路口錄影.mp4（multi_view.record_video=true），
    或單路口模式的 分析結果.mp4（pipeline.save_video=true）。
    兩者的影片時間皆與報表中的「時間_秒」對應，故可直接以越線時間挑選片段。

使用方式：
    python tools/make_web_clip.py --run outputs/20261017_233000
    python tools/make_web_clip.py --run outputs/20261017_233000 --start 120   指定起點（秒）

建立日期：2026-10-17
版本號：v1.2.1
"""

import argparse
import csv
import os
import re
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SOURCE_NAMES = ("多路口錄影.mp4", "分析結果.mp4")   # 依序尋找，多路口錄影優先
_EVENTS_NAME = "越線明細.csv"
_TIME_COLUMN = "時間_秒"
_DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def load_settings(config_path: str):
    """讀取主設定檔的 web_clip 區段（含 .env 中的環境變數）。"""
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
    except ImportError:  # 未安裝 python-dotenv 時僅使用系統環境變數與預設值
        pass
    from omegaconf import OmegaConf

    return OmegaConf.load(config_path)["web_clip"]


def find_source_video(run_dir: str):
    """在輸出資料夾中找出錄影檔；找不到時回傳 None。"""
    for name in _SOURCE_NAMES:
        path = os.path.join(run_dir, name)
        if os.path.isfile(path):
            return path
    return None


def collect_event_times(run_dir: str) -> list:
    """收集輸出資料夾（含多路口的各路口子資料夾）中所有越線事件的時間。"""
    folders = [run_dir] + [
        os.path.join(run_dir, name) for name in sorted(os.listdir(run_dir))
        if os.path.isdir(os.path.join(run_dir, name))
    ]
    times = []
    for folder in folders:
        path = os.path.join(folder, _EVENTS_NAME)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                try:
                    times.append(float(row[_TIME_COLUMN]))
                except (KeyError, TypeError, ValueError):
                    continue
    return sorted(times)


def pick_busiest_start(times: list, video_secs: float, clip_secs: float,
                       skip_head_secs: float = 0.0) -> float:
    """
    找出越線車次最多的片段起點（秒）。

    候選起點為每個事件時間（片段從車流開始處切入），並限制片段完整落在影片內；
    事件不足或影片太短時，退回可用範圍的起點。
    """
    latest = max(video_secs - clip_secs, 0.0)
    earliest = min(max(skip_head_secs, 0.0), latest)

    best_start, best_count = earliest, -1
    for candidate in [earliest] + list(times):
        start = min(max(candidate, earliest), latest)
        count = sum(1 for t in times if start <= t < start + clip_secs)
        if count > best_count:
            best_start, best_count = start, count
    return round(best_start, 2)


def parse_duration(ffmpeg_output: str):
    """由 ffmpeg -i 的輸出解析影片長度（秒）；解析不到時回傳 None。"""
    match = _DURATION_PATTERN.search(ffmpeg_output or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe_duration(ffmpeg_bin: str, video_path: str):
    """以 ffmpeg 讀取影片長度（秒）。"""
    result = subprocess.run([ffmpeg_bin, "-hide_banner", "-i", video_path],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return parse_duration(result.stderr)


def target_bitrate_kbps(settings) -> int:
    """
    由大小上限與片段長度估算影片位元率（kbps）。

    以位元率控制大小而非畫質參數（crf），是因為各平台可用的 H.264 編碼器不同，
    例如 Windows 內建的 h264_mf 不支援 crf，但所有編碼器都支援位元率。
    """
    budget_kbits = float(settings["max_size_mb"]) * 1024 * 8 * float(settings["size_fill_ratio"])
    return max(int(budget_kbits / float(settings["duration_secs"])), 100)


def build_ffmpeg_command(ffmpeg_bin: str, source: str, output: str, start: float,
                         settings, bitrate_kbps: int) -> list:
    """組出剪輯與轉檔的 ffmpeg 指令。"""
    return [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.2f}", "-i", source,
        "-t", f"{float(settings['duration_secs']):.2f}",
        "-vf", f"scale={int(settings['width'])}:-2,fps={float(settings['fps'])}",
        "-c:v", str(settings["video_codec"]),
        "-b:v", f"{int(bitrate_kbps)}k", "-maxrate", f"{int(bitrate_kbps)}k",
        "-bufsize", f"{int(bitrate_kbps) * 2}k",
        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
        output,
    ]


def encode_clip(source: str, output: str, start: float, settings, runner=None) -> tuple:
    """
    剪輯並轉檔，仍超過大小上限時降低位元率重試。

    參數 runner 為執行外部指令的函式，預設為 subprocess.run，測試時可替換。
    回傳：(最終使用的位元率 kbps, 檔案大小 MB)。重試次數用完仍超過上限時保留最後一次的結果。
    """
    runner = runner or subprocess.run
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    limit_bytes = float(settings["max_size_mb"]) * 1024 * 1024
    bitrate = target_bitrate_kbps(settings)
    for attempt in range(1, int(settings["max_attempts"]) + 1):
        command = build_ffmpeg_command(str(settings["ffmpeg_bin"]), source, output, start,
                                       settings, bitrate)
        result = runner(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"make_web_clip｜ffmpeg 轉檔失敗：{result.stderr.strip()}")
        size = os.path.getsize(output)
        if size <= limit_bytes or attempt == int(settings["max_attempts"]):
            return bitrate, round(size / 1024 / 1024, 2)
        bitrate = max(int(bitrate * float(settings["retry_scale"])), 100)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="剪輯成果展示網頁的分析短片")
    parser.add_argument("--run", required=True, help="分析輸出資料夾，例如 outputs/20261017_233000")
    parser.add_argument("--start", type=float, default=None, help="指定片段起點（秒）；省略則自動挑選")
    parser.add_argument("--config", default=os.path.join(_PROJECT_ROOT, "configs", "app_config.yaml"))
    parser.add_argument("--output", default=None, help="輸出路徑；省略則使用設定檔的 web_clip.output")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not os.path.isdir(args.run):
        print(f"找不到輸出資料夾：{args.run}")
        return 1

    source = find_source_video(args.run)
    if source is None:
        print(f"輸出資料夾中沒有錄影檔（{'、'.join(_SOURCE_NAMES)}）：{args.run}")
        return 1

    settings = load_settings(args.config)
    output = args.output or os.path.join(_PROJECT_ROOT, str(settings["output"]))
    clip_secs = float(settings["duration_secs"])

    start = args.start
    if start is None:
        video_secs = probe_duration(str(settings["ffmpeg_bin"]), source)
        if video_secs is None:
            print(f"無法讀取影片長度：{source}")
            return 1
        times = collect_event_times(args.run)
        start = pick_busiest_start(times, video_secs, clip_secs, float(settings["skip_head_secs"]))
        count = sum(1 for t in times if start <= t < start + clip_secs)
        print(f"  影片長度 {video_secs:.0f} 秒，挑選第 {start:.0f}～{start + clip_secs:.0f} 秒（越線 {count} 車次）")

    bitrate, size_mb = encode_clip(source, output, start, settings)
    print(f"  已輸出：{os.path.abspath(output)}（{size_mb} MB，{bitrate} kbps）")
    if size_mb > float(settings["max_size_mb"]):
        print(f"  注意：重試後仍超過 {settings['max_size_mb']} MB，可縮短 duration_secs 或降低 width")
    return 0


if __name__ == "__main__":
    sys.exit(main())
