# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：尖峰小時係數報表節點
功能說明：
    蒐集每台車的進入時間，分析結束時計算尖峰小時係數（PHF）並輸出 CSV。

    以軌跡離場時的最終紀錄為資料來源，與 ReportNode 採用相同的母體
    （已計入進入流量的車輛），確保 PHF 的流量與統計總表對得起來。

    觀測長度不足一小時時不計算，報表會寫明原因，不以外插值充數。

建立日期：2026-10-08
版本號：v1.2.0
"""

import csv
import logging
import os

from core.stream_end_element import StreamEndElement
from utils.phf import compute_phf
from utils.profiler import profile_time

logger = logging.getLogger(__name__)

_ALL_ROADS = "全路口"


class PhfReportNode:
    """尖峰小時係數計算與輸出。"""

    def __init__(self, config: dict, run_dir: str) -> None:
        """
        參數：
            config:  完整設定檔，使用 phf_node 與 report_node 區段。
            run_dir: 本次執行的輸出資料夾。
        """
        phf_cfg = config["phf_node"]

        self.run_dir = run_dir
        self.period_secs = float(phf_cfg["period_secs"])
        self.periods_per_hour = int(phf_cfg["periods_per_hour"])
        self.encoding = str(config["report_node"].get("csv_encoding", "utf-8-sig"))

        self._entries: list = []   # [(進入道路, 進入時間)]
        self.output_path = os.path.join(self.run_dir, "尖峰小時係數.csv")

    @profile_time
    def process(self, element):
        """累積已離場且已計入的車輛；收到結束訊號時輸出報表。"""
        for track in element.retired_tracks:
            if track.counted_entry and track.entry_timestamp is not None:
                self._entries.append((track.entry_road, track.entry_timestamp))

        if isinstance(element, StreamEndElement):
            self.write_report(element.timestamp)
        return element

    def build_rows(self, duration_secs: float) -> list:
        """計算全路口與各道路的 PHF，回傳報表列。"""
        groups = {_ALL_ROADS: [timestamp for _, timestamp in self._entries]}
        for road, timestamp in self._entries:
            groups.setdefault(f"道路 {road}", []).append(timestamp)

        rows = []
        for name, timestamps in groups.items():
            result = compute_phf(
                timestamps, duration_secs, self.period_secs, self.periods_per_hour
            )
            if result is None:
                rows.append([name, len(timestamps), "", "", "", "",
                             "觀測不足一小時或尖峰小時內無車，無法計算"])
                continue
            rows.append([
                name,
                len(timestamps),
                result["尖峰起始_秒"],
                result["尖峰小時流量"],
                result["最大區間流量"],
                result["PHF"],
                "",
            ])
        return rows

    def write_report(self, duration_secs: float) -> None:
        """輸出尖峰小時係數報表。"""
        os.makedirs(self.run_dir, exist_ok=True)
        with open(self.output_path, "w", newline="", encoding=self.encoding) as file:
            writer = csv.writer(file)
            writer.writerow(["範圍", "觀測車次", "尖峰起始_秒", "尖峰小時流量",
                             "最大區間流量", "PHF", "備註"])
            writer.writerows(self.build_rows(duration_secs))
        logger.info("尖峰小時係數報表已輸出：%s", os.path.abspath(self.output_path))
