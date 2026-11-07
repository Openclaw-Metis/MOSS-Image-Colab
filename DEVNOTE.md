# SNAPSHOT
2026-11-07：Stage 0/1 PASS；Stage 2 開發中。Stage 1 新 checkout/venv 重演 52 tests PASS。
瀏覽器 Colab 已分配 NVIDIA L4、23,659,151,360 bytes VRAM、56,863,301,632 bytes RAM。
Python 3.13.16、torch 2.14.1+cu130、CUDA 13.0、driver 580.82.07。
文字/vision/edit 三條單步載入探測成功（workflows/probes）；四個下載權重 SHA256 通過。
Quick Tunnel + scripts/polling_probe.py 已完成瀏覽器登入、真實 GPU 出圖、PNG/ZIP 下載。
瀏覽器自動檔案上傳缺擴充功能 file URLs 權限；使用者已手動上傳，vision UI 探測 PASS。
實際取消 cancelling→cancelled，reload 找回相同工作。JS-only callbacks，無 heartbeat/SSE 依賴。

# DECISIONS
沿用規格 v1.2.0（specs/requirements.md），必要 gate 未過不聲稱全功能。
Stage 0 runtime 無第三方依賴；開發工具以 requirements-dev.lock 固定。
Project 刪除先移 trash，可恢復；資產回收與活動工作屏障留待服務層。

# VALIDATION
docs/stages/stage0.md、stage1.md；Stage1 Colab 52 passed（含3真實GPU）；ruff PASS。
Stage2 已有排版編譯、SVG 拉框、Gradio 五 tab 導航（目前僅第一 tab 實作）、
HTTP 認證/CSRF、單 GPU 排程、WS 真進度、原子素材/結果保存與草稿 CAS。
本地 110 passed + 4 GPU skipped；ruff/Python/JS 語法 PASS，完整 UI build PASS，backend callbacks=0。
正式 UI 已在新 Colab 啟動；登入、拖曳拉框、文字/數值編輯、JSON錯誤保留與有效套用、
草稿保存及 reload 找回 queued 工作已觀察。修正 accordion lazy DOM、深色對比與 focus 捲動偏移。
尚未觀察排版最終結果/下載，也未收齊五筆正式基準，勿標 Stage2 PASS。
Stage2 quality50 初次長測觀察到 warmup 124.142s、第一筆正式樣本 112.485s，均1024²非黑圖。
之後 Colab 換成新 kernel/VM（ipykernel 1662→3069，執行計數重置、models/source/results 消失）。
完整5樣本結果未取回，不算 AC-04 PASS；需重建環境並把新結果頻繁同步回工作區。
新 VM 已重建，四個權重校驗通過；Xet429以已驗證低併發設定與有限退避恢復。
新基準已觀察暖機127.616s、正式第一筆113.801s；checkpoint見docs/evidence/stage2/benchmark.json。
完整暖機PNG及hash已取回；其他原圖仍待取回。不要把checkpoint running當成失敗或成功。
docs/compatibility.md 記載實際載入與通道結果；AC-01～18 仍未全面放行。

# LANDMINES
目前正式 ui/app.py 的第一分頁已可操作；其餘四分頁尚未實作。
瀏覽器自動審核於讀取正式UI時拒絕，原因usage limit；不是使用者拒絕，也不是判定動作不安全。
不得改用其他瀏覽器/間接通道繞過；待額度恢復後，先讀現有Colab輸出及benchmark報告，勿重送工作。
Colab：ROOT=/content/moss-stage1、code_root=/content/moss-code-stage2。
固定基準背景程序bench_process，報告ROOT/evidence/stage2/benchmark.json，log為stage2-benchmark.log。
排版UI工作種子9223372036854775807，最後觀察sampling25/50；reload已找回同一工作。
最新本地HTTP request lookup與JS pending去重尚未同步Colab；必須待現有工作結束才重啟app_manager。
先取回報告/原圖，再同步差異、驗證正式UI結果/下載/取消/重連及五筆基準，通過後才能進Stage3。
冷安裝修正：bootstrap 不用 --no-checkout，避免新 clone 被誤判 dirty；有真實 git 回歸測試。
當前 Colab Python 3.13 與規格草稿時可能不同，安裝須驗證相容，不盲降版本。
不得把 CPU/mock 測試或權重檔名存在標成 released capability。
原生 TextEncodeMOSSImageEdit 無 VAE 時可直接使用 vision conditioning；不先裝社群外掛。
polling_probe 的 JS-only Gradio callbacks 不用 SSE；認證 middleware 同時保護 Gradio/資產/API。
瀏覽器 Colab Notebook 名稱 MOSS_Image_Stage1_Validation；勿提交其私有 URL/密碼/輸出。

# HISTORY
建立公開 GitHub 倉庫後開始 Stage 0；使用者授權用瀏覽器開 Colab 執行驗證。
