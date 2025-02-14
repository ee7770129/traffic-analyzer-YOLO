# utils（共用工具）

## 模組功能說明

提供與業務邏輯無關的輔助函式。所有模組皆為無狀態或僅持有自身設定，
可被任何節點安全重複使用。

## 技術棧

NumPy、Shapely、Pillow、OpenCV

## 架構依賴圖

```
utils/
├── __init__.py          刻意不匯入子模組（見下方說明）
├── geometry.py          多邊形建立、區域內含判定、IoU 矩陣
├── vehicle_types.py     車種中英對照與 PCU 當量查詢
├── text_drawer.py       以 Pillow 在 OpenCV 影像上繪製繁體中文
├── fps_counter.py       滑動視窗 FPS 計算
├── profiler.py          節點耗時量測裝飾器
└── vendor_path.py       第三方套件路徑註冊（有 sys.path 副作用）
```

本套件僅相依於第三方函式庫，**不得相依於 core/ 或 nodes/**。

`__init__.py` 刻意不匯入任何子模組，避免 `vendor_path` 的 `sys.path`
副作用在非預期時機被觸發。使用端請直接匯入所需的子模組。

## 各模組說明

| 模組 | 對外介面 | 說明 |
|------|----------|------|
| `geometry` | `build_polygons()`, `locate_zone()`, `bbox_center()`, `iou_matrix()` | 多邊形只在首幀建立一次，避免每幀重複解析座標 |
| `vehicle_types` | `VehicleTypeRegistry.to_chinese()`, `.pcu_of()`, `.labels` | 對照值全部由設定檔注入，程式內不寫死 |
| `text_drawer` | `TextDrawer.draw()`, `.text_size()` | 整張影像單次轉換策略，見下方效能說明 |
| `fps_counter` | `FPSCounter.update()` | 視窗未滿時回傳 0.0，避免初期數值跳動 |
| `profiler` | `@profile_time` | DEBUG 等級輸出，平時不影響效能 |
| `vendor_path` | 匯入即生效 | 將專案根目錄與 `vendor/` 加入 `sys.path` |

## 設計要點

### 中文文字繪製效能（text_drawer.py）

`cv2.putText()` 僅支援 ASCII，無法顯示中日韓文字，故改用 Pillow。

為兼顧效能採「整張影像單次轉換」策略：呼叫端先用 cv2 完成所有圖形繪製，
最後把所有文字一次交給 `draw()`，避免每段文字都做一次格式轉換。

色彩空間轉換使用 `cv2.cvtColor` 而非 NumPy 的 `[:, :, ::-1]` 切片。
後者產生負步長檢視，Pillow 需額外複製一次陣列；
實測改用 `cv2.cvtColor` 後，含繪圖的整體處理速度由約 22 FPS 提升至約 32 FPS。

### 字型解析（text_drawer.py）

依設定檔的 `font_candidates` 順序尋找第一個實際存在的字型檔。
全部找不到時退回 Pillow 預設字型並輸出警告，中文會顯示為方框但程式不會中斷。

## 變更日誌參考

詳見 `../CHANGELOG.md`

---
**建立日期**：2024-12-18
**最後更新**：2025-02-14（新增 TextDrawer，並記錄色彩轉換的效能調校結果）
