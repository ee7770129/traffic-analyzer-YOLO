# core（核心資料結構）

## 模組功能說明

定義流水線上傳遞的資料容器，**不含任何業務邏輯**。

每個節點依序在同一個物件上附加自己產出的資訊，讓後續節點取用，
避免節點之間直接互相呼叫而產生耦合。

## 技術棧

Python 標準函式庫、NumPy

## 架構依賴圖

```
core/
├── __init__.py               對外匯出三個資料類別
├── frame_element.py          FrameElement：單幀資料容器
├── track_element.py          TrackElement：單一車輛軌跡
└── stream_end_element.py     StreamEndElement：串流結束訊號
```

本套件為相依鏈的最底層，**不得相依於 nodes/ 或 utils/**。

## 資料類別

### FrameElement

單一影格及其分析結果，欄位依流水線順序逐步填入：

| 階段 | 欄位 |
|------|------|
| 影像讀取 | `source`, `frame`, `timestamp`, `frame_num`, `total_frames`, `roads_info` |
| 偵測 | `detected_conf`, `detected_cls`, `detected_xyxy` |
| 追蹤 | `tracked_ids`, `tracked_conf`, `tracked_cls`, `tracked_xyxy` |
| 軌跡維護 | `active_tracks`, `retired_tracks` |
| 計數 | `count_events`, `statistics` |
| 繪製 | `frame_result` |

### TrackElement

一台車從進入到離開畫面的完整歷程，是精確計數與 OD 矩陣的資料基礎。

| 欄位 | 說明 |
|------|------|
| `entry_road` / `entry_timestamp` | 進入道路與時間（第一個造訪的區域） |
| `exit_road` / `exit_timestamp` | 離開道路與時間（第一個不同於進入道路的區域） |
| `zone_sequence` | 依序造訪過的區域，供除錯與人工驗證 |
| `counted_entry` / `counted_movement` | 計數旗標，保證每台車只計一次 |
| `vehicle_type` | 生命週期多數決得出的車種（唯讀屬性） |
| `vote_count` | 成功辨識的幀數（唯讀屬性） |
| `lifetime` | 軌跡存活秒數（唯讀屬性） |

主要方法：`update()` 更新時間與位置、`vote_vehicle_type()` 累積車種投票、
`observe_zone()` 記錄所在區域並推導進出道路、`to_record()` 轉為報表用紀錄。

### StreamEndElement

影像來源結束的標記。刻意保留與 `FrameElement` 同名的統計欄位
（`active_tracks`、`retired_tracks`、`count_events`、`statistics`），
讓「軌跡收尾 → 計數 → 報表」這條收尾路徑不需要額外的特例分支。

## 變更日誌參考

詳見 `../CHANGELOG.md`

---
**建立日期**：2024-12-18
**最後更新**：2025-01-15（新增 TrackElement，支援進出道路判定與車種投票）
