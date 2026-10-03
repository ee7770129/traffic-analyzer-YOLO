# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：單一車輛軌跡資料結構
功能說明：
    紀錄一台車從進入畫面到離開畫面的完整歷程，是「精確累計計數」與
    「轉向 OD 矩陣」兩項統計的資料基礎。

    與原始專案的差異（原專案僅記錄進入道路、且統計為滑動視窗估計值）：
        1. 同時記錄「進入道路」與「離開道路」，可推導轉向流向。
        2. 以生命週期多數決決定車種，比逐幀分類穩定。
        3. 以 counted_* 旗標保證每台車只被計入一次，統計值可重現。

建立日期：2025-01-15
版本號：v1.0.0
"""

from collections import Counter
from typing import Optional


class TrackElement:
    """單一車輛追蹤軌跡。"""

    def __init__(self, track_id: int, timestamp: float) -> None:
        """
        參數：
            track_id:  追蹤器指派的唯一編號
            timestamp: 首次出現的時間（自影片起算的秒數）
        """
        self.track_id = int(track_id)

        # ---- 時間資訊 ----
        self.timestamp_first = float(timestamp)  # 首次出現
        self.timestamp_last = float(timestamp)   # 最後一次出現

        # ---- 進出道路判定 ----
        self.entry_road: Optional[int] = None      # 進入圓環所經的道路編號
        self.entry_timestamp: Optional[float] = None
        self.exit_road: Optional[int] = None       # 離開圓環所經的道路編號
        self.exit_timestamp: Optional[float] = None
        self.zone_sequence: list = []              # 依序造訪過的區域，供除錯與驗證

        # ---- 車種投票 ----
        self._class_votes: Counter = Counter()

        # ---- 計數旗標（確保每台車只計一次）----
        self.counted_entry = False      # 是否已計入進入流量
        self.counted_movement = False   # 是否已計入轉向 OD 矩陣

        # 計入當下所採用的車種。計數發生在軌跡剛達門檻時（票數還少），
        # 之後票數累積可能改變多數決結果，離場時需據此回頭修正統計。
        self.counted_vehicle_type: Optional[str] = None

        # ---- 其他 ----
        self.last_xyxy: Optional[list] = None  # 最後一次的邊界框，供繪圖使用

    # ------------------------------------------------------------------
    # 狀態更新
    # ------------------------------------------------------------------
    def update(self, timestamp: float, xyxy: Optional[list] = None) -> None:
        """更新最後出現時間與邊界框。"""
        self.timestamp_last = float(timestamp)
        if xyxy is not None:
            self.last_xyxy = list(xyxy)

    def vote_vehicle_type(self, label: Optional[str]) -> None:
        """累積一次車種投票；label 為 None 時不計入，避免污染統計。"""
        if label:
            self._class_votes[label] += 1

    def observe_zone(self, zone_id: Optional[int], timestamp: float) -> None:
        """
        記錄本幀車輛所在的區域，並據此判定進入／離開道路。

        判定規則：
            - 第一個踩到的區域視為「進入道路」。
            - 之後第一個「與進入道路不同」的區域視為「離開道路」。
            - 車輛在圓環中央（不屬於任何區域）時 zone_id 為 None，直接略過。

        參數：
            zone_id:   本幀所在區域編號，不在任何區域內時為 None
            timestamp: 本幀時間（秒）
        """
        if zone_id is None:
            return

        # 只在區域切換時記錄，避免同一區域被重複塞入序列
        if not self.zone_sequence or self.zone_sequence[-1] != zone_id:
            self.zone_sequence.append(zone_id)

        if self.entry_road is None:
            self.entry_road = zone_id
            self.entry_timestamp = float(timestamp)
        elif zone_id != self.entry_road and self.exit_road is None:
            self.exit_road = zone_id
            self.exit_timestamp = float(timestamp)

    # ------------------------------------------------------------------
    # 衍生屬性
    # ------------------------------------------------------------------
    @property
    def vehicle_type(self) -> Optional[str]:
        """以生命週期內出現最多次的類別作為此車的車種；無票時回傳 None。"""
        if not self._class_votes:
            return None
        return self._class_votes.most_common(1)[0][0]

    @property
    def vote_count(self) -> int:
        """累積的車種投票總數，可視為此軌跡被成功辨識的幀數。"""
        return sum(self._class_votes.values())

    @property
    def lifetime(self) -> float:
        """軌跡存活秒數。"""
        return self.timestamp_last - self.timestamp_first

    @property
    def has_movement(self) -> bool:
        """是否已同時取得進入與離開道路（可構成一筆轉向紀錄）。"""
        return self.entry_road is not None and self.exit_road is not None

    def to_record(self) -> dict:
        """轉為報表用的一筆紀錄，對應輸出的車輛明細 CSV。"""
        return {
            "追蹤編號": self.track_id,
            "車種": self.vehicle_type or "",
            "進入道路": self.entry_road if self.entry_road is not None else "",
            "進入時間_秒": round(self.entry_timestamp, 2) if self.entry_timestamp is not None else "",
            "離開道路": self.exit_road if self.exit_road is not None else "",
            "離開時間_秒": round(self.exit_timestamp, 2) if self.exit_timestamp is not None else "",
            "首次出現_秒": round(self.timestamp_first, 2),
            "最後出現_秒": round(self.timestamp_last, 2),
            "存活秒數": round(self.lifetime, 2),
            "辨識幀數": self.vote_count,
            "區域序列": "-".join(str(z) for z in self.zone_sequence),
        }
