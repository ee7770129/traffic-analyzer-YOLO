# tests（單元測試）

## 模組功能說明

以 pytest 撰寫的單元測試。專案規範要求整體覆蓋率 ≥ 70%、核心邏輯 ≥ 90%，
門檻寫在 `pytest.ini` 的 `--cov-fail-under`，未達標時測試直接視為失敗。

**目前狀態：232 個測試、整體覆蓋率 87%，核心統計模組 99%。**

## 技術棧

pytest、pytest-cov

## 架構依賴圖

```
tests/
├── CLAUDE.md
├── conftest.py                    共用設定與 fixture
├── test_geometry.py               多邊形判定、IoU 矩陣
├── test_vehicle_types.py          車種對照、PCU 當量
├── test_utils_misc.py             FPS 計數、效能裝飾器、中文繪字
├── test_cython_bbox.py            Windows 相容層的數值正確性
├── test_core_elements.py          FrameElement、StreamEndElement
├── test_track_element.py          進出道路判定、車種多數決
├── test_counting_node.py          精確計數、轉向 OD、車種修正
├── test_track_update_node.py      軌跡生命週期、離場判定
├── test_report_node.py            四份報表內容、編碼、一致性
├── test_video_io_nodes.py         影像讀取、影片輸出
├── test_render_and_detection.py   疊圖繪製、車種還原邏輯
├── test_zone_editor.py            區域編輯器邏輯、座標換算
└── test_accuracy_check.py         誤差指標計算
```

## 命名規範

採 pytest 預設的 `test_*.py`，而非專案規範建議的 `xxx.test.py`。

原因是 `xxx.test.py` 無法作為 Python 模組名稱匯入（檔名含點號），
pytest 收集時會失敗。測試類別以 `Test*` 開頭、測試函式以 `test_` 開頭，
函式名稱直接使用繁體中文描述驗證的行為。

## 執行

```
run_tests.bat                              雙擊即可，含覆蓋率報告
python -m pytest                           同上
python -m pytest tests/test_counting_node.py   只跑單一檔案
python -m pytest -k counting               只跑名稱含 counting 的測試
python -m pytest --cov-report=html         產生 HTML 覆蓋率報告
```

## 共用 fixture（conftest.py）

| fixture | 內容 |
|---------|------|
| `vehicle_types_config` | 車種對照與 PCU 當量設定 |
| `general_config` | 一般參數，門檻值刻意調小以便構造測試情境 |
| `base_config` | 組合出節點建構所需的完整設定字典 |
| `square_roads` | 三個互不重疊的方形區域，座標格式同 `roads_polygons.json` |

`conftest.py` 同時負責把專案根目錄加入 `sys.path`，測試才能匯入 `core` / `nodes` / `utils`。

## 測試重點

這些是出錯會直接讓數據失真、因此覆蓋得特別密的地方：

1. **進出道路判定**（`test_track_element.py`）
   第一個區域為進入、第一個不同區域為離開；重複踩同一區不得誤判為離開。

2. **計數的三道門檻與去重**（`test_counting_node.py`）
   未達門檻不得計入；同一台車無論被處理幾次都只能計一次。

3. **車種修正**（`test_counting_node.py`）
   計數發生在票數還少時，離場時須以最終多數決回頭修正統計與 PCU。

4. **報表一致性**（`test_report_node.py`）
   四份報表皆由同一份軌跡紀錄推導，車次、車種分布必須逐項相符。

5. **座標換算**（`test_zone_editor.py`）
   畫面縮放時滑鼠座標須換算回原始解析度，否則區域整組偏移。

6. **相容層數值**（`test_cython_bbox.py`）
   以手算值確認 IoU 與原始 C 擴充套件完全一致（含 +1 像素慣例）。

## 未覆蓋的部分與原因

| 模組 | 覆蓋率 | 未覆蓋的原因 |
|------|--------|-------------|
| `nodes/detection_tracking_node.py` | 48% | 建構子會載入 YOLO 權重、`process()` 需實際推論。純邏輯部分（追蹤器輸入組裝、車種還原）已以 `object.__new__` 繞過建構子完整覆蓋 |
| `tools/zone_editor.py` | 71% | cv2 的互動主迴圈需要真實鍵盤滑鼠事件。狀態管理與座標換算已完整覆蓋 |
| `tools/accuracy_check.py` | 67% | 命令列進入點與主控台輸出格式。所有計算邏輯已完整覆蓋 |

## 撰寫新測試的原則

- 一個測試只驗證一件事，函式名稱直接寫出預期行為
- 用 `tmp_path` fixture 產生暫存檔，不得污染專案目錄
- 不相依 `test_videos/` 或 `weights/` 的實際檔案——這兩者不隨儲存庫散布，
  需要影片時以 `cv2.VideoWriter` 即時合成
- 邊界情況（空輸入、除以零、檔案不存在）要一併覆蓋，這些是實務上最常爆的地方

## 變更日誌參考

詳見 `../CHANGELOG.md`

---
**建立日期**：2026-10-03
**最後更新**：2026-10-03（初版建立）
