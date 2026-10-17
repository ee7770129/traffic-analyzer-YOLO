# tools（獨立工具）

## 模組功能說明

不屬於分析流水線、但使用上必要的輔助工具。各自為可獨立執行的命令列程式，
以 `argparse` 接收參數，不經過 Hydra。

| 工具 | 解決的問題 |
|------|-----------|
| `zone_editor.py` | 換影片時不必手算像素座標去改 JSON |
| `accuracy_check.py` | 自動算出人工計數與系統計數的誤差率 |
| `export_dashboard.py` | 把一次分析的輸出轉成成果展示網頁的資料 |
| `make_web_clip.py` | 從分析錄影剪出網頁用的 30 秒短片（v1.2.1） |

## 技術棧

OpenCV（滑鼠互動與影格讀取）、Pillow（中文繪字）、Python csv、argparse

## 架構依賴圖

```
tools/
├── CLAUDE.md
├── zone_editor.py        道路區域座標編輯器（GUI）
├── accuracy_check.py     準確度驗證（純命令列）
├── export_dashboard.py   成果展示網頁資料匯出（純命令列）
└── make_web_clip.py      成果網頁短片剪輯（純命令列，需 ffmpeg）
```

**相依方向**：

```
tools/ ──→ utils/      （zone_editor 使用 TextDrawer；export_dashboard 使用 cctv_source）
tools/ ──X nodes/      不相依，工具不介入流水線
tools/ ──X core/       不相依
```

`accuracy_check.py` 只相依 Python 標準函式庫，沒有任何專案內部相依，
因此可單獨複製出去使用。

## zone_editor.py — 道路區域座標編輯器

### 為什麼需要

`configs/roads_polygons.json` 的座標只對應特定的攝影機視角。
換一支影片若沒重畫，車輛會被判定到錯誤的道路，所有統計都失去意義。
手動填座標數字既費時又容易出錯，這個工具讓這一步變成用滑鼠框選。

### 操作

| 輸入 | 動作 |
|------|------|
| 左鍵 | 新增一個頂點 |
| 右鍵 / `N` | 完成目前區域（至少三個頂點） |
| `U` | 復原上一個頂點 |
| `D` | 刪除最後一個已完成的區域 |
| `C` | 清空全部 |
| `S` | 存檔 |
| `Q` / `Esc` | 離開（有未存檔變更時會先提醒一次） |
| `+` / `-` | 放大／縮小顯示 |

### 關鍵設計

- **座標換算**：顯示畫面可能被縮小，滑鼠座標必須除以 `scale` 換算回原始解析度後才存入。
  這裡出錯會讓所有區域整組偏移，是最需要測試覆蓋的一段。
- **道路編號**：依完成順序由 1 開始連續編號，與報表中的「道路 N」直接對應。
- **既有設定**：啟動時會載入現有的 JSON 並顯示出來，可在原有基礎上修改。
  設定檔損毀時從空白開始並印出警告，不會讓工具無法啟動。

## accuracy_check.py — 準確度驗證

### 為什麼需要

任何自動計數系統在引用前都必須先證明自己夠準。
本工具把「人工數一遍 → 跟系統比對 → 算出誤差率」這個流程自動化。

### 三步驟流程

```
① 產生範本        python tools/accuracy_check.py --result outputs/<執行時間> --template
                  依系統實際偵測到的道路與車種，預先列好所有組合

② 人工填寫        開啟 人工計數.csv，對著影片把數字填上
                  留空代表尚未驗證，不會被當成 0

③ 比對           python tools/accuracy_check.py --result outputs/<執行時間>
                  輸出 準確度驗證.csv 並在主控台印出摘要
```

### 資料來源的設計決策

系統計數直接由 `車輛明細.csv` **逐筆聚合**而來，而非讀取 `統計總表.csv`。
這樣驗證結果與原始紀錄完全同源，不會因彙總邏輯本身的問題而失真——
事實上本工具第一次執行時就是這樣抓到了報表之間車種分布不一致的問題。

只採計「是否計入統計 = 是」的車輛，與主程式的統計母體完全相同。

### 輸出指標

| 指標 | 意義 |
|------|------|
| 誤差 | 系統計數 − 人工計數（正值代表系統多算） |
| 誤差率 | 絕對誤差 ÷ 人工計數（人工為 0 時標示為「—」） |
| 總量準確率 | 1 − 總量絕對誤差 ÷ 人工總計 |
| 分項 MAPE | 各項誤差率的平均，只納入人工計數不為零的項目 |
| 平均／最大絕對誤差 | 以「輛」為單位，看絕對量而非比例 |

