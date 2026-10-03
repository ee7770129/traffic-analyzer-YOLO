# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：統計報表輸出節點
功能說明：
    蒐集已離場的車輛軌跡，於分析結束時輸出四份 CSV 報表：

        1. 車輛明細.csv：每台車一列，含進出道路、車種、時間，可與影片逐筆核對。
        2. 時段流量.csv：依設定的時間區間彙總各道路、各車種的車次與 PCU。
        3. 轉向矩陣.csv：進入道路 × 離開道路 的轉向 OD 矩陣。
        4. 統計總表.csv：全時段彙總，含各道路車次、車種組成、PCU 與平均流率。

資料來源的設計決策：
    四份報表一律由「已離場的軌跡紀錄」推導，而非由計數當下發出的事件。

    原因是計數發生在軌跡剛達門檻時（可能只有 5 票），
    而離場時的車種多數決往往已累積數百票，可靠得多。
    改以軌跡紀錄為單一事實來源後，四份報表彼此必定一致，
    且都採用最可靠的那個版本的車種判定。

    所有 CSV 皆以 UTF-8 with BOM 編碼輸出，確保在 Windows 的 Excel
    直接雙擊開啟時中文不會變成亂碼。

建立日期：2025-02-05
最後更新：2026-10-03（改為以軌跡紀錄為單一事實來源）
版本號：v1.1.0
"""

import csv
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime

from core.stream_end_element import StreamEndElement
from utils.profiler import profile_time
from utils.vehicle_types import VehicleTypeRegistry

logger = logging.getLogger(__name__)


class ReportNode:
    """統計報表蒐集與輸出。"""

    def __init__(self, config: dict, run_dir: str) -> None:
        """
        參數：
            config:  完整設定檔，使用 report_node 與 vehicle_types 區段。
            run_dir: 本次執行的輸出資料夾，由主程式統一建立，
                     讓報表與成果影片集中於同一批次目錄下。
        """
        report_cfg = config["report_node"]

        self.run_dir = run_dir
        self.interval_seconds = float(report_cfg["interval_seconds"])
        # Excel 需要 BOM 才會正確判讀 UTF-8，否則中文欄位會變亂碼
        self.encoding = str(report_cfg.get("csv_encoding", "utf-8-sig"))

        self.vehicle_types = VehicleTypeRegistry(config["vehicle_types"])

        self._vehicles: list = []     # 所有已離場的 TrackElement
        self._road_ids: set = set()
        self._last_timestamp = 0.0
        self._finalized = False

    @profile_time
    def process(self, element):
        """累積離場軌跡；收到結束訊號時輸出報表。"""
        self._collect(element)

        if isinstance(element, StreamEndElement) and not self._finalized:
            self.finalize()

        return element

    # ------------------------------------------------------------------
    # 資料蒐集
    # ------------------------------------------------------------------
    def _collect(self, element) -> None:
        """把本幀離場的軌跡收進暫存。"""
        self._last_timestamp = max(self._last_timestamp, element.timestamp)

        for track in element.retired_tracks:
            self._vehicles.append(track)
            if track.entry_road is not None:
                self._road_ids.add(track.entry_road)
            if track.exit_road is not None:
                self._road_ids.add(track.exit_road)

    @property
    def _counted(self) -> list:
        """通過計數門檻的軌跡，是所有統計報表的母體。"""
        return [t for t in self._vehicles if t.counted_entry]

    def _type_of(self, track) -> str:
        """取得軌跡的最終車種，未能判定時歸入未知類別。"""
        return track.vehicle_type or self.vehicle_types.unknown_label

    # ------------------------------------------------------------------
    # 報表輸出
    # ------------------------------------------------------------------
    def finalize(self) -> str:
        """輸出所有報表，回傳輸出資料夾路徑。"""
        self._finalized = True
        os.makedirs(self.run_dir, exist_ok=True)

        self._write_vehicle_details()
        self._write_interval_flow()
        self._write_od_matrix()
        self._write_summary()

        logger.info("統計報表已輸出至：%s", os.path.abspath(self.run_dir))
        return self.run_dir

    def _write_csv(self, filename: str, fieldnames: list, rows: list) -> None:
        """共用的 CSV 寫檔流程，統一編碼與換行設定。"""
        path = os.path.join(self.run_dir, filename)
        # newline="" 為 csv 模組在 Windows 的必要設定，否則會多出空白列
        with open(path, "w", encoding=self.encoding, newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info("已輸出 %s（%d 列）", filename, len(rows))

    def _write_vehicle_details(self) -> None:
        """輸出車輛明細：每台車一列，供人工抽查與準確度驗證。"""
        fieldnames = [
            "追蹤編號", "車種", "進入道路", "進入時間_秒", "離開道路", "離開時間_秒",
            "首次出現_秒", "最後出現_秒", "存活秒數", "辨識幀數", "區域序列", "是否計入統計",
        ]
        rows = []
        for track in self._vehicles:
            record = track.to_record()
            record["是否計入統計"] = "是" if track.counted_entry else "否"
            rows.append(record)

        rows.sort(key=lambda r: r["追蹤編號"])
        self._write_csv("車輛明細.csv", fieldnames, rows)

    def _write_interval_flow(self) -> None:
        """輸出時段流量：時間區間 × 道路 × 車種的車次與 PCU。"""
        vehicle_labels = self.vehicle_types.labels
        roads = self._sorted_roads()

        # {(區間索引, 道路): Counter(車種)}
        buckets: dict = defaultdict(Counter)
        for track in self._counted:
            bucket_index = int(track.entry_timestamp // self.interval_seconds)
            buckets[(bucket_index, track.entry_road)][self._type_of(track)] += 1

        fieldnames = ["時段起_秒", "時段迄_秒", "道路"] + vehicle_labels + ["小計", "PCU小計"]
        rows = []

        for bucket_index in range(self._total_bucket_count()):
            start = bucket_index * self.interval_seconds
            for road in roads:
                counter = buckets.get((bucket_index, road), Counter())
                row = {
                    "時段起_秒": round(start, 1),
                    "時段迄_秒": round(start + self.interval_seconds, 1),
                    "道路": road,
                }
                subtotal = 0
                pcu_subtotal = 0.0
                for label in vehicle_labels:
                    count = counter.get(label, 0)
                    row[label] = count
                    subtotal += count
                    pcu_subtotal += count * self.vehicle_types.pcu_of(label)
                row["小計"] = subtotal
                row["PCU小計"] = round(pcu_subtotal, 1)
                rows.append(row)

        self._write_csv("時段流量.csv", fieldnames, rows)

    def _write_od_matrix(self) -> None:
        """輸出轉向 OD 矩陣：列為進入道路、欄為離開道路。"""
        roads = self._sorted_roads()

        matrix: dict = defaultdict(int)
        for track in self._counted:
            if track.counted_movement:
                matrix[(track.entry_road, track.exit_road)] += 1

        fieldnames = ["進入道路＼離開道路"] + [f"往道路{road}" for road in roads] + ["合計"]
        rows = []
        for entry_road in roads:
            row = {"進入道路＼離開道路": f"道路{entry_road}"}
            total = 0
            for exit_road in roads:
                count = matrix.get((entry_road, exit_road), 0)
                row[f"往道路{exit_road}"] = count
                total += count
            row["合計"] = total
            rows.append(row)

        # 補一列欄位合計，方便直接讀出各方向的流出總量
        footer = {"進入道路＼離開道路": "合計"}
        grand_total = 0
        for exit_road in roads:
            column_total = sum(matrix.get((e, exit_road), 0) for e in roads)
            footer[f"往道路{exit_road}"] = column_total
            grand_total += column_total
        footer["合計"] = grand_total
        rows.append(footer)

        self._write_csv("轉向矩陣.csv", fieldnames, rows)

    def _write_summary(self) -> None:
        """輸出統計總表：全時段各道路的車次、車種組成、PCU 與平均流率。"""
        vehicle_labels = self.vehicle_types.labels
        roads = self._sorted_roads()
        duration = max(self._last_timestamp, 1e-6)
        duration_hours = duration / 3600.0

        per_road: dict = defaultdict(Counter)
        for track in self._counted:
            per_road[track.entry_road][self._type_of(track)] += 1

        fieldnames = (
            ["道路"] + vehicle_labels + ["車次合計", "PCU合計", "平均流率_輛每小時", "組成佔比"]
        )
        rows = []
        grand_counter = Counter()

        for road in roads:
            counter = per_road.get(road, Counter())
            grand_counter.update(counter)
            row = {"道路": f"道路{road}"}
            subtotal = 0
            pcu_subtotal = 0.0
            for label in vehicle_labels:
                count = counter.get(label, 0)
                row[label] = count
                subtotal += count
                pcu_subtotal += count * self.vehicle_types.pcu_of(label)
            row["車次合計"] = subtotal
            row["PCU合計"] = round(pcu_subtotal, 1)
            row["平均流率_輛每小時"] = round(subtotal / duration_hours, 1)
            rows.append(row)

        total_vehicles = sum(grand_counter.values())
        for row in rows:
            row["組成佔比"] = (
                f"{row['車次合計'] / total_vehicles * 100:.1f}%" if total_vehicles else "0.0%"
            )

        # 全路口合計列
        total_row = {"道路": "全部合計"}
        total_pcu = 0.0
        for label in vehicle_labels:
            count = grand_counter.get(label, 0)
            total_row[label] = count
            total_pcu += count * self.vehicle_types.pcu_of(label)
        total_row["車次合計"] = total_vehicles
        total_row["PCU合計"] = round(total_pcu, 1)
        total_row["平均流率_輛每小時"] = round(total_vehicles / duration_hours, 1)
        total_row["組成佔比"] = "100.0%" if total_vehicles else "0.0%"
        rows.append(total_row)

        movements = sum(1 for t in self._counted if t.counted_movement)

        # 分析條件列，讓報表本身即可交代數據產生的前提
        rows.append({"道路": ""})
        rows.append({"道路": f"分析時長_秒：{round(duration, 1)}"})
        rows.append({"道路": f"統計區間_秒：{round(self.interval_seconds, 1)}"})
        rows.append({"道路": f"轉向紀錄筆數：{movements}"})
        rows.append({"道路": f"未計入統計的軌跡數：{len(self._vehicles) - len(self._counted)}"})
        rows.append({"道路": f"報表產生時間：{datetime.now():%Y-%m-%d %H:%M:%S}"})

        self._write_csv("統計總表.csv", fieldnames, rows)

    # ------------------------------------------------------------------
    # 輔助
    # ------------------------------------------------------------------
    def _sorted_roads(self) -> list:
        """回傳排序後的道路編號，確保各報表欄位順序一致。"""
        return sorted(self._road_ids)

    def _total_bucket_count(self) -> int:
        """計算需要輸出幾個時間區間，至少一個。"""
        if self.interval_seconds <= 0:
            return 1
        return max(1, int(self._last_timestamp // self.interval_seconds) + 1)
