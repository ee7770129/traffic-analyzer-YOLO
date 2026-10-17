# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：越線計數節點
功能說明：
    在每條聯絡道上設一條計數線，以車輛前後兩幀的位移是否跨越該線來計數，
    並依跨越方向區分「進入路口」與「離開路口」。

    與既有區域計數（CountingNode）的差異：
        1. 區域計數以「造訪區域的先後順序」推論進出，同一塊區域同時涵蓋
           進入與離開車道；越線計數直接由跨越方向判定，不需推論。
        2. 以線段相交判定，低幀率串流下車輛一幀跨過整條線也不會漏計。

    兩者並存、互不影響：本節點只讀取軌跡，不修改 CountingNode 的任何統計。

計數門檻：
    沿用 general 區段的 min_track_life_secs 與 min_vote_count。
    越線當下若軌跡尚未達門檻，先暫存；達門檻後才計入即時統計。
    最終紀錄於軌跡離場時產生，車種採用離場時的多數決結果。

建立日期：2026-10-08
版本號：v1.2.0
"""

import json
import logging
import os

from core.stream_end_element import StreamEndElement
from utils.line_geometry import ANCHOR_BOTTOM_CENTER, anchor_point, crossing_direction
from utils.profiler import profile_time
from utils.vehicle_types import VehicleTypeRegistry

logger = logging.getLogger(__name__)


def load_lines(lines_file: str) -> dict:
    """
    載入計數線設定檔。

    檔案格式：
        {
          "inside_point": [x, y],                      路口內側的參考點
          "lines": [{"id": 1, "name": "...", "p1": [x, y], "p2": [x, y]}, ...]
        }
    """
    if not os.path.isfile(lines_file):
        raise FileNotFoundError(f"LineCountingNode｜找不到計數線設定檔：{lines_file}")

    with open(lines_file, "r", encoding="utf-8") as file:
        raw = json.load(file)

    inside_point = tuple(float(v) for v in raw["inside_point"])
    lines = {}
    for item in raw.get("lines", []):
        lines[int(item["id"])] = {
            "name": str(item.get("name", f"計數線 {item['id']}")),
            "p1": tuple(float(v) for v in item["p1"]),
            "p2": tuple(float(v) for v in item["p2"]),
        }
    return {"inside_point": inside_point, "lines": lines}


class LineCountingNode:
    """以計數線判定車輛進入與離開路口。"""

    def __init__(self, config: dict, lines_file: str) -> None:
        """
        參數：
            config:     完整設定檔，使用 general、vehicle_types、line_counting 區段。
            lines_file: 計數線設定檔路徑。
        """
        general_cfg = config["general"]
        line_cfg = config["line_counting"]

        self.min_track_life_secs = float(general_cfg["min_track_life_secs"])
        self.min_vote_count = int(general_cfg["min_vote_count"])
        self.anchor_mode = str(line_cfg.get("anchor", ANCHOR_BOTTOM_CENTER))

        self.vehicle_types = VehicleTypeRegistry(config["vehicle_types"])

        loaded = load_lines(lines_file)
        self.inside_point = loaded["inside_point"]
        self.lines = loaded["lines"]

        # {追蹤編號: {"prev": 上一幀代表點, "crossings": [(時間, 線編號, 方向)], "live": 已計入即時統計的筆數}}
        self._states: dict = {}

        # 即時統計 {線編號: {"進入": n, "離開": n}}
        self.live_counts = {
            line_id: {"進入": 0, "離開": 0} for line_id in self.lines
        }

        logger.info("越線計數已啟用，計數線 %d 條：%s", len(self.lines),
                    [line["name"] for line in self.lines.values()])

    @profile_time
    def process(self, element):
        """偵測本幀的越線事件，並結算已離場軌跡的越線紀錄。"""
        if not isinstance(element, StreamEndElement):
            for track_id, track in element.active_tracks.items():
                self._observe(track_id, track, element.timestamp)

        records = []
        for track in element.retired_tracks:
            records.extend(self._finalize(track))

        element.line_events = records
        element.statistics["越線計數"] = self._build_statistics()
        return element

    # ------------------------------------------------------------------
    # 越線偵測
    # ------------------------------------------------------------------
    def _observe(self, track_id: int, track, timestamp: float) -> None:
        """比對軌跡前後兩幀的位置，記錄新發生的越線。"""
        if track.last_xyxy is None:
            return

        current = anchor_point(track.last_xyxy, self.anchor_mode)
        state = self._states.get(track_id)
        if state is None:
            self._states[track_id] = {"prev": current, "crossings": [], "live": 0}
            return

        previous = state["prev"]
        state["prev"] = current

        for line_id, line in self.lines.items():
            direction = crossing_direction(
                previous, current, line["p1"], line["p2"], self.inside_point
            )
            if direction is None:
                continue
            # 車輛在線上抖動會反覆跨越，同一條線同一方向每台車只記一次
            if any(c[1] == line_id and c[2] == direction for c in state["crossings"]):
                continue
            state["crossings"].append((timestamp, line_id, direction))

        self._flush_live(track, state)

    def _is_eligible(self, track) -> bool:
        """軌跡是否達到計數門檻（與 CountingNode 相同的兩項條件）。"""
        return (
            track.lifetime >= self.min_track_life_secs
            and track.vote_count >= self.min_vote_count
        )

    def _flush_live(self, track, state: dict) -> None:
        """軌跡達門檻後，把尚未計入的越線補進即時統計。"""
        if not self._is_eligible(track):
            return
        for _, line_id, direction in state["crossings"][state["live"]:]:
            self.live_counts[line_id][direction] += 1
        state["live"] = len(state["crossings"])

    def _finalize(self, track) -> list:
        """軌跡離場時產生最終越線紀錄；未達門檻的軌跡整筆捨棄。"""
        state = self._states.pop(track.track_id, None)
        if state is None or not state["crossings"]:
            return []
        if not self._is_eligible(track):
            return []

        # 離場前最後一幀才達門檻的情況：補齊即時統計，確保與最終紀錄一致
        self._flush_live(track, state)

        vehicle_type = track.vehicle_type or self.vehicle_types.unknown_label
        pcu = self.vehicle_types.pcu_of(vehicle_type)

        return [
            {
                "追蹤編號": track.track_id,
                "時間_秒": round(timestamp, 2),
                "計數線": line_id,
                "計數線名稱": self.lines[line_id]["name"],
                "方向": direction,
                "車種": vehicle_type,
                "PCU": pcu,
            }
            for timestamp, line_id, direction in state["crossings"]
        ]

    def _build_statistics(self) -> dict:
        """彙整供畫面顯示的即時越線統計。"""
        return {
            line_id: {
                "名稱": self.lines[line_id]["name"],
                "進入": counts["進入"],
                "離開": counts["離開"],
            }
            for line_id, counts in self.live_counts.items()
        }
