# 路口車流分析系統（TrafficAnalyzer_TW）- 系統說明

## 專案定位

**開發期間**：2024 年 12 月 ～ 2025 年 2 月　|　**目前版本**：v1.2.0（2026-10-08）

> 安裝與操作說明請見 [README.md](./README.md)，本文件著重於架構與設計決策。

以電腦視覺自動化產出路口／圓環車流調查數據，取代人工計數，供交通工程分析使用。

系統輸入一段路口影片（或即時攝影機串流），輸出：

- 各方向的**精確累計車次**（可與人工計數逐筆核對）
- **車種分類統計**與小客車當量（PCU）
- **轉向 OD 矩陣**（由第 i 條路進入、由第 j 條路離開的車輛數）
- **時段流量報表**（可設定統計區間）
- 帶有疊加圖層的**成果影片**
- **越線計數**（各聯絡道進入與離開路口的車次，v1.2.0）
- **軌跡熱力圖**與**尖峰小時係數**（v1.2.0）

v1.2.0 起可直接分析**臺中市交通局的路口即時影像**，已內建中興大學周邊七個路口的設定，
並可**同時分析多個路口**，以寬螢幕版面顯示（左側路口畫面、右側詳細資料）。

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
| 成果網頁 | `web/` | 純靜態展示頁，不執行分析，數據由 `tools/export_dashboard.py` 匯出 |

**溝通用詞統一**：

- 「道路 N」：圓環的第 N 條聯絡道，編號對應 `configs/roads_polygons.json`
- 「進入道路」：車輛第一個踩到的區域
- 「離開道路」：車輛之後第一個踩到的、不同於進入道路的區域
- 「轉向紀錄」：一筆完整的「進入→離開」配對
- 「計數線」：橫跨一條聯絡道的線段，車輛越過即計一次，方向分「進入」與「離開」
- 「路口預設組」：`configs/cctv_cameras.yaml` 中登記的一個路口（攝影機編號 + 區域 + 計數線）

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
| 指派問題求解 | SciPy | >= 1.10 | 經由根目錄的 `lap.py` 相容層供 ByteTrack 使用 |
| 成果網頁 | 純 HTML / CSS / JavaScript | — | 無建置步驟，可部署於任何靜態代管服務 |

**執行環境**：Python 3.10（conda 環境名稱 `traffic`）、Windows 11、NVIDIA GPU（CPU 亦可執行但速度大幅下降）。

---

## 端口配置

本專案為**離線分析工具，不對外開放任何服務端口**。

`web/` 為純靜態檔案，部署於靜態代管服務，本機不需啟動伺服器。
分析即時影像時，程式會**對外連線**到臺中市交通局的伺服器（HTTPS 443）取得串流。

若未來需要新增本機網頁服務，端口須以環境變數管理，並於本節補上對照表。

---

## 架構依賴圖

```
TrafficAnalyzer_TW/
├── START.bat                        建議入口：先檢查素材齊全再啟動
├── run.bat                          一鍵啟動（即時預覽視窗）
├── run_export.bat                   批次匯出（無視窗，輸出影片 + 報表）
├── run_cctv.bat                     分析路口即時影像（可指定路口預設組）
├── run_multi.bat                    多路口同步分析（寬螢幕版面）
├── edit_zones.bat                   開啟區域座標編輯器
├── check_accuracy.bat               準確度驗證
├── run_tests.bat                    執行單元測試與覆蓋率
├── _find_python.bat                 批次檔共用的 conda 環境尋找邏輯
├── pytest.ini                       測試探索規則與覆蓋率門檻
├── main.py                          主程式進入點，組裝流水線
├── pipeline_builder.py              依設定建立擴充節點、解析影像來源
├── multi_view.py                    多路口同步分析進入點
├── cython_bbox.py                   Windows 相容層（純 NumPy 版 bbox_overlaps）
├── lap.py                           相容層（以 SciPy 實作 lapjv，免載入編譯檔）
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
│   ├── roads_polygons.json          道路區域座標（內附測試影片用）
│   ├── cctv_cameras.yaml            路口 CCTV 目錄（七個路口預設組）
│   ├── cctv/<路口>_zones.json       各路口的區域座標
│   ├── cctv/<路口>_lines.json       各路口的計數線
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
│   ├── video_writer_node.py         成果影片輸出
│   ├── line_counting_node.py        越線計數
│   ├── line_render_node.py          計數線繪製
│   ├── line_report_node.py          越線報表輸出
│   ├── heatmap_node.py              軌跡熱力圖
│   └── phf_report_node.py           尖峰小時係數報表
│
├── utils/                           共用工具（詳見 utils/CLAUDE.md）
│   ├── geometry.py                  多邊形判定與 IoU
│   ├── vehicle_types.py             車種對照與 PCU 當量
│   ├── text_drawer.py               中文文字繪製
│   ├── fps_counter.py               FPS 計算
│   ├── profiler.py                  效能計時
│   ├── line_geometry.py             計數線幾何
│   ├── phf.py                       尖峰小時係數計算
│   ├── cctv_source.py               路口 CCTV 來源解析
│   ├── direction_gate.py            依行進方向判定進入或離開
│   └── vendor_path.py               第三方套件路徑註冊
│
├── multiview/                       多路口同步分析
│   ├── camera_pipeline.py           單一路口的完整流水線
│   ├── camera_worker.py             讓一條流水線在自己的執行緒中運作
│   ├── mosaic.py                    多格畫面排版
│   ├── detail_panel.py              右側詳細資料面板
│   └── flow_history.py              每分鐘車流紀錄
│
├── tools/                           獨立工具（詳見 tools/CLAUDE.md）
│   ├── zone_editor.py               道路區域座標編輯器
│   ├── accuracy_check.py            準確度驗證
│   └── export_dashboard.py          成果展示網頁資料匯出
│
├── tests/                           單元測試（詳見 tests/CLAUDE.md）
│   ├── conftest.py                  共用設定與 fixture
│   └── test_*.py                    351 個測試，覆蓋率 91%
│
├── web/                             成果展示網頁（純靜態）
│   ├── index.html / styles.css / app.js
│   ├── data/summary.json            由 export_dashboard.py 產生
│   └── assets/                      熱力圖與代表畫面
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

v1.2.0 的擴充節點依設定插入上述流程（由 `pipeline_builder.py` 建立）：

```
CountingNode 之後  →  LineCountingNode   附加 line_events / statistics["越線計數"]
RenderNode 之後    →  LineRenderNode     在 frame_result 上加畫計數線
ReportNode 之後    →  LineReportNode     輸出 3 份越線 CSV
                      HeatmapNode        輸出 軌跡熱力圖.png
                      PhfReportNode      輸出 尖峰小時係數.csv
