# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：影片輸出節點
功能說明：
    把繪製完成的成果影格寫入影片檔，供事後檢視或作為結果佐證。

    影片尺寸在收到第一幀時才確定（因統計面板會改變寬度），
    因此 VideoWriter 採延遲初始化，並於收到串流結束訊號時釋放資源。

建立日期：2025-02-14
版本號：v1.0.0
"""

import logging
import os
from typing import Optional

import cv2

from core.stream_end_element import StreamEndElement
from utils.profiler import profile_time

logger = logging.getLogger(__name__)


class VideoWriterNode:
    """成果影片輸出。"""

    def __init__(self, config: dict, run_dir: str) -> None:
        """
        參數：
            config:  設定檔 video_writer_node 區段。
            run_dir: 本次執行的輸出資料夾，與統計報表同目錄，便於整批保存。
        """
        self.run_dir = run_dir
        self.fps = float(config["fps"])
        self.fourcc = str(config["fourcc"])

        os.makedirs(self.run_dir, exist_ok=True)
        self.output_path = os.path.join(self.run_dir, "分析結果.mp4")

        self._writer: Optional[cv2.VideoWriter] = None

    @profile_time
    def process(self, element):
        """寫入一幀；收到結束訊號時關閉檔案。"""
        if isinstance(element, StreamEndElement):
            self.release()
            return element

        frame = element.frame_result
        if frame is None:
            # 繪製節點被停用時沒有成果影格，退而寫入原始影格
            frame = element.frame

        if self._writer is None:
            height, width = frame.shape[:2]
            self._writer = cv2.VideoWriter(
                self.output_path,
                cv2.VideoWriter_fourcc(*self.fourcc),
                self.fps,
                (width, height),
            )
            if not self._writer.isOpened():
                raise RuntimeError(
                    f"VideoWriterNode｜無法建立影片檔：{self.output_path}"
                    f"（編碼 {self.fourcc} 可能不被支援）"
                )
            logger.info("成果影片輸出中：%s（%dx%d @ %.1f fps）",
                        self.output_path, width, height, self.fps)

        self._writer.write(frame)
        return element

    def release(self) -> None:
        """關閉影片檔並釋放資源。"""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            logger.info("成果影片已儲存：%s", os.path.abspath(self.output_path))
