# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：tools/accuracy_check.py 的單元測試
功能說明：
    驗證準確度驗證工具本身的正確性。

    這個工具是用來證明系統夠準的，如果它自己算錯，
    整個驗證就失去意義，因此誤差指標需逐一以手算值確認。

建立日期：2026-10-03
版本號：v1.0.0
"""

import csv
import os

import pytest

from tools.accuracy_check import (
    compare,
    load_manual_counts,
    load_system_counts,
    resolve_detail_path,
    summarise,
    write_report,
    write_template,
)

_ENCODING = "utf-8-sig"


def write_detail(path, rows):
    """寫出一份最小可用的車輛明細 CSV。"""
    fields = ["追蹤編號", "車種", "進入道路", "是否計入統計"]
    with open(path, "w", encoding=_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_manual(path, rows, fields):
    with open(path, "w", encoding=_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def detail_csv(tmp_path):
    path = tmp_path / "車輛明細.csv"
    write_detail(path, [
        {"追蹤編號": 1, "車種": "小客車", "進入道路": "1", "是否計入統計": "是"},
        {"追蹤編號": 2, "車種": "小客車", "進入道路": "1", "是否計入統計": "是"},
        {"追蹤編號": 3, "車種": "機車", "進入道路": "1", "是否計入統計": "是"},
        {"追蹤編號": 4, "車種": "小客車", "進入道路": "2", "是否計入統計": "是"},
        # 未計入統計者不應被納入系統計數
        {"追蹤編號": 5, "車種": "小客車", "進入道路": "2", "是否計入統計": "否"},
        # 沒有進入道路者應被略過
        {"追蹤編號": 6, "車種": "小客車", "進入道路": "", "是否計入統計": "是"},
    ])
    return str(path)


class TestLoadSystemCounts:
    """系統計數聚合。"""

    def test_只採計已計入統計的車輛(self, detail_csv):
        counts = load_system_counts(detail_csv)
        assert counts[("1", "小客車")] == 2
        assert counts[("1", "機車")] == 1
        assert counts[("2", "小客車")] == 1
        assert sum(counts.values()) == 4

    def test_略過沒有進入道路的車輛(self, detail_csv):
        counts = load_system_counts(detail_csv)
        assert all(road != "" for road, _ in counts)

    def test_檔案不存在時拋出例外(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="找不到車輛明細"):
            load_system_counts(str(tmp_path / "不存在.csv"))

    def test_全部未計入時拋出例外(self, tmp_path):
        path = tmp_path / "空.csv"
        write_detail(path, [{"追蹤編號": 1, "車種": "小客車",
                             "進入道路": "1", "是否計入統計": "否"}])
        with pytest.raises(ValueError, match="沒有任何計入統計"):
            load_system_counts(str(path))


class TestResolveDetailPath:
    """路徑解析。"""

    def test_傳入資料夾時自動接上檔名(self, tmp_path, detail_csv):
        assert resolve_detail_path(str(tmp_path)).endswith("車輛明細.csv")

    def test_傳入檔案時原樣回傳(self, detail_csv):
        assert resolve_detail_path(detail_csv) == detail_csv


class TestLoadManualCounts:
    """人工計數讀取。"""

    def test_含車種格式(self, tmp_path):
        path = tmp_path / "人工.csv"
        write_manual(path, [
            {"道路": "1", "車種": "小客車", "人工計數": "3"},
            {"道路": "1", "車種": "機車", "人工計數": "1"},
        ], ["道路", "車種", "人工計數"])

        counts, by_type = load_manual_counts(str(path))
        assert by_type is True
        assert counts[("1", "小客車")] == 3

    def test_僅道路格式(self, tmp_path):
        path = tmp_path / "人工.csv"
        write_manual(path, [{"道路": "1", "人工計數": "4"}], ["道路", "人工計數"])

        counts, by_type = load_manual_counts(str(path))
        assert by_type is False
        assert counts[("1", None)] == 4

    def test_未填寫的格子不視為零(self, tmp_path):
        """空白代表尚未驗證，當成 0 會讓誤差率嚴重失真。"""
        path = tmp_path / "人工.csv"
        write_manual(path, [
            {"道路": "1", "車種": "小客車", "人工計數": "3"},
            {"道路": "1", "車種": "機車", "人工計數": ""},
        ], ["道路", "車種", "人工計數"])

        counts, _ = load_manual_counts(str(path))
        assert ("1", "機車") not in counts

    def test_略過合計列(self, tmp_path):
        path = tmp_path / "人工.csv"
        write_manual(path, [
            {"道路": "1", "人工計數": "4"},
            {"道路": "全部合計", "人工計數": "4"},
        ], ["道路", "人工計數"])

        counts, _ = load_manual_counts(str(path))
        assert len(counts) == 1

    def test_欄位缺漏時拋出明確例外(self, tmp_path):
        path = tmp_path / "人工.csv"
        write_manual(path, [{"錯誤欄位": "1"}], ["錯誤欄位"])
        with pytest.raises(ValueError, match="必須包含"):
            load_manual_counts(str(path))

    def test_非數字內容拋出明確例外(self, tmp_path):
        path = tmp_path / "人工.csv"
        write_manual(path, [{"道路": "1", "人工計數": "很多"}], ["道路", "人工計數"])
        with pytest.raises(ValueError, match="必須是數字"):
            load_manual_counts(str(path))


class TestTemplate:
    """人工計數範本產生。"""

    def test_列出所有道路與車種的組合(self, detail_csv, tmp_path):
        output = str(tmp_path / "範本.csv")
        write_template(detail_csv, output)

        with open(output, encoding=_ENCODING, newline="") as f:
            rows = list(csv.DictReader(f))

        # 2 條道路 x 2 種車種
        assert len(rows) == 4
        assert all(r["人工計數"] == "" for r in rows)

    def test_範本可直接被讀回(self, detail_csv, tmp_path):
        """填完就能用，欄位格式必須與讀取端相容。"""
        output = str(tmp_path / "範本.csv")
        write_template(detail_csv, output)

        # 模擬使用者填入數字
        with open(output, encoding=_ENCODING, newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row["人工計數"] = "1"
        write_manual(output, rows, ["道路", "車種", "人工計數"])

        counts, by_type = load_manual_counts(output)
        assert by_type is True
        assert sum(counts.values()) == 4


class TestCompare:
    """比對與誤差計算。"""

    def test_完全一致時誤差為零(self):
        system = {("1", "小客車"): 10}
        manual = {("1", "小客車"): 10}
        rows = compare(system, manual, by_type=True)
        assert rows[0]["誤差"] == 0
        assert rows[0]["誤差率"] == "0.0%"

    def test_系統多算時誤差為正(self):
        rows = compare({("1", "小客車"): 12}, {("1", "小客車"): 10}, by_type=True)
        assert rows[0]["誤差"] == 2
        assert rows[0]["誤差率"] == "20.0%"

    def test_系統少算時誤差為負(self):
        rows = compare({("1", "小客車"): 8}, {("1", "小客車"): 10}, by_type=True)
        assert rows[0]["誤差"] == -2
        assert rows[0]["絕對誤差"] == 2

    def test_人工為零時不計算百分比(self):
        """分母為零不能算出百分比，應標示為未定義而非崩潰。"""
        rows = compare({("1", "小客車"): 3}, {("1", "小客車"): 0}, by_type=True)
        assert rows[0]["誤差率"] == "—"

    def test_僅道路比對時系統計數會依道路加總(self):
        system = {("1", "小客車"): 7, ("1", "機車"): 3}
        manual = {("1", None): 10}
        rows = compare(system, manual, by_type=False)
        assert len(rows) == 1
        assert rows[0]["系統計數"] == 10
        assert rows[0]["誤差"] == 0

    def test_只存在於單邊的項目仍會列出(self):
        """系統偵測到但人工沒數到（或相反）是重要的誤差來源，不可被忽略。"""
        rows = compare({("2", "大貨車"): 1}, {("1", "小客車"): 5}, by_type=True)
        assert len(rows) == 2


class TestSummarise:
    """整體指標。"""

    def test_總量與準確率(self):
        rows = compare(
            {("1", "小客車"): 9, ("2", "小客車"): 4},
            {("1", "小客車"): 10, ("2", "小客車"): 5},
            by_type=True,
        )
        metrics = summarise(rows)
        assert metrics["人工總計"] == 15
        assert metrics["系統總計"] == 13
        assert metrics["總量誤差"] == -2
        assert metrics["總量誤差率"] == pytest.approx(2 / 15 * 100)
        assert metrics["總量準確率"] == pytest.approx((1 - 2 / 15) * 100)

    def test_平均與最大絕對誤差(self):
        rows = compare(
            {("1", "小客車"): 9, ("2", "小客車"): 1},
            {("1", "小客車"): 10, ("2", "小客車"): 5},
            by_type=True,
        )
        metrics = summarise(rows)
        assert metrics["平均絕對誤差"] == pytest.approx(2.5)  # (1 + 4) / 2
        assert metrics["最大絕對誤差"] == 4

    def test_MAPE_排除人工為零的項目(self):
        rows = compare(
            {("1", "小客車"): 8, ("2", "機車"): 3},
            {("1", "小客車"): 10, ("2", "機車"): 0},
            by_type=True,
        )
        metrics = summarise(rows)
        # 只有道路1 納入：|8-10|/10 = 20%
        assert metrics["分項MAPE"] == pytest.approx(20.0)

    def test_全為零不會除以零(self):
        metrics = summarise(compare({}, {}, by_type=True))
        assert metrics["人工總計"] == 0
        assert metrics["總量準確率"] == 0.0


class TestWriteReport:
    """報表輸出。"""

    def test_輸出含合計列與指標(self, tmp_path):
        rows = compare({("1", "小客車"): 9}, {("1", "小客車"): 10}, by_type=True)
        metrics = summarise(rows)
        output = str(tmp_path / "驗證.csv")
        write_report(rows, metrics, True, output)

        with open(output, encoding=_ENCODING, newline="") as f:
            content = f.read()

        assert "全部合計" in content
        assert "總量準確率" in content
        assert "分項MAPE" in content

    def test_編碼含_BOM(self, tmp_path):
        rows = compare({("1", "小客車"): 9}, {("1", "小客車"): 10}, by_type=True)
        output = str(tmp_path / "驗證.csv")
        write_report(rows, summarise(rows), True, output)

        with open(output, "rb") as f:
            assert f.read(3) == b"\xef\xbb\xbf"

    def test_僅道路模式不輸出車種欄(self, tmp_path):
        rows = compare({("1", "小客車"): 9}, {("1", None): 10}, by_type=False)
        output = str(tmp_path / "驗證.csv")
        write_report(rows, summarise(rows), False, output)

        with open(output, encoding=_ENCODING, newline="") as f:
            header = f.readline()
        assert "車種" not in header


class TestEndToEnd:
    """完整流程：產生範本 → 填寫 → 比對。"""

    def test_流程可串接且數字正確(self, detail_csv, tmp_path):
        template = str(tmp_path / "人工計數.csv")
        write_template(detail_csv, template)

        # 模擬人工計數：道路1 小客車 實際有 3 台（系統只抓到 2）
        write_manual(template, [
            {"道路": "1", "車種": "小客車", "人工計數": "3"},
            {"道路": "1", "車種": "機車", "人工計數": "1"},
            {"道路": "2", "車種": "小客車", "人工計數": "1"},
            {"道路": "2", "車種": "機車", "人工計數": "0"},
        ], ["道路", "車種", "人工計數"])

        system = load_system_counts(detail_csv)
        manual, by_type = load_manual_counts(template)
        rows = compare(system, manual, by_type)
        metrics = summarise(rows)

        assert metrics["人工總計"] == 5
        assert metrics["系統總計"] == 4
        assert metrics["總量誤差"] == -1

        output = str(tmp_path / "準確度驗證.csv")
        write_report(rows, metrics, by_type, output)
        assert os.path.isfile(output)
