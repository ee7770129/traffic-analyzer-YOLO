# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：準確度驗證工具
功能說明：
    比對人工計數與系統計數，產出誤差率報表。

    任何自動計數系統在正式引用前都必須先證明自己夠準，
    本工具把「人工數一遍、跟系統比對、算出誤差率」這個流程自動化。

    系統計數直接由 車輛明細.csv 逐筆聚合而來（而非讀取彙總表），
    確保驗證結果與原始紀錄完全同源，不會因彙總邏輯而失真。

使用方式：
    步驟一　產生人工計數範本（依系統實際偵測到的道路與車種預先列好欄位）
        python tools/accuracy_check.py --template outputs/20250224_143052

    步驟二　開啟 人工計數.csv，看著影片把每一格的數字填上

    步驟三　比對並產出誤差報表
        python tools/accuracy_check.py --result outputs/20250224_143052 \
                                       --manual outputs/20250224_143052/人工計數.csv

建立日期：2026-10-03
版本號：v1.0.0
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

# UTF-8 with BOM：Excel 直接雙擊開啟才不會變成亂碼
_ENCODING = "utf-8-sig"

_DETAIL_FILE = "車輛明細.csv"
_TEMPLATE_FILE = "人工計數.csv"
_REPORT_FILE = "準確度驗證.csv"

_COL_ROAD = "道路"
_COL_TYPE = "車種"
_COL_MANUAL = "人工計數"


# ----------------------------------------------------------------------
# 讀取
# ----------------------------------------------------------------------
def resolve_detail_path(result_path: str) -> str:
    """接受資料夾或直接指定 車輛明細.csv，統一回傳檔案路徑。"""
    if os.path.isdir(result_path):
        return os.path.join(result_path, _DETAIL_FILE)
    return result_path


def load_system_counts(detail_path: str) -> dict:
    """
    從車輛明細聚合出系統計數。

    只採計「是否計入統計 = 是」的車輛，與主程式的統計母體完全一致。

    回傳：
        {(道路, 車種): 數量}
    """
    if not os.path.isfile(detail_path):
        raise FileNotFoundError(f"找不到車輛明細：{detail_path}")

    counts = defaultdict(int)
    with open(detail_path, encoding=_ENCODING, newline="") as file:
        for row in csv.DictReader(file):
            if row.get("是否計入統計", "").strip() != "是":
                continue
            road = (row.get("進入道路") or "").strip()
            vehicle = (row.get("車種") or "").strip()
            if not road:
                continue
            counts[(road, vehicle or "其他車種")] += 1

    if not counts:
        raise ValueError(f"車輛明細中沒有任何計入統計的車輛：{detail_path}")
    return dict(counts)


def load_manual_counts(manual_path: str) -> tuple:
    """
    讀取人工計數。

    支援兩種格式：
        含車種：道路, 車種, 人工計數   → 逐車種比對
        僅道路：道路, 人工計數        → 只比對各道路總量

    回傳：
        ({(道路, 車種或 None): 數量}, 是否逐車種比對)
    """
    if not os.path.isfile(manual_path):
        raise FileNotFoundError(f"找不到人工計數檔：{manual_path}")

    with open(manual_path, encoding=_ENCODING, newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]

        if _COL_ROAD not in fieldnames or _COL_MANUAL not in fieldnames:
            raise ValueError(
                f"人工計數檔必須包含「{_COL_ROAD}」與「{_COL_MANUAL}」欄位，"
                f"目前為：{fieldnames}"
            )

        by_type = _COL_TYPE in fieldnames
        counts = defaultdict(int)

        for row in reader:
            road = (row.get(_COL_ROAD) or "").strip()
            if not road or road.startswith("全部"):
                continue  # 略過空列與合計列
            raw = (row.get(_COL_MANUAL) or "").strip()
            if raw == "":
                continue  # 尚未填寫的格子視為未驗證，不當成 0
            try:
                value = int(float(raw))
            except ValueError:
                raise ValueError(f"人工計數必須是數字，但讀到「{raw}」（道路 {road}）")

            key = (road, (row.get(_COL_TYPE) or "").strip()) if by_type else (road, None)
            counts[key] += value

    if not counts:
        raise ValueError(f"人工計數檔沒有任何已填寫的數字：{manual_path}")
    return dict(counts), by_type


