# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：成果網頁短片剪輯的單元測試
功能說明：
    驗證越線事件收集、最熱鬧片段的挑選、ffmpeg 輸出解析與指令組裝，
    以及超過大小上限時調高壓縮率重試的流程。
    ffmpeg 以假的執行函式代替，測試不需要安裝 ffmpeg。

建立日期：2026-10-17
版本號：v1.2.1
"""

import os
from types import SimpleNamespace

import pytest

from tools import make_web_clip as clip

_SETTINGS = {
    "ffmpeg_bin": "ffmpeg",
    "video_codec": "h264_mf",
    "duration_secs": 30,
    "skip_head_secs": 20,
    "width": 1280,
    "fps": 10,
    "max_size_mb": 5,
    "size_fill_ratio": 0.85,
    "retry_scale": 0.8,
    "max_attempts": 4,
    "output": "web/assets/result.mp4",
}

_EVENTS_HEADER = "追蹤編號,時間_秒,計數線,計數線名稱,方向,車種,PCU\n"


def write_events(folder, times):
    os.makedirs(folder, exist_ok=True)
    rows = "".join(f"{i},{t},1,近端道路,進入,小客車,1.0\n" for i, t in enumerate(times))
    with open(os.path.join(folder, "越線明細.csv"), "w", encoding="utf-8-sig") as file:
        file.write(_EVENTS_HEADER + rows)


# ---------------------------------------------------------------- 事件收集

def test_collect_event_times_from_root_and_subfolders(tmp_path):
    write_events(str(tmp_path / "camera_a"), [50.0, 10.5])
    write_events(str(tmp_path / "camera_b"), [30.0])
    write_events(str(tmp_path), [5.0])
    with open(tmp_path / "camera_b" / "越線明細.csv", "a", encoding="utf-8") as file:
        file.write("9,壞資料,1,近端道路,進入,小客車,1.0\n")

    assert clip.collect_event_times(str(tmp_path)) == [5.0, 10.5, 30.0, 50.0]


def test_collect_event_times_without_files(tmp_path):
    (tmp_path / "empty").mkdir()
    assert clip.collect_event_times(str(tmp_path)) == []


# ---------------------------------------------------------------- 片段挑選

def test_pick_busiest_start_finds_dense_window():
    times = [25, 100, 101, 102, 103, 110, 125, 300]
    assert clip.pick_busiest_start(times, video_secs=600, clip_secs=30, skip_head_secs=20) == 100


def test_pick_busiest_start_ignores_head_and_clamps_to_end():
    # 開頭的密集事件落在略過範圍內，起點被夾到 skip_head_secs
    assert clip.pick_busiest_start([1, 2, 3, 21], 600, 30, skip_head_secs=20) == 20
    # 尾端的事件：起點不能晚於 影片長度 - 片段長度
    assert clip.pick_busiest_start([590, 595], 600, 30, skip_head_secs=20) == 570


def test_pick_busiest_start_without_events_or_short_video():
    assert clip.pick_busiest_start([], 600, 30, skip_head_secs=20) == 20
    assert clip.pick_busiest_start([5, 6], 25, 30, skip_head_secs=20) == 0


# ---------------------------------------------------------------- ffmpeg

def test_parse_duration():
    output = "Input #0, mov,mp4\n  Duration: 00:10:02.40, start: 0.000000, bitrate: 4000 kb/s"
    assert clip.parse_duration(output) == pytest.approx(602.4)
    assert clip.parse_duration("no duration here") is None
    assert clip.parse_duration(None) is None


def test_target_bitrate_from_size_budget():
    # 5 MB × 8 × 1024 × 0.85 ÷ 30 秒 ≈ 1160 kbps
    assert clip.target_bitrate_kbps(_SETTINGS) == 1160
    # 極端設定下不低於 100 kbps
    assert clip.target_bitrate_kbps({**_SETTINGS, "max_size_mb": 0.01}) == 100


def test_build_ffmpeg_command():
    command = clip.build_ffmpeg_command("ff.exe", "in.mp4", "out.mp4", 12.345, _SETTINGS, 900)
    assert command[0] == "ff.exe"
    assert command[command.index("-ss") + 1] == "12.35"
    assert command[command.index("-t") + 1] == "30.00"
    assert command[command.index("-vf") + 1] == "scale=1280:-2,fps=10.0"
    assert command[command.index("-c:v") + 1] == "h264_mf"
    assert command[command.index("-b:v") + 1] == "900k"
    assert command[command.index("-bufsize") + 1] == "1800k"
    assert "-an" in command and "+faststart" in command and "yuv420p" in command
    assert command[-1] == "out.mp4"


def fake_runner(sizes, calls, returncode=0):
    """每次呼叫依序寫出指定大小（MB）的檔案，模擬 ffmpeg 輸出。"""
    def run(command, **kwargs):
        calls.append(command)
        size_mb = sizes[min(len(calls) - 1, len(sizes) - 1)]
        with open(command[-1], "wb") as file:
            file.write(b"\0" * int(size_mb * 1024 * 1024))
        return SimpleNamespace(returncode=returncode, stderr="boom")
    return run


def test_encode_clip_retries_until_under_limit(tmp_path):
    calls = []
    output = str(tmp_path / "assets" / "result.mp4")
    bitrate, size_mb = clip.encode_clip("in.mp4", output, 0, _SETTINGS, fake_runner([8, 6, 3], calls))
    assert (bitrate, size_mb) == (742, 3.0)
    assert [c[c.index("-b:v") + 1] for c in calls] == ["1160k", "928k", "742k"]


def test_encode_clip_stops_after_max_attempts(tmp_path):
    calls = []
    output = str(tmp_path / "result.mp4")
    bitrate, size_mb = clip.encode_clip("in.mp4", output, 0, _SETTINGS, fake_runner([9], calls))
    assert size_mb == 9.0
    assert len(calls) == 4
    assert bitrate == 593   # 1160 → 928 → 742 → 593


def test_encode_clip_raises_on_ffmpeg_error(tmp_path):
    with pytest.raises(RuntimeError):
        clip.encode_clip("in.mp4", str(tmp_path / "r.mp4"), 0, _SETTINGS,
                         fake_runner([1], [], returncode=1))


# ---------------------------------------------------------------- 主程式

def test_find_source_video_prefers_mosaic(tmp_path):
    assert clip.find_source_video(str(tmp_path)) is None
    (tmp_path / "分析結果.mp4").write_bytes(b"x")
    assert clip.find_source_video(str(tmp_path)).endswith("分析結果.mp4")
    (tmp_path / "多路口錄影.mp4").write_bytes(b"x")
    assert clip.find_source_video(str(tmp_path)).endswith("多路口錄影.mp4")


def test_main_reports_missing_inputs(tmp_path, capsys):
    assert clip.main(["--run", str(tmp_path / "nope")]) == 1
    assert clip.main(["--run", str(tmp_path)]) == 1
    assert "沒有錄影檔" in capsys.readouterr().out


def test_main_full_flow(tmp_path, monkeypatch, capsys):
    run_dir = tmp_path / "run"
    write_events(str(run_dir / "camera_a"), [60, 61, 62, 200])
    (run_dir / "多路口錄影.mp4").write_bytes(b"x")
    config = tmp_path / "app_config.yaml"
    config.write_text(
        "web_clip:\n" + "".join(f"  {k}: {v}\n" for k, v in _SETTINGS.items()), encoding="utf-8"
    )

    calls = []
    monkeypatch.setattr(clip, "probe_duration", lambda ffmpeg, path: 600.0)
    monkeypatch.setattr(clip.subprocess, "run", fake_runner([2], calls))

    output = tmp_path / "out.mp4"
    assert clip.main(["--run", str(run_dir), "--config", str(config), "--output", str(output)]) == 0
    assert calls[0][calls[0].index("-ss") + 1] == "60.00"
    assert output.is_file()
    assert "越線 3 車次" in capsys.readouterr().out

    # 指定起點時不讀影片長度、不挑選片段
    monkeypatch.setattr(clip, "probe_duration", lambda *a: pytest.fail("不應讀取影片長度"))
    assert clip.main(["--run", str(run_dir), "--config", str(config),
                      "--output", str(output), "--start", "77"]) == 0
    assert calls[-1][calls[-1].index("-ss") + 1] == "77.00"


def test_main_fails_when_duration_unknown(tmp_path, monkeypatch, capsys):
    (tmp_path / "多路口錄影.mp4").write_bytes(b"x")
    config = tmp_path / "app_config.yaml"
    config.write_text(
        "web_clip:\n" + "".join(f"  {k}: {v}\n" for k, v in _SETTINGS.items()), encoding="utf-8"
    )
    monkeypatch.setattr(clip, "probe_duration", lambda *a: None)
    assert clip.main(["--run", str(tmp_path), "--config", str(config)]) == 1
    assert "無法讀取影片長度" in capsys.readouterr().out
