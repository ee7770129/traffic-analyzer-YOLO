# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：路口分析執行緒
功能說明：
    讓一條路口流水線在自己的執行緒中持續運作，並對外提供
    「最新的成果影格」與「最新的統計」。

    為什麼需要執行緒：
        讀取即時串流時，程式會停在原地等下一張影像送達。
        若四個路口輪流讀取，最慢的那一路會拖住其他三路，
        影像還會在緩衝區越積越多、畫面越來越落後於現場。
        各路口各自一條執行緒，才能各自以攝影機的實際速度前進。

建立日期：2026-10-08
版本號：v1.2.0
"""

import logging
import threading

from core.stream_end_element import StreamEndElement

logger = logging.getLogger(__name__)

STATUS_CONNECTING = "連線中"
STATUS_RUNNING = "分析中"
STATUS_ENDED = "已結束"
STATUS_ERROR = "發生錯誤"


class CameraWorker(threading.Thread):
    """在背景執行緒中執行單一路口的分析。"""

    def __init__(self, pipeline) -> None:
        """
        參數：
            pipeline: 具備 name、frames()、finish()、release() 的流水線物件。
        """
        # 設為背景執行緒：主程式結束時不會被卡在等待串流的讀取上
        super().__init__(name=f"camera-{getattr(pipeline, 'key', 'worker')}", daemon=True)
        self.pipeline = pipeline
        self.camera_name = pipeline.name

        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._frame = None
        self._statistics: dict = {}
        self._status = STATUS_CONNECTING
        self.frame_count = 0

    def run(self) -> None:
        """執行緒主體：逐幀分析，結束或出錯時完成收尾。"""
        try:
            for element in self.pipeline.frames():
                if isinstance(element, StreamEndElement):
                    self._publish(None, element.statistics, STATUS_ENDED)
                    return

                self.frame_count += 1
                self._publish(element.frame_result, element.statistics, STATUS_RUNNING)

                if self._stop_requested.is_set():
                    break

            final_statistics = self.pipeline.finish()
            self._publish(None, final_statistics, STATUS_ENDED)
        except Exception:  # 單一路口出錯不得拖垮其他路口，記錄後標示狀態即可
            logger.exception("路口「%s」分析中斷", self.camera_name)
            self._publish(None, {}, STATUS_ERROR)
        finally:
            self.pipeline.release()

    def _publish(self, frame, statistics: dict, status: str) -> None:
        """更新對外可見的狀態；frame 或 statistics 為空時保留前一次的內容。"""
        with self._lock:
            if frame is not None:
                self._frame = frame
            if statistics:
                self._statistics = statistics
            self._status = status

    def snapshot(self) -> tuple:
        """回傳 (最新成果影格, 最新統計, 狀態)；尚未取得影像時影格為 None。"""
        with self._lock:
            return self._frame, self._statistics, self._status

    def request_stop(self) -> None:
        """要求在處理完目前這一幀後結束並收尾。"""
        self._stop_requested.set()