# ----------------------------------------------------------------------
# 範本產生
# ----------------------------------------------------------------------
def write_template(detail_path: str, output_path: str) -> str:
    """
    依系統實際偵測到的道路與車種，產生待填寫的人工計數範本。

    預先列好所有組合，使用者只要對著影片把數字填進最後一欄即可。
    """
    system = load_system_counts(detail_path)
    roads = sorted({road for road, _ in system}, key=lambda r: (len(r), r))
    types = sorted({vehicle for _, vehicle in system})

    rows = [{_COL_ROAD: road, _COL_TYPE: vehicle, _COL_MANUAL: ""}
            for road in roads for vehicle in types]

    with open(output_path, "w", encoding=_ENCODING, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[_COL_ROAD, _COL_TYPE, _COL_MANUAL])
        writer.writeheader()
        writer.writerows(rows)

    return output_path


# ----------------------------------------------------------------------
# 比對
# ----------------------------------------------------------------------
def compare(system: dict, manual: dict, by_type: bool) -> list:
    """
    比對兩組計數，產出逐項結果。

    回傳的每一列包含人工值、系統值、誤差、絕對誤差與誤差率。
    誤差率以人工計數為分母（人工值視為真值）；人工為 0 時不計算百分比。
    """
    if not by_type:
        # 僅比對道路總量，先把系統計數依道路加總
        collapsed = defaultdict(int)
        for (road, _), count in system.items():
            collapsed[(road, None)] += count
        system = dict(collapsed)

    keys = sorted(set(system) | set(manual), key=lambda k: (len(k[0]), k[0], k[1] or ""))

    rows = []
    for road, vehicle in keys:
        manual_value = manual.get((road, vehicle), 0)
        system_value = system.get((road, vehicle), 0)
        diff = system_value - manual_value
        rate = f"{abs(diff) / manual_value * 100:.1f}%" if manual_value else "—"

        row = {"道路": road}
        if by_type:
            row["車種"] = vehicle
        row.update({
            "人工計數": manual_value,
            "系統計數": system_value,
            "誤差": diff,
            "絕對誤差": abs(diff),
            "誤差率": rate,
        })
        rows.append(row)

    return rows


def summarise(rows: list) -> dict:
    """計算整體指標。"""
    manual_total = sum(r["人工計數"] for r in rows)
    system_total = sum(r["系統計數"] for r in rows)
    abs_errors = [r["絕對誤差"] for r in rows]

    # MAPE 只納入人工計數不為零的項目，否則分母為零
    rates = [r["絕對誤差"] / r["人工計數"] for r in rows if r["人工計數"]]

    return {
        "項目數": len(rows),
        "人工總計": manual_total,
        "系統總計": system_total,
        "總量誤差": system_total - manual_total,
        "總量誤差率": (abs(system_total - manual_total) / manual_total * 100
                      if manual_total else 0.0),
        "總量準確率": ((1 - abs(system_total - manual_total) / manual_total) * 100
                      if manual_total else 0.0),
        "平均絕對誤差": sum(abs_errors) / len(abs_errors) if abs_errors else 0.0,
        "最大絕對誤差": max(abs_errors) if abs_errors else 0,
        "分項MAPE": sum(rates) / len(rates) * 100 if rates else 0.0,
    }


