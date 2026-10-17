# nodes（流水線節點）

## 模組功能說明

流水線的業務邏輯層。每個節點只負責一件事，對外統一提供 `process(element)` 介面，
節點之間僅透過 `FrameElement` 傳遞資料，彼此不直接呼叫，維持低耦合。

所有節點收到 `StreamEndElement` 時不進行影像處理，但仍可執行收尾動作
（清空殘留軌跡、結算統計、輸出報表、關閉影片檔）。

## 技術棧

ultralytics（YOLOv8）、ByteTrack、OpenCV、Pillow、Shapely、Python csv

## 架構依賴圖

```
nodes/
├── __init__.py                   對外匯出所有節點類別
├── video_reader_node.py          影像讀取（產生器，流水線起點）
├── detection_tracking_node.py    YOLO 偵測 + ByteTrack 追蹤 + 車種還原
├── track_update_node.py          軌跡生命週期維護、進出道路判定
├── counting_node.py              精確累計計數、轉向 OD、即時流率
├── render_node.py                疊加圖層繪製（區域、邊界框、統計面板）
├── report_node.py                四份 CSV 報表輸出
├── video_writer_node.py          成果影片輸出
├── line_counting_node.py         越線計數（進入／離開路口）
├── line_render_node.py           計數線與越線車次繪製
├── line_report_node.py           三份越線報表輸出
├── heatmap_node.py               軌跡熱力圖
└── phf_report_node.py            尖峰小時係數報表
```

**相依方向**（單向，不得反向相依）：

```
nodes/ ──→ core/      （資料結構）
       ──→ utils/     （共用工具）
       ──→ vendor/    （第三方 ByteTrack，僅 detection_tracking_node）
```

## 節點清單

| 節點 | 輸入 | 產出（寫入 element 的欄位） |
|------|------|------------------------------|
| `VideoReaderNode` | 設定檔 | `frame`, `timestamp`, `frame_num`, `roads_info` |
| `DetectionTrackingNode` | FrameElement | `detected_*`, `tracked_*`（含中文車種） |
| `TrackUpdateNode` | FrameElement | `active_tracks`, `retired_tracks` |
| `CountingNode` | FrameElement | `count_events`, `statistics` |
| `RenderNode` | FrameElement | `frame_result` |
| `VideoWriterNode` | FrameElement | 寫出 `分析結果.mp4` |
| `ReportNode` | FrameElement | 寫出 4 份 CSV |
| `LineCountingNode` | FrameElement | `line_events`, `statistics["越線計數"]` |
| `LineRenderNode` | FrameElement | 在 `frame_result` 上加畫計數線 |
| `LineReportNode` | FrameElement | 寫出 `越線明細.csv`、`越線計數.csv`、`越線轉向矩陣.csv` |
| `HeatmapNode` | FrameElement | 寫出 `軌跡熱力圖.png` |
| `PhfReportNode` | FrameElement | 寫出 `尖峰小時係數.csv` |

v1.2.0 新增的五個節點皆可個別開關，由根目錄的 `pipeline_builder.py` 依設定建立，
停用時既有七個節點的行為完全不變。

## 設計要點

### 車種還原（detection_tracking_node.py）

送入追蹤器前把所有物件的類別統一為 COCO 的 car，維持與參考專案一致的追蹤行為；
追蹤完成後再以 IoU 最大配對把追蹤框對回當幀的偵測框取得車種。
物件被遮擋時追蹤器會以卡爾曼濾波預測位置，該幀沒有對應偵測框，
配對 IoU 低於 `class_match_iou` 即不投票——這正是需要生命週期多數決的原因。

### 計數保證（counting_node.py）

- 進入計數與轉向計數各由 `counted_entry`、`counted_movement` 旗標保證只發生一次
- 計數門檻：存活時間 ≥ `min_track_life_secs` 且辨識幀數 ≥ `min_vote_count`
- 轉向計數僅結算已計入進入流量的車輛，確保兩份統計的母體一致

### 軌跡收尾（track_update_node.py）

以「最後出現時間」超過 `track_timeout_secs` 判定離場，
並把離場軌跡完整交給下游，確保每台車都會被結算且只結算一次。
收到 `StreamEndElement` 時一次清空所有殘留軌跡，避免影片尾端的車輛漏計。

### 進入方向判定（track_update_node.py）

建構子可選擇性傳入 `DirectionGate`。有傳入時，區域觀測改由它處理：
車輛移動一小段後才依行進方向決定第一個區域是進入還是離開。
未傳入時維持「第一個踩到的區域即為進入道路」的原規則，既有測試與內附影片的結果不變。

### 越線計數（line_counting_node.py）

- 以車輛前後兩幀的位移線段是否與計數線相交來判定，低幀率串流下不漏判
- 同一台車對同一條線的同一方向只記一次，避免在線上抖動造成重複計數
- 計數門檻與 `CountingNode` 相同；越線當下未達門檻者先暫存，達門檻後補計
- 最終紀錄在軌跡離場時產生，車種採離場時的多數決，與 `ReportNode` 的原則一致
- 只讀取軌跡，不修改 `CountingNode` 的任何統計，兩套計數並存

### 串流重連（video_reader_node.py）

交通局的 MJPEG 串流實測約 30 秒會被伺服器中斷一次。
`reconnect_attempts` 大於 0 時，讀取失敗會重新開啟串流後繼續；
以「連續失敗次數」計算，成功讀到一幀即歸零。預設值 0 維持原本「讀不到即結束」的行為。
重連期間的影像會遺失，該時段內通過的車輛不會被計入。

### 熱力圖的亮度上限（heatmap_node.py）

一台長時間停等的車會讓單點數值遠高於其他位置。
若以最大值正規化，整張圖只會剩一個亮點，故改以 `clip_percentile` 百分位數為上限。

## 開發指令

```
python main.py                                    執行完整流水線
python main.py hydra.job_logging.root.level=DEBUG  輸出各節點耗時，定位效能瓶頸
```

## 新增節點的步驟

1. 在本資料夾建立新檔案，類別提供 `process(element)` 方法
2. 開頭處理 `StreamEndElement`（原樣回傳或執行收尾）
3. 以 `@profile_time` 裝飾 `process()` 以納入效能量測
4. 在 `__init__.py` 匯出
5. 在 `main.py` 的 `_run_analysis_chain()` 中串接
6. 於 `configs/app_config.yaml` 新增對應的設定區段
7. 更新本文件與根目錄的 `CHANGELOG.md`

## 變更日誌參考

詳見 `../CHANGELOG.md`

---
**建立日期**：2024-12-20
**最後更新**：2026-10-09（v1.2.0 新增越線計數、熱力圖、尖峰小時係數節點、串流重連與進入方向判定）
