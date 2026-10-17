# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：每分鐘車流紀錄
功能說明：
    定期取樣「累計車次」，換算成每一分鐘新增的車次，供詳細資料面板繪製
    近幾分鐘的車流變化，並推估小時流量。

    只保存最近 N 分鐘，長時間執行時記憶體用量固定。

建立日期：2026-10-09
版本號：v1.2.0
"""

from collections import OrderedDict


class FlowHistory:
    """由累計車次推導每分鐘車流。"""

    def __init__(self, keep_minutes: int = 10) -> None:
        """
        參數：
            keep_minutes: 保留最近幾分鐘的紀錄
        """
        self.keep_minutes = max(int(keep_minutes), 1)
        self._per_minute: OrderedDict = OrderedDict()   # {第幾分鐘: 該分鐘新增車次}
        self._last_total = 0
        self._latest_minute = 0

    def update(self, elapsed_secs: float, total: int) -> None:
        """
        記錄一次取樣。

        參數：
            elapsed_secs: 自分析開始經過的秒數
            total:        目前的累計車次
        """
        minute = int(max(elapsed_secs, 0.0) // 60)
        self._latest_minute = max(self._latest_minute, minute)

        # 車種修正等情況可能讓累計值短暫不變或回退，不產生負的車流
        added = max(int(total) - self._last_total, 0)
        self._last_total = max(int(total), self._last_total)

        self._per_minute[minute] = self._per_minute.get(minute, 0) + added
        while len(self._per_minute) > self.keep_minutes:
            self._per_minute.popitem(last=False)

    def recent(self) -> list:
        """
        回傳最近 keep_minutes 分鐘的每分鐘車次，由舊到新。
        沒有車通過的分鐘補 0，最後一個元素是「目前這一分鐘」（尚未結束）。
        """
        first = max(self._latest_minute - self.keep_minutes + 1, 0)
        return [self._per_minute.get(minute, 0) for minute in range(first, self._latest_minute + 1)]

    @staticmethod
    def hourly_rate(total: int, elapsed_secs: float, min_secs: float = 60.0):
        """
        以目前的平均流率推估小時流量（輛／小時）。
        觀測時間太短時推估值沒有意義，回傳 None。
        """
        if elapsed_secs < min_secs:
            return None
        return int(round(total / elapsed_secs * 3600.0))
