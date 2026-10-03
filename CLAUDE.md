# 路口車流分析系統（TrafficAnalyzer_TW）- 系統說明

## 專案定位

**開發期間**：2024 年 12 月 ～ 2025 年 2 月　|　**目前版本**：v1.1.0（2026-10-03）

> 安裝與操作說明請見 [README.md](./README.md)，本文件著重於架構與設計決策。

以電腦視覺自動化產出路口／圓環車流調查數據，取代人工計數，供交通工程分析使用。

系統輸入一段路口影片（或即時攝影機串流），輸出：

- 各方向的**精確累計車次**（可與人工計數逐筆核對）
- **車種分類統計**與小客車當量（PCU）
- **轉向 OD 矩陣**（由第 i 條路進入、由第 j 條路離開的車輛數）
- **時段流量報表**（可設定統計區間）
- 帶有疊加圖層的**成果影片**

本專案以開源專案 [Koldim2001/TrafficAnalyzer](https://github.com/Koldim2001/TrafficAnalyzer) 的節點流水線架構為參考基礎重新實作，並補齊原專案缺少的計數與報表能力。本專案為獨立可執行的實作，不依賴原專案的任何檔案。

### 與參考專案的主要差異

| 項目 | 參考專案 | 本專案 |
|------|----------|--------|
| 車流數據 | 滑動視窗估計值（輛/分），無法累加 | 事件驅動的精確累計，可重現、可核對 |
| 車種統計 | 無（追蹤前類別被統一改為 car） | 以 IoU 回溯配對 + 生命週期多數決還原 |
| 轉向分析 | 無（僅記錄進入道路） | 完整 OD 矩陣 |
| 資料輸出 | PostgreSQL + Grafana | CSV 報表（UTF-8 BOM，Excel 可直接開啟） |
| 註解語言 | 俄文 | 繁體中文 |
| Windows 相容性 | 需 MSVC 編譯 cython-bbox | 內附純 NumPy 相容層，免編譯器 |

---

## 模組結構與命名規範

| 層級 | 資料夾 | 職責 |
|------|--------|------|
| 進入點 | `main.py` | 只負責串接節點與流程控制，不含業務邏輯 |
| 資料結構 | `core/` | 流水線傳遞的資料容器，無業務邏輯 |
| 業務節點 | `nodes/` | 每個節點一支程式，單一職責，介面統一為 `process(element)` |
| 共用工具 | `utils/` | 幾何、字型、效能等與業務無關的輔助函式 |
| 第三方 | `vendor/` | 原樣保存的第三方程式碼，不修改 |
| 設定 | `configs/` | 所有可調參數，程式內不寫死數值 |
| 輸出 | `outputs/` | 每次執行建立獨立的時間戳資料夾 |

**溝通用詞統一**：

- 「道路 N」：圓環的第 N 條聯絡道，編號對應 `configs/roads_polygons.json`
- 「進入道路」：車輛第一個踩到的區域
- 「離開道路」：車輛之後第一個踩到的、不同於進入道路的區域
- 「轉向紀錄」：一筆完整的「進入→離開」配對

---

## 技術選擇

| 類別 | 技術 | 版本 | 說明 |
|------|------|------|------|
| 物件偵測 | YOLOv8m (ultralytics) | 8.2.38 | COCO 預訓練權重，偵測類別 2/3/5/7 |
| 多目標追蹤 | ByteTrack | 內附 | 原樣保存於 `vendor/`，未修改 |
| 深度學習框架 | PyTorch | 2.3.1 + cu121 | 需依顯示卡 CUDA 版本安裝 |
| 影像處理 | OpenCV | 4.9.0.80 | 圖形繪製與影片讀寫 |
| 中文文字繪製 | Pillow | >= 10.0 | cv2.putText 不支援 CJK，故以 PIL 補足 |
| 幾何運算 | Shapely | 2.0.3 | 多邊形內含判定 |
| 設定管理 | Hydra | 1.3.2 | 支援命令列覆寫參數 |
| 環境變數 | python-dotenv | >= 1.0 | 讀取 `.env` |

**執行環境**：Python 3.10（conda 環境名稱 `traffic`）、Windows 11、NVIDIA GPU（CPU 亦可執行但速度大幅下降）。

---

## 端口配置

本專案為**離線分析工具，不對外開放任何服務端口**。

若未來需要新增網頁介面，端口須以環境變數管理，並於本節補上對照表。

---

## 架構依賴圖

```
TrafficAnalyzer_TW/
├── START.bat                        建議入口：先檢查素材齊全再啟動
├── run.bat                          一鍵啟動（即時預覽視窗）
├── run_export.bat                   批次匯出（無視窗，輸出影片 + 報表）
├── edit_zones.bat                   開啟區域座標編輯器
├── check_accuracy.bat               準確度驗證
├── run_tests.bat                    執行單元測試與覆蓋率
├── _find_python.bat                 批次檔共用的 conda 環境尋找邏輯
├── pytest.ini                       測試探索規則與覆蓋率門檻
├── main.py                          主程式進入點，組裝流水線
├── cython_bbox.py                   Windows 相容層（純 NumPy 版 bbox_overlaps）
├── requirements.txt
├── .env.example                     環境變數範本
├── README.md                        使用說明（安裝、執行畫面、圖解、疑難排解）
├── CLAUDE.md                        本文件
├── CHANGELOG.md                     變更歷史
│
├── docs/images/                     說明文件用的截圖
│   ├── preview.png                  即時預覽視窗
│   └── console-output.png           主控台輸出
│
├── configs/
│   ├── app_config.yaml              主設定檔（所有可調參數）
│   ├── roads_polygons.json          道路區域座標
│   └── hydra/job_logging/custom.yaml  日誌格式
│
├── core/                            資料結構（詳見 core/CLAUDE.md）
│   ├── frame_element.py             單幀資料容器
│   ├── track_element.py             單一車輛軌跡
│   └── stream_end_element.py        串流結束訊號
│
├── nodes/                           流水線節點（詳見 nodes/CLAUDE.md）
│   ├── video_reader_node.py         影像讀取
│   ├── detection_tracking_node.py   偵測 + 追蹤 + 車種還原
│   ├── track_update_node.py         軌跡狀態維護
│   ├── counting_node.py             車流計數與轉向統計
│   ├── render_node.py               畫面繪製
│   ├── report_node.py               統計報表輸出
│   └── video_writer_node.py         成果影片輸出
│
├── utils/                           共用工具（詳見 utils/CLAUDE.md）
│   ├── geometry.py                  多邊形判定與 IoU
│   ├── vehicle_types.py             車種對照與 PCU 當量
│   ├── text_drawer.py               中文文字繪製
│   ├── fps_counter.py               FPS 計算
│   ├── profiler.py                  效能計時
│   └── vendor_path.py               第三方套件路徑註冊
│
├── tools/                           獨立工具（詳見 tools/CLAUDE.md）
│   ├── zone_editor.py               道路區域座標編輯器
│   └── accuracy_check.py            準確度驗證
│
├── tests/                           單元測試（詳見 tests/CLAUDE.md）
│   ├── conftest.py                  共用設定與 fixture
│   └── test_*.py                    232 個測試，覆蓋率 87%
│
├── vendor/byte_tracker/             第三方 ByteTrack（原樣保存，不修改）
├── weights/yolov8m.pt               YOLO 權重
├── test_videos/test_video.mp4       測試影片（圓環，66.8 秒）
└── outputs/<執行時間>/               每次執行的結果
```

---

## 關鍵資料流

```
影片 → VideoReaderNode ─── FrameElement(frame, timestamp, roads_info)
                              ↓
        DetectionTrackingNode ─ 附加 detected_* / tracked_*（含還原的中文車種）
                              ↓
        TrackUpdateNode ────── 附加 active_tracks / retired_tracks
                              │   └ 更新每台車的 進入道路 / 離開道路 / 車種投票
                              ↓
        CountingNode ───────── 附加 count_events / statistics
                              │   └ 每台車只計一次：進入計數、轉向 OD
                              ↓
        RenderNode ─────────── 附加 frame_result（疊加圖層）
                              ↓
        VideoWriterNode ────── 寫入 分析結果.mp4
                              ↓
        ReportNode ─────────── 累積事件；收到結束訊號時輸出 4 份 CSV
```

**計數判定規則**（決定數據可信度的核心）：

1. 車輛中心點落入某區域 → 第一個區域記為「進入道路」
2. 之後落入不同區域 → 記為「離開道路」
3. 計入統計的門檻：存活時間 ≥ `min_track_life_secs` **且** 成功辨識幀數 ≥ `min_vote_count`
4. 每台車的進入計數與轉向計數各只發生一次（以 `counted_*` 旗標保證）
5. 車種以生命週期內出現最多次的類別為準（多數決）

---

## 輸出報表說明

每次執行於 `outputs/<年月日_時分秒>/` 產生：

| 檔案 | 內容 | 用途 |
|------|------|------|
| `車輛明細.csv` | 每台車一列：進出道路、車種、時間、區域序列、是否計入 | **人工抽查與準確度驗證** |
| `時段流量.csv` | 時間區間 × 道路 × 車種的車次與 PCU | 尖峰分析、時變特性 |
| `轉向矩陣.csv` | 進入道路 × 離開道路的 OD 矩陣（含行列合計） | 圓環績效與路徑分析 |
| `統計總表.csv` | 全時段各道路車次、車種組成、PCU、平均流率 | 主要成果表 |
| `分析結果.mp4` | 疊加圖層的成果影片（啟用 `save_video` 時） | 結果佐證、對外說明 |

所有 CSV 皆為 UTF-8 with BOM，Windows 的 Excel 可直接雙擊開啟而不亂碼。

---

## 功能現狀

| 功能模組 | 狀態 | 說明 |
|----------|------|------|
| 影像讀取（影片／攝影機／RTSP） | 已完成 | 支援抽幀 |
| YOLO 車輛偵測 | 已完成 | 小客車、機車、大客車、大貨車 |
| ByteTrack 追蹤 | 已完成 | 沿用參考專案的已驗證參數 |
| 車種還原 | 已完成 | IoU 回溯配對 + 多數決 |
| 精確累計計數 | 已完成 | 每台車只計一次 |
| 轉向 OD 矩陣 | 已完成 | 見下方限制說明 |
| PCU 當量換算 | 已完成 | 當量值可於設定檔調整 |
| 時段流量報表 | 已完成 | 區間可設定 |
| 中文視覺化介面 | 已完成 | 微軟正黑體 |
| 成果影片輸出 | 已完成 | |
| 一鍵啟動批次檔 | 已完成 | `START.bat` / `run.bat` / `run_export.bat` |
| **區域座標編輯工具** | 已完成 | `edit_zones.bat`，換影片不必再手改 JSON |
| **準確度驗證模組** | 已完成 | `check_accuracy.bat`，產出誤差率報表 |
| **單元測試** | 已完成 | 232 個測試、覆蓋率 87%，`run_tests.bat` |

### 已知限制（引用數據前必讀）

1. **轉向判定的精度受區域劃設方式影響**：目前的 `roads_polygons.json` 每條聯絡道只有一個多邊形，同時涵蓋進入與離開車道，因此「進入／離開」是以造訪順序推論而非車道級判定。若需要車道級精度，須將每條路拆成獨立的「進入區」與「離開區」多邊形。
2. **僅取得部分軌跡的轉向**：車輛若在畫面外完成離開，或追蹤中斷，則只有進入計數而無轉向紀錄。故轉向筆數必然少於累計車次，兩者不可混用。
3. **模型未針對本地場景微調**：使用 COCO 預訓練權重，對台灣路口常見的密集機車群、遮擋情境準確度會下降，正式使用前應以標的路口影像進行微調與準確度驗證。
4. **尚未取得實際的準確度數據**：驗證工具已完成（`check_accuracy.bat`），
   但還沒有人真的對著影片數過一遍。引用數據前應先跑過一次驗證流程，
   取得該支影片的實際誤差率。

---

## 待開發功能

| 功能 | 狀態 | 目標 | 技術方案 |
|------|------|------|----------|
| 進出區分離的區域定義 | 規劃中 | 提升轉向判定精度至車道級 | 每條路拆為進入區與離開區兩個多邊形 |
| 尖峰小時係數（PHF） | 規劃中 | 交通工程常用指標 | 需 1 小時以上影片，以 15 分鐘區間計算 |
| 模型微調 | 規劃中 | 提升本地場景（密集機車）準確度 | 標註標的路口影像後微調 YOLO |
| 速度估計 | 未排程 | 需要相機標定或參考尺標 | 單應性轉換（homography） |

---

## 開發指引

### 首次環境建置

```
conda create --name traffic python=3.10 -y
conda activate traffic
pip install torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

### 執行

| 方式 | 說明 |
|------|------|
| 雙擊 `run.bat` | 開啟即時預覽視窗，按 `Q` 或 `Esc` 可提前結束（仍會輸出報表） |
| 雙擊 `run_export.bat` | 無視窗，輸出成果影片 + 報表（批次處理用，速度最快） |
| `python main.py` | 同 `run.bat`，但需先手動 `conda activate traffic` |

### 常用命令列覆寫

```
python main.py video_reader.src=D:/我的影片.mp4       指定其他影片
python main.py pipeline.save_video=true               同時輸出成果影片
python main.py pipeline.show_window=false             關閉預覽（加速）
python main.py report_node.interval_seconds=900       改用 15 分鐘統計區間
python main.py detection_node.confidence=0.25         提高偵測門檻
python main.py hydra.job_logging.root.level=DEBUG     觀察各節點耗時
```

### 換一段新影片要做什麼

1. 把影片放進 `test_videos/`，或以 `video_reader.src` 指定路徑
2. **重新繪製 `configs/roads_polygons.json` 的區域座標**（目前座標僅適用內附的測試影片）
3. 依畫面中的道路數量，調整 `general.colors_of_roads`
4. 視拍攝高度與車輛大小，調整 `detection_node.confidence` 與 `general.min_track_life_secs`

### 效能參考（RTX 4070 12GB、1436×926 影片）

| 模式 | 速度 |
|------|------|
| 僅統計（無繪圖） | 約 80 FPS |
| 繪圖 + 影片輸出 | 約 32 FPS |

---

## 專案管理備註

- 所有程式碼註解、文件與畫面 UI 一律使用繁體中文，檔案一律 UTF-8 編碼
- 單支程式不超過 500 行，超過須拆分
- 新增功能建立新檔案，不得堆疊於既有檔案
- 所有可配置的值須置於 `configs/app_config.yaml` 或 `.env`，程式內不寫死
- 新增環境變數時須同步更新 `.env.example`
- `vendor/` 內的第三方程式碼不得修改
- `.bat` 檔內容一律純 ASCII（cmd.exe 在 `chcp` 生效前以 OEM 編碼解析，中文會導致閃退）
- 每次變更須同步更新 `CHANGELOG.md` 與對應資料夾的 `CLAUDE.md`

---

## 變更日誌

詳見 [CHANGELOG.md](./CHANGELOG.md)

---

**文檔版本**：v1.1.0
**建立日期**：2024-12-09
**最後更新**：2026-10-03（v1.1.0 新增單元測試、區域編輯器、準確度驗證）
