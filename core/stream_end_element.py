# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：串流結束訊號
功能說明：
    影片讀取完畢或串流中斷時，由 VideoReaderNode 產生此物件並送入流水線，
    讓各節點知道可以進行收尾（例如報表輸出、影片檔關閉）。

    各節點的 process() 收到此物件時不做影像處理，但仍可進行收尾統計，
    因此本物件保留與 FrameElement 相同名稱的統計欄位，
    讓「軌跡收尾 → 計數 → 報表」這條收尾路徑不需要額外的特例分支。

建立日期：2024-12-18
版本號：v1.0.0
"""


class StreamEndElement:
    """影像來源結束的標記物件。"""

    def __init__(self, source: str, timestamp: float, frame_num: int = 0) -> None:
        """
        參數：
            source:    影像來源描述
            timestamp: 最後一幀的時間（秒）
            frame_num: 已處理的總幀數
        """
        self.source = source
        self.timestamp = float(timestamp)
        self.frame_num = int(frame_num)

        # 收尾階段仍會用到的統計欄位，與 FrameElement 同名以簡化下游處理
        self.active_tracks: dict = {}
        self.retired_tracks: list = []   # 影片結束時一次清空的所有殘留軌跡
        self.count_events: list = []
        self.statistics: dict = {}
