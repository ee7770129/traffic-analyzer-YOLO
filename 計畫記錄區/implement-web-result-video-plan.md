# 成果網頁加入分析影片

## 專案位置
**絕對路徑**：`D:\中興大學\YOLO 路口車流數據\TrafficAnalyzer_TW`
**相對根目錄**：`./`

## 計畫概述
**功能類型**：實作
**目標說明**：成果展示網頁（Vercel，部署 `research/nchu` 分支的 `web/`）原本只有靜態截圖，
改為自動循環播放約 30 秒的多路口分析影片（含右側詳細資料面板），影片與網頁數字來自同一次執行。
**影響範圍**：
- 新增：`multiview/mosaic_recorder.py`、`tools/make_web_clip.py`、對應測試
- 小幅修改：`multi_view.py`（掛上錄影，預設關閉）、`web/index.html`、`web/styles.css`
- 設定：`configs/app_config.yaml`（`multi_view.record_*`、`web_clip`）、`.env.example`
- 數據：`web/data/summary.json`、`web/assets/*` 以新錄影重新匯出
- 文件：CHANGELOG（v1.2.1）、CLAUDE.md（根、tools、tests）、README

### [2026-10-17 23:17] 指令記錄
**收到指令**：
```
（在 Railway / 免費 GPU 方案討論後）用 A 吧（網頁放分析結果影片），你準備一下，晚點我要睡了讓你弄。
確認事項：今晚重錄兩個路口（五權西路／美村路、文心南路／復興路）；約 30 秒、小於 5MB；
影片包含右側詳細資料面板；今晚錄、全部做完；只 commit 到 research/nchu，不 push，
使用者早上看過再 push；同意建立本計畫檔。
```

**執行環境**：
- 作業系統：Windows 11
- 開發工具：Claude Code
- 相關技術：Python 3.10（conda env `traffic`）、OpenCV、ffmpeg、Hydra、靜態 HTML

**執行計畫**：
1. [✓] **錄影模組 `multiview/mosaic_recorder.py`**
   - 完成時間：2026-10-17 23:19
   - 依實際經過時間補幀；先寫 ASCII 暫存檔再改名；`record_video` 預設 false
2. [✓] **`multi_view.py` 掛上錄影**（新增 6 行）
   - 完成時間：2026-10-17 23:19
3. [✓] **剪輯工具 `tools/make_web_clip.py`**
   - 完成時間：2026-10-17 23:35
   - 問題：Anaconda 的 ffmpeg 6.1.1 不含 libx264（`Unrecognized option 'preset'`）
   - 解法：改用 Windows 內建 `h264_mf`，並以「大小預算 → 位元率」控制檔案大小（h264_mf 不支援 crf），
     編碼器可由 `web_clip.video_codec` / `TRAFFIC_VIDEO_CODEC` 切換
4. [✓] **錄影**：`outputs/20261017_231930`，600 秒、兩路口皆成功
   - 五權西路／美村路 累計 50 輛（越線 進 48 出 74）；文心南路／復興路 累計 144 輛（進 104 出 108）
   - 串流約每 30 秒中斷並自動重連（已知現象）
5. [✓] **重新匯出網頁數據與短片**
   - 短片取第 228～258 秒（越線 33 車次），1280×664、10 fps、3.97 MB
   - 抽幀檢查：畫面清楚、文字可讀，面板「已分析 04:03」與影片時間一致
6. [✓] **網頁**：`<video autoplay muted loop playsinline poster=result.jpg>`，本機伺服器驗證所有檔案 200
7. [✓] **測試**：新增 21 個，全部 375 個通過、覆蓋率 92%，測試產物已清除
8. [✓] **文件**：CHANGELOG v1.2.1、CLAUDE.md（根、tools、tests）、README、`app_config.yaml`、`.env.example`
9. [✓] **commit 到 research/nchu**（不 push）

**預期成果**：
- `web/assets/result.mp4` 約 30 秒、小於 5MB，網頁自動循環播放，手機可播
- 網頁數字、熱力圖與影片來自同一次錄影
- 原有測試全數通過，新增模組皆有測試

**風險評估**：
- 深夜車少且為夜間黑白畫面：使用者已知悉並同意
- CCTV 串流中斷：讀取節點已有自動重連；若某路口全程失敗，改錄單一路口並回報
- 影片公開涉及交通局影像授權：由使用者 push 前確認

**回滾方式**：`git revert` 本次 commit；`web/` 舊版數據可由 commit `5c60497` 取回。
