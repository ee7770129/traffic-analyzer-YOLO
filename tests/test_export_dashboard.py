# -*- coding: utf-8 -*-
"""
請以繁體中文產生程式碼註解。請務必保持 UTF-8 編碼。

模組名稱：成果展示網頁資料匯出的單元測試
功能說明：
    以暫存資料夾模擬單路口與多路口的分析輸出，
    驗證彙總數字、路口辨識、圖片轉檔與缺檔時的行為。

建立日期：2026-10-08
最後更新：2026-10-09（支援多路口輸出）
版本號：v1.2.0
"""

import json
import os

import cv2
import numpy as np
import pytest

from tools import export_dashboard as exporter

_CATALOG = """
page_url_template: "https://example.test/show?id={camera_id}"
cameras:
  demo:
    name: 示範路口
    camera_id: C000001
    resolution: 640x360
    measured_fps: 7.1
    roads_info: zones.json
  other:
    name: 另一個路口
    camera_id: C000002
    roads_info: zones.json
"""

_DETAIL = (
    "追蹤編號,車種,進入道路,最後出現_秒,是否計入統計\n"
    "1,小客車,1,10.5,是\n"
    "2,機車,1,42.0,是\n"
    "3,小客車,2,30.0,是\n"
    "4,小客車,,5.0,否\n"
)


def write_image(path, shape, value=120):
    ok, buffer = cv2.imencode(os.path.splitext(str(path))[1], np.full(shape, value, dtype=np.uint8))
    buffer.tofile(str(path))


def fill_reports(folder):
    """在資料夾中放入一個路口的報表與熱力圖。"""
    (folder / "車輛明細.csv").write_text(_DETAIL, encoding="utf-8-sig")
    (folder / "越線計數.csv").write_text("計數線,車次\n1,3\n", encoding="utf-8-sig")
    write_image(folder / "軌跡熱力圖.png", (20, 30, 3))


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "cameras.yaml"
    path.write_text(_CATALOG, encoding="utf-8")
    return str(path)


@pytest.fixture
def single_run(tmp_path):
    """單路口模式的輸出：報表直接放在輸出資料夾，另有成果影片。"""
    folder = tmp_path / "20261008_000000"
    folder.mkdir()
    fill_reports(folder)

    video = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(10):
        writer.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    writer.release()
    os.replace(str(video), str(folder / "分析結果.mp4"))
    return str(folder)


@pytest.fixture
def multi_run(tmp_path):
    """多路口模式的輸出：每個路口一個子資料夾，另有多路口畫面。"""
    folder = tmp_path / "20261009_000000"
    folder.mkdir()
    for key in ("demo", "other"):
        (folder / key).mkdir()
        fill_reports(folder / key)
    write_image(folder / "多路口畫面.jpg", (40, 90, 3))
    return str(folder)


def read_summary(web_dir):
    with open(os.path.join(web_dir, "data", "summary.json"), encoding="utf-8") as file:
        return json.load(file)


class TestSummarizeVehicles:
    def test_只統計已計入的車輛(self):
        rows = [line.split(",") for line in _DETAIL.strip().split("\n")]
        summary = exporter.summarize_vehicles(rows)
        assert summary["total"] == 3
        assert summary["by_road"] == {"1": 2, "2": 1}
        assert summary["by_type"] == {"小客車": 2, "機車": 1}
        assert summary["duration_secs"] == 42.0

    def test_沒有資料時回傳零值(self):
        assert exporter.summarize_vehicles([])["total"] == 0


class TestSingleRun:
    def test_輸出資料檔與兩張圖片(self, single_run, catalog_file, tmp_path):
        web_dir = str(tmp_path / "web")
        written = exporter.export(single_run, "demo", catalog_file, web_dir)
        assert written == {"summary": True, "heatmap_demo": True, "result": True}

        summary = read_summary(web_dir)
        assert summary["run_id"] == "20261008_000000"
        assert len(summary["cameras"]) == 2
        assert len(summary["intersections"]) == 1

        item = summary["intersections"][0]
        assert item["camera"]["name"] == "示範路口"
        assert item["camera"]["page_url"] == "https://example.test/show?id=C000001"
        assert item["vehicles"]["total"] == 3
        assert item["line_counts"] == [["計數線", "車次"], ["1", "3"]]
        assert item["phf"] == []
        assert item["heatmap"] == "assets/heatmap_demo.jpg"

        heatmap = exporter.read_image(os.path.join(web_dir, "assets", "heatmap_demo.jpg"))
        assert heatmap.shape == (20, 30, 3)
        # 沒有多路口畫面時，代表畫面取自成果影片
        assert exporter.read_image(os.path.join(web_dir, "assets", "result.jpg")).shape == (48, 64, 3)

    def test_未指定路口時拋出錯誤(self, single_run, catalog_file, tmp_path):
        with pytest.raises(ValueError, match="--camera"):
            exporter.export(single_run, None, catalog_file, str(tmp_path / "web"))

    def test_路口不在目錄中時拋出錯誤(self, single_run, catalog_file, tmp_path):
        with pytest.raises(ValueError, match="nope"):
            exporter.export(single_run, "nope", catalog_file, str(tmp_path / "web"))

    def test_缺少圖片與影片時仍輸出資料檔(self, catalog_file, tmp_path):
        empty_run = tmp_path / "empty_run"
        empty_run.mkdir()
        written = exporter.export(str(empty_run), "demo", catalog_file, str(tmp_path / "web"))
        assert written == {"summary": True, "heatmap_demo": False, "result": False}


class TestMultiRun:
    def test_自動辨識各路口的子資料夾(self, multi_run, catalog_file, tmp_path):
        web_dir = str(tmp_path / "web")
        written = exporter.export(multi_run, None, catalog_file, web_dir)
        assert written == {"summary": True, "heatmap_demo": True, "heatmap_other": True, "result": True}

        summary = read_summary(web_dir)
        assert [item["camera"]["key"] for item in summary["intersections"]] == ["demo", "other"]
        assert summary["intersections"][1]["vehicles"]["total"] == 3
        assert summary["intersections"][1]["heatmap"] == "assets/heatmap_other.jpg"

        # 多路口模式以現成的多路口畫面作為代表畫面
        assert exporter.read_image(os.path.join(web_dir, "assets", "result.jpg")).shape == (40, 90, 3)

    def test_只匯出實際存在的路口(self, catalog_file, tmp_path):
        run = tmp_path / "partial"
        (run / "other").mkdir(parents=True)
        fill_reports(run / "other")
        exporter.export(str(run), None, catalog_file, str(tmp_path / "web"))
        summary = read_summary(str(tmp_path / "web"))
        assert [item["camera"]["key"] for item in summary["intersections"]] == ["other"]


class TestMain:
    def test_正常執行回傳0(self, multi_run, catalog_file, tmp_path, capsys):
        code = exporter.main(["--run", multi_run, "--catalog", catalog_file,
                              "--web", str(tmp_path / "web")])
        assert code == 0
        assert "已輸出" in capsys.readouterr().out

    def test_輸出資料夾不存在回傳1(self, catalog_file, tmp_path):
        code = exporter.main(["--run", str(tmp_path / "missing"), "--camera", "demo",
                              "--catalog", catalog_file])
        assert code == 1
