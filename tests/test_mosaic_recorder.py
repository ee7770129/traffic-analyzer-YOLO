# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：多路口畫面錄影的單元測試
功能說明：
    以可控制的假時鐘驗證「依經過時間補幀」的幀數計算，
    並實際寫出小尺寸影片，確認暫存檔會改為含中文的正式檔名。

建立日期：2026-10-17
版本號：v1.2.1
"""

import os

import cv2
import numpy as np
import pytest

from multiview.mosaic_recorder import MosaicRecorder, build_recorder


class FakeClock:
    """可手動推進的時鐘。"""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def make_frame(width=64, height=48, value=80):
    return np.full((height, width, 3), value, dtype=np.uint8)


def read_frame_count(path):
    """讀取影片幀數；OpenCV 無法開啟中文路徑，故先複製到 ASCII 檔名。"""
    temp = os.path.join(os.path.dirname(path), "_count_check.mp4")
    with open(path, "rb") as src, open(temp, "wb") as dst:
        dst.write(src.read())
    capture = cv2.VideoCapture(temp)
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()
    os.remove(temp)
    return count


def test_writes_frames_by_elapsed_time(tmp_path):
    clock = FakeClock()
    recorder = MosaicRecorder(str(tmp_path / "多路口錄影.mp4"), fps=10, clock=clock)

    assert recorder.write(make_frame()) == 1      # 第一幀立即寫入
    assert recorder.write(make_frame()) == 0      # 時間未前進，不重複寫

    clock.now += 0.5                              # 經過 0.5 秒 → 應累計到第 6 幀
    assert recorder.write(make_frame()) == 5
    assert recorder.frames_written == 6

    clock.now += 0.05                             # 不足一幀的間隔不寫
    assert recorder.write(make_frame()) == 0

    path = recorder.close()
    assert path == str(tmp_path / "多路口錄影.mp4")
    assert os.path.isfile(path)
    assert not os.path.exists(tmp_path / "_mosaic_recording.mp4")
    assert read_frame_count(path) == 6


def test_resizes_frames_with_different_size(tmp_path):
    clock = FakeClock()
    recorder = MosaicRecorder(str(tmp_path / "out.mp4"), fps=5, clock=clock)
    recorder.write(make_frame(64, 48))
    clock.now += 0.2
    assert recorder.write(make_frame(100, 80)) == 1
    recorder.close()
    assert read_frame_count(str(tmp_path / "out.mp4")) == 2


def test_none_frame_and_close_without_frames(tmp_path):
    recorder = MosaicRecorder(str(tmp_path / "out.mp4"), fps=10)
    assert recorder.write(None) == 0
    assert recorder.close() is None
    assert not os.path.exists(tmp_path / "out.mp4")


def test_rejects_non_positive_fps(tmp_path):
    with pytest.raises(ValueError):
        MosaicRecorder(str(tmp_path / "out.mp4"), fps=0)


def test_raises_when_writer_cannot_open(tmp_path):
    recorder = MosaicRecorder(str(tmp_path / "missing_dir" / "out.mp4"), fps=10)
    with pytest.raises(RuntimeError):
        recorder.write(make_frame())


def test_build_recorder_respects_switch(tmp_path):
    assert build_recorder({"record_video": False}, str(tmp_path)) is None
    assert build_recorder({}, str(tmp_path)) is None

    recorder = build_recorder(
        {"record_video": True, "record_name": "多路口錄影.mp4", "record_fps": 8},
        str(tmp_path),
    )
    assert isinstance(recorder, MosaicRecorder)
    assert recorder.fps == 8.0
    assert recorder.fourcc == "mp4v"
    assert recorder.output_path == os.path.join(str(tmp_path), "多路口錄影.mp4")