```

指定路口預設組時的來源解析：

```
cctv.camera=wuquan_fuxing
   → cctv_cameras.yaml 查出攝影機編號、區域檔、計數線檔
   → 向交通局攝影機頁面查出目前的串流網址
   → VideoReaderNode 以該網址讀取（中斷時自動重連）
```

多路口模式（`multi_view.py`）：

```
multi_view.cameras 的每個路口
   → CameraPipeline（各自獨立的模型、追蹤器、計數器、輸出資料夾）
   → CameraWorker（各自一條執行緒，以攝影機的實際速度前進）
主執行緒定期取各路口的最新畫面與統計
   → mosaic 排成左側的路口畫面
   → DetailPanel 繪製右側的詳細資料
```

**計數判定規則**（決定數據可信度的核心）：

1. 車輛中心點落入某區域 → 第一個區域記為「進入道路」
2. 之後落入不同區域 → 記為「離開道路」
3. 計入統計的門檻：存活時間 ≥ `min_track_life_secs` **且** 成功辨識幀數 ≥ `min_vote_count`
4. 每台車的進入計數與轉向計數各只發生一次（以 `counted_*` 旗標保證）
5. 車種以生命週期內出現最多次的類別為準（多數決）
6. 有路口參考點時（即時影像的路口預設組）改為**依行進方向判定**：
   車輛第一次出現在某區域時先不下結論，等它移動後比較與路口中心的距離，
   朝路口內行駛才記為進入道路；朝路口外行駛則只記離開道路、進入道路未知，不計入進入流量。
   未提供參考點時（內附測試影片）維持規則 1 的原行為

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
| `越線明細.csv` | 每次越線一列：時間、計數線、方向、車種 | 越線計數的逐筆核對 |
| `越線計數.csv` | 計數線 × 方向 × 車種的車次與 PCU | 各聯絡道的進入量與離開量 |
| `越線轉向矩陣.csv` | 由哪條線進入、由哪條線離開 | 以越線方向判定的 OD 矩陣 |
| `軌跡熱力圖.png` | 車輛位置累積的熱力圖 | 觀察動線與停等位置 |
| `尖峰小時係數.csv` | 全路口與各道路的 PHF | 需觀測滿一小時才有數值 |

越線相關的三份報表只在有指定計數線設定檔時產生。

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
| **單元測試** | 已完成 | 351 個測試、覆蓋率 91%，`run_tests.bat` |
| **路口即時影像分析** | 已完成 | `run_cctv.bat`，內建七個中興大學周邊路口，串流中斷自動重連 |
| **多路口同步分析** | 已完成 | `run_multi.bat`，預設兩個路口上下排列，右側為詳細資料面板 |
| **進入方向判定** | 已完成 | 朝路口外行駛的車不再被誤判為進入 |
| **越線計數** | 已完成 | 依越線方向區分進入與離開，低幀率下不漏判 |
| **軌跡熱力圖** | 已完成 | 分析結束時輸出 |
| **尖峰小時係數（PHF）** | 已完成 | 需觀測滿一小時 |
| **成果展示網頁** | 已完成 | `web/`，以 `tools/export_dashboard.py` 更新數據 |

### 已知限制（引用數據前必讀）

1. **轉向判定的精度受區域劃設方式影響**：目前的 `roads_polygons.json` 每條聯絡道只有一個多邊形，同時涵蓋進入與離開車道，因此「進入／離開」是以造訪順序推論而非車道級判定。若需要車道級精度，須將每條路拆成獨立的「進入區」與「離開區」多邊形。
2. **僅取得部分軌跡的轉向**：車輛若在畫面外完成離開，或追蹤中斷，則只有進入計數而無轉向紀錄。故轉向筆數必然少於累計車次，兩者不可混用。
3. **模型未針對本地場景微調**：使用 COCO 預訓練權重，對台灣路口常見的密集機車群、遮擋情境準確度會下降，正式使用前應以標的路口影像進行微調與準確度驗證。
4. **七個路口的區域與計數線為初步劃設**：依單張畫面目測繪製，尚未逐一校正。
   正式使用前須以 `edit_zones.bat` 校正。
5. **即時影像幀率偏低**：實測每秒 5 至 10 幀，且串流會不定時中斷。
   追蹤參數仍沿用高幀率影片的設定，尚未針對低幀率調校；重連期間通過的車輛不會被計入。
6. **夜間與遠處的機車容易漏偵測**：實測畫面中可見未被框出的機車。
7. **熱力圖混合了車流量與停等時間**：亮點可能是車多，也可能只是有車停很久。
9. **同一台車可能被拆成兩筆紀錄**：追蹤短暫中斷後又以相同編號接回時，報表會出現兩筆，
   可能造成重複計數。低幀率與串流重連時較常發生，尚未處理。
10. **部分攝影機不適合長期使用**（2026-10-09 白天實測）：
    五權路／民生路白天僅約 6 FPS，多人同時連線時掉到 2 至 4 FPS，會嚴重漏計；
    五權路／復興路的鏡頭會轉動變焦，白天的視角已與前一晚不同，現有區域對不上。
    多路口模式因此預設改用五權西路／美村路與文心南路／復興路，
    這兩支在日夜兩次抽查中視角相同、白天仍有約 10 FPS。但「兩次抽查」不代表永遠不動，
    每次分析前仍應先看畫面確認區域有對上。
11. **推估小時流量只是把目前平均流率換算成一小時**，觀測時間短時波動很大，不可當作實測值引用。
8. **尚未取得實際的準確度數據**：驗證工具已完成（`check_accuracy.bat`），
   但還沒有人真的對著影片數過一遍。引用數據前應先跑過一次驗證流程，
   取得該支影片的實際誤差率。

---

## 待開發功能

| 功能 | 狀態 | 目標 | 技術方案 |
|------|------|------|----------|
| 計數線編輯工具 | 規劃中 | 免手改計數線 JSON | 比照 `zone_editor.py` 以滑鼠畫線 |
| 低幀率追蹤調校 | 規劃中 | 降低即時影像的追蹤中斷 | 依實測幀率調整 ByteTrack 參數，或評估含外觀特徵的追蹤器 |
| 行人與自行車偵測 | 規劃中 | 行人穿越量、人車衝突 | 需濾除機車騎士被誤判為行人的情況，並與車輛分開追蹤 |
| 停等長度與延滯 | 規劃中 | 路口服務水準 | 需定義停止線與停等區 |
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
| 雙擊 `run_cctv.bat` | 分析路口即時影像，預設五權路／復興路，按 `Q` 結束並輸出報表 |
| `run_cctv.bat wuquannan_gaogong` | 改分析其他路口預設組 |
| 雙擊 `run_multi.bat` | 同時分析 `multi_view.cameras` 列出的路口，寬螢幕版面，按 `Q` 結束 |

### 常用命令列覆寫

```
python main.py video_reader.src=D:/我的影片.mp4       指定其他影片
python main.py pipeline.save_video=true               同時輸出成果影片
python main.py pipeline.show_window=false             關閉預覽（加速）
python main.py report_node.interval_seconds=900       改用 15 分鐘統計區間
python main.py detection_node.confidence=0.25         提高偵測門檻
python main.py hydra.job_logging.root.level=DEBUG     觀察各節點耗時
python main.py cctv.camera=wuquan_fuxing              分析路口即時影像
python main.py cctv.camera=wuquan_fuxing cctv.max_duration_secs=3600   分析一小時後自動結束
python main.py line_counting.lines_file=configs/cctv/wuquan_fuxing_lines.json   本機影片搭配計數線
```

### 更新成果展示網頁

```
python tools/export_dashboard.py --run outputs/<執行時間> --camera wuquan_fuxing
```

執行後 `web/` 內的數據與圖片即更新，重新部署 `web/` 資料夾即可。

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
- 根目錄的 `lap.py`、`cython_bbox.py` 是刻意遮蔽同名已安裝套件的相容層，不可改名或搬移
- 即時影像來自臺中市政府交通局，對外發表成果前須確認其開放資料授權條款

---

## 變更日誌

詳見 [CHANGELOG.md](./CHANGELOG.md)

---

**文檔版本**：v1.2.0
**建立日期**：2024-12-09
**最後更新**：2026-10-09（v1.2.0 新增多路口同步分析、詳細資料面板、進入方向判定）