### 人工計數檔格式

支援兩種，依欄位自動判斷：

```
含車種（逐車種比對）          僅道路（只比總量）
道路,車種,人工計數            道路,人工計數
1,小客車,10                   1,10
1,機車,3                      2,8
```

## export_dashboard.py — 成果展示網頁資料匯出

### 為什麼需要

分析需要 GPU 與 OpenCV，無法在靜態網站代管服務上執行。
網頁（`web/`）因此只負責呈現，數據由本工具從輸出資料夾轉出：

| 產出 | 來源 |
|------|------|
| `web/data/summary.json` | 各路口的 `車輛明細.csv`、三份越線報表、`尖峰小時係數.csv`，以及路口目錄 |
| `web/assets/heatmap_<路口>.jpg` | 各路口的 `軌跡熱力圖.png` |
| `web/assets/result.jpg` | `多路口畫面.jpg`；沒有時改取 `分析結果.mp4` 中的一幀（預設 90% 位置） |

來源檔不存在時該項略過，不會中斷。要更新網頁數據時，重新執行本工具後再部署一次。

多路口模式的輸出資料夾內，每個路口各有一個以預設組名稱命名的子資料夾，工具會自動辨識；
單路口模式的報表直接放在輸出資料夾，須以 `--camera` 指明是哪個路口。

```
python tools/export_dashboard.py --run outputs/<執行時間>                          多路口
python tools/export_dashboard.py --run outputs/<執行時間> --camera wuquan_fuxing   單路口
```

## make_web_clip.py — 成果網頁短片剪輯

### 為什麼需要

成果網頁原本只有一張截圖，看不出系統「在跑」。錄影動輒數百 MB，不能直接放進儲存庫，
本工具把它剪成約 30 秒、5 MB 以下、瀏覽器與手機可直接播放的短片 `web/assets/result.mp4`。

### 流程

```
① 找錄影       多路口錄影.mp4（multi_view.record_video=true）優先，其次 分析結果.mp4
② 挑片段       讀所有 越線明細.csv 的「時間_秒」，找出越線車次最多的 duration_secs 秒
               （略過開頭 skip_head_secs 秒，片段須完整落在影片內）
③ 轉檔         ffmpeg：H.264、yuv420p、無音訊、faststart
④ 控制大小     位元率 = max_size_mb × size_fill_ratio ÷ 片段長度；
               仍超過上限時乘上 retry_scale 重試，最多 max_attempts 次
```

### 關鍵設計

- **時間對齊**：即時串流的報表時間是自第一幀起算的系統時間，錄影器也依經過時間補幀，
  兩者只差連線所需的數秒，因此可直接用越線時間挑片段。
- **以位元率控制大小**：Anaconda 內附的 ffmpeg 不含 libx264，預設改用 Windows 內建的 `h264_mf`，
  它不支援 crf，但所有編碼器都支援位元率。編碼器由 `web_clip.video_codec`（`TRAFFIC_VIDEO_CODEC`）切換。
- **ffmpeg 不寫死**：路徑來自設定檔 `web_clip.ffmpeg_bin`（環境變數 `TRAFFIC_FFMPEG_BIN`），
  外部指令的執行函式可替換，測試不需要安裝 ffmpeg。

```
python tools/make_web_clip.py --run outputs/<執行時間>              自動挑選片段
python tools/make_web_clip.py --run outputs/<執行時間> --start 120  指定起點（秒）
```

## 開發指令

```
python tools/zone_editor.py --video test_videos/my.mp4 --frame 300
python tools/accuracy_check.py --result outputs/20250224_143052 --template
python tools/accuracy_check.py --result outputs/20250224_143052
```

亦可直接雙擊 `edit_zones.bat` 與 `check_accuracy.bat`。

## 新增工具的原則

- 放在本資料夾，不得加入流水線
- 以 `argparse` 接參數，預設值可由環境變數覆寫，不得寫死路徑
- 純邏輯與 GUI 迴圈分離，讓邏輯部分能被單元測試覆蓋
- 在 `tests/` 補上對應測試，並於本文件登記

## 變更日誌參考

詳見 `../CHANGELOG.md`

---
**建立日期**：2026-10-03
**最後更新**：2026-10-17（v1.2.1 新增 make_web_clip 成果網頁短片剪輯）