# ----------------------------------------------------------------------
# 輸出
# ----------------------------------------------------------------------
def write_report(rows: list, metrics: dict, by_type: bool, output_path: str) -> str:
    """輸出誤差報表 CSV。"""
    fieldnames = ["道路"] + (["車種"] if by_type else []) + [
        "人工計數", "系統計數", "誤差", "絕對誤差", "誤差率"
    ]

    with open(output_path, "w", encoding=_ENCODING, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

        total = {"道路": "全部合計",
                 "人工計數": metrics["人工總計"],
                 "系統計數": metrics["系統總計"],
                 "誤差": metrics["總量誤差"],
                 "絕對誤差": abs(metrics["總量誤差"]),
                 "誤差率": f"{metrics['總量誤差率']:.1f}%"}
        if by_type:
            total["車種"] = ""
        writer.writerow(total)

        writer.writerow({})
        for label, value in (
            ("總量準確率", f"{metrics['總量準確率']:.1f}%"),
            ("分項MAPE", f"{metrics['分項MAPE']:.1f}%"),
            ("平均絕對誤差", f"{metrics['平均絕對誤差']:.2f} 輛"),
            ("最大絕對誤差", f"{metrics['最大絕對誤差']} 輛"),
        ):
            writer.writerow({"道路": f"{label}：{value}"})

    return output_path


def print_summary(rows: list, metrics: dict, by_type: bool) -> None:
    """在主控台印出比對結果。"""
    print("")
    print("=" * 62)
    print("  準確度驗證結果")
    print("=" * 62)

    header = f"  {'道路':<6}" + (f"{'車種':<10}" if by_type else "")
    print(header + f"{'人工':>6}{'系統':>6}{'誤差':>6}{'誤差率':>9}")
    print("  " + "-" * 58)

    for row in rows:
        line = f"  {row['道路']:<6}" + (f"{row.get('車種', ''):<10}" if by_type else "")
        line += f"{row['人工計數']:>6}{row['系統計數']:>6}{row['誤差']:>+6}{row['誤差率']:>9}"
        print(line)

    print("  " + "-" * 58)
    print(f"  {'合計':<6}" + (f"{'':<10}" if by_type else "")
          + f"{metrics['人工總計']:>6}{metrics['系統總計']:>6}"
            f"{metrics['總量誤差']:>+6}{metrics['總量誤差率']:>8.1f}%")
    print("=" * 62)
    print(f"  總量準確率　　：{metrics['總量準確率']:.1f}%")
    print(f"  分項 MAPE　　 ：{metrics['分項MAPE']:.1f}%")
    print(f"  平均絕對誤差　：{metrics['平均絕對誤差']:.2f} 輛")
    print(f"  最大絕對誤差　：{metrics['最大絕對誤差']} 輛")
    print("=" * 62)
    print("")


# ----------------------------------------------------------------------
# 進入點
# ----------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="準確度驗證：比對人工計數與系統計數，產出誤差率報表。"
    )
    parser.add_argument(
        "--result", required=True,
        help="分析結果資料夾（outputs/<執行時間>），或直接指定 車輛明細.csv",
    )
    parser.add_argument(
        "--manual",
        help="人工計數 CSV 的路徑。未指定時預設為結果資料夾中的 人工計數.csv",
    )
    parser.add_argument(
        "--output",
        help="誤差報表的輸出路徑。未指定時寫入結果資料夾中的 準確度驗證.csv",
    )
    parser.add_argument(
        "--template", action="store_true",
        help="只產生待填寫的人工計數範本，不進行比對",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    detail_path = resolve_detail_path(args.result)
    base_dir = args.result if os.path.isdir(args.result) else os.path.dirname(detail_path)

    try:
        if args.template:
            output = args.output or os.path.join(base_dir, _TEMPLATE_FILE)
            path = write_template(detail_path, output)
            print(f"\n已產生人工計數範本：{path}")
            print("請開啟該檔案，對著影片把每一列的「人工計數」欄位填上數字，")
            print("再執行不帶 --template 的比對指令。\n")
            return 0

        manual_path = args.manual or os.path.join(base_dir, _TEMPLATE_FILE)
        system = load_system_counts(detail_path)
        manual, by_type = load_manual_counts(manual_path)

        rows = compare(system, manual, by_type)
        metrics = summarise(rows)

        output = args.output or os.path.join(base_dir, _REPORT_FILE)
        write_report(rows, metrics, by_type, output)

        print_summary(rows, metrics, by_type)
        print(f"  誤差報表已輸出：{os.path.abspath(output)}\n")
        return 0

    except (FileNotFoundError, ValueError) as error:
        print(f"\n[錯誤] {error}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
