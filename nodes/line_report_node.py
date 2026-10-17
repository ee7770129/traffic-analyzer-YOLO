# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：越線計數報表輸出節點
功能說明：
    蒐集 LineCountingNode 產生的越線紀錄，於分析結束時輸出三份 CSV：

        1. 越線明細.csv：每次越線一列，可與影片逐筆核對。
        2. 越線計數.csv：計數線 × 方向 × 車種 的車次與 PCU。
        3. 越線轉向矩陣.csv：由哪條線進入、由哪條線離開的 OD 矩陣。

    轉向的定義：同一台車的「第一次進入」與其後「最後一次離開」配成一筆。
    只有進入或只有離開的車輛不計入轉向矩陣。

建立日期：2026-10-08
版本號：v1.2.0
"""

import csv
import logging
import os
from collections import defaultdict

from core.stream_end_element import StreamEndElement
from utils.line_geometry import DIRECTION_IN, DIRECTION_OUT
from utils.profiler import profile_time

logger = logging.getLogger(__name__)

_DETAIL_FIELDS = ["追蹤編號", "時間_秒", "計數線", "計數線名稱", "方向", "車種", "PCU"]


def build_line_movements(records: list) -> dict:
    """
    由越線紀錄推導轉向矩陣。

    回傳：
        {(進入線編號, 離開線編號): 車輛數}
    """
    by_track = defaultdict(list)
    for record in records:
        by_track[record["追蹤編號"]].append(record)

    movements = defaultdict(int)
    for track_records in by_track.values():
        ordered = sorted(track_records, key=lambda r: r["時間_秒"])
        entries = [r for r in ordered if r["方向"] == DIRECTION_IN]
        if not entries:
            continue
        first_entry = entries[0]
        exits = [
            r for r in ordered
            if r["方向"] == DIRECTION_OUT and r["時間_秒"] >= first_entry["時間_秒"]
        ]
        if not exits:
            continue
        movements[(first_entry["計數線"], exits[-1]["計數線"])] += 1
    return dict(movements)


class LineReportNode:
    """越線計數報表蒐集與輸出。"""

    def __init__(self, config: dict, run_dir: str) -> None:
        """
        參數：
            config:  完整設定檔，使用 report_node 區段的 csv_encoding。
            run_dir: 本次執行的輸出資料夾。
        """
        self.run_dir = run_dir
        self.encoding = str(config["report_node"].get("csv_encoding", "utf-8-sig"))
        self._records: list = []
        self._line_names: dict = {}

    @profile_time
    def process(self, element):
        """累積越線紀錄；收到結束訊號時輸出報表。"""
        self._records.extend(getattr(element, "line_events", []) or [])

        # 即時統計內含全部計數線名稱，沒有車通過的線也要出現在報表中
        for line_id, info in (element.statistics.get("越線計數") or {}).items():
            self._line_names[line_id] = info["名稱"]

        if isinstance(element, StreamEndElement):
            self.write_reports()
        return element

    # ------------------------------------------------------------------
    # 報表輸出
    # ------------------------------------------------------------------
    def write_reports(self) -> None:
        """輸出三份越線報表。"""
        os.makedirs(self.run_dir, exist_ok=True)
        self._write_detail()
        self._write_summary()
        self._write_matrix()
        logger.info("越線報表已輸出（越線 %d 筆）：%s",
                    len(self._records), os.path.abspath(self.run_dir))

    def _open(self, filename: str):
        return open(os.path.join(self.run_dir, filename), "w",
                    newline="", encoding=self.encoding)

    def _write_detail(self) -> None:
        with self._open("越線明細.csv") as file:
            writer = csv.DictWriter(file, fieldnames=_DETAIL_FIELDS)
            writer.writeheader()
            for record in sorted(self._records, key=lambda r: r["時間_秒"]):
                writer.writerow(record)

    def _write_summary(self) -> None:
        totals = defaultdict(lambda: {"車次": 0, "PCU": 0.0})
        for record in self._records:
            key = (record["計數線"], record["方向"], record["車種"])
            totals[key]["車次"] += 1
            totals[key]["PCU"] += float(record["PCU"])

        with self._open("越線計數.csv") as file:
            writer = csv.writer(file)
            writer.writerow(["計數線", "計數線名稱", "方向", "車種", "車次", "PCU"])
            for line_id in sorted(self._line_names):
                for direction in (DIRECTION_IN, DIRECTION_OUT):
                    rows = sorted(
                        (k, v) for k, v in totals.items()
                        if k[0] == line_id and k[1] == direction
                    )
                    for (_, _, vehicle_type), value in rows:
                        writer.writerow([line_id, self._line_names[line_id], direction,
                                         vehicle_type, value["車次"], round(value["PCU"], 1)])
                    subtotal = sum(v["車次"] for _, v in rows)
                    subtotal_pcu = sum(v["PCU"] for _, v in rows)
                    writer.writerow([line_id, self._line_names[line_id], direction,
                                     "合計", subtotal, round(subtotal_pcu, 1)])

    def _write_matrix(self) -> None:
        movements = build_line_movements(self._records)
        line_ids = sorted(self._line_names)

        with self._open("越線轉向矩陣.csv") as file:
            writer = csv.writer(file)
            writer.writerow(["進入＼離開"] + [self._line_names[i] for i in line_ids] + ["合計"])
            for origin in line_ids:
                row = [movements.get((origin, destination), 0) for destination in line_ids]
                writer.writerow([self._line_names[origin]] + row + [sum(row)])
            column_totals = [
                sum(movements.get((origin, destination), 0) for origin in line_ids)
                for destination in line_ids
            ]
            writer.writerow(["合計"] + column_totals + [sum(column_totals)])
