# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：多路口畫面錄影
功能說明：
    把多路口模式每次更新的多格畫面（含右側詳細資料面板）寫成影片，
    供成果展示網頁使用（再由 tools/make_web_clip.py 剪成短片）。

    多格畫面的更新間隔會隨繪製耗時浮動，若每輪只寫一幀，影片會比真實時間快或慢。
    因此依實際經過的時間決定要寫幾幀：落後時重複寫入目前的畫面，
    讓影片第 N 秒對應分析開始後的第 N 秒，便於與報表中的時間對照。

    OpenCV 在 Windows 無法寫入含中文的路徑，故先寫到同資料夾的 ASCII 暫存檔，
    關閉時再改為正式檔名。

建立日期：2026-10-17
版本號：v1.2.1
"""

import logging
import os
import time
from typing import Callable, Optional

import cv2

logger = logging.getLogger(__name__)

_TEMP_NAME = "_mosaic_recording.mp4"


class MosaicRecorder:
    """多格畫面錄影器。"""

    def __init__(self, output_path: str, fps: float, fourcc: str = "mp4v",
                 clock: Callable[[], float] = time.monotonic) -> None:
        """
        參數：
            output_path: 影片的正式路徑（可含中文）。
            fps:         影片幀率。
            fourcc:      影片編碼。
            clock:       取得目前時間的函式，測試時可替換。
        """
        if fps <= 0:
            raise ValueError(f"MosaicRecorder｜幀率必須大於 0：{fps}")
        self.output_path = output_path
        self.fps = float(fps)
        self.fourcc = str(fourcc)
        self._clock = clock
        self._temp_path = os.path.join(os.path.dirname(output_path) or ".", _TEMP_NAME)
        self._writer: Optional[cv2.VideoWriter] = None
        self._size = None
        self._started_at = 0.0
        self.frames_written = 0

    def write(self, frame) -> int:
        """
        依經過時間寫入畫面，回傳本次寫入的幀數。

        第一次呼叫時才建立影片檔（多格畫面的尺寸要畫出來才知道）。
        """
        if frame is None:
            return 0

        if self._writer is None:
            self._open(frame)

        if (frame.shape[1], frame.shape[0]) != self._size:
            # 尺寸改變（理論上不會發生）時縮放回原尺寸，避免 VideoWriter 靜默丟棄
            frame = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)

        elapsed = self._clock() - self._started_at
        target = int(elapsed * self.fps) + 1
        count = max(target - self.frames_written, 0)
        for _ in range(count):
            self._writer.write(frame)
        self.frames_written += count
        return count

    def close(self) -> Optional[str]:
        """關閉影片並改為正式檔名，回傳正式路徑；未寫入任何畫面時回傳 None。"""
        if self._writer is None:
            return None
        self._writer.release()
        self._writer = None
        os.replace(self._temp_path, self.output_path)
        logger.info("多路口錄影已儲存：%s（%d 幀，約 %.0f 秒）",
                    os.path.abspath(self.output_path), self.frames_written,
                    self.frames_written / self.fps)
        return self.output_path

    def _open(self, frame) -> None:
        """建立影片檔並開始計時。"""
        height, width = frame.shape[:2]
        self._size = (width, height)
        self._writer = cv2.VideoWriter(
            self._temp_path, cv2.VideoWriter_fourcc(*self.fourcc), self.fps, self._size
        )
        if not self._writer.isOpened():
            self._writer = None
            raise RuntimeError(
                f"MosaicRecorder｜無法建立影片檔：{self._temp_path}（編碼 {self.fourcc} 可能不被支援）"
            )
        self._started_at = self._clock()
        logger.info("多路口錄影中：%s（%dx%d @ %.1f fps）",
                    self.output_path, width, height, self.fps)


def build_recorder(view_cfg, run_dir: str) -> Optional[MosaicRecorder]:
    """依 multi_view 設定建立錄影器；未啟用錄影時回傳 None。"""
    if not bool(view_cfg.get("record_video", False)):
        return None
    return MosaicRecorder(
        os.path.join(run_dir, str(view_cfg["record_name"])),
        float(view_cfg["record_fps"]),
        str(view_cfg.get("record_fourcc", "mp4v")),
    )
