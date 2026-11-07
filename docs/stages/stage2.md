# Stage 2：文生圖與排版垂直切片

狀態：開發及實機驗證中；尚未 PASS。

已實作真正的 Gradio 提示詞／尺寸／種子輸入、SVG 排版畫布與 JSON 雙向編輯、
單 GPU 排程、不可變工作快照、實際引擎進度、取消、素材及結果原子保存。
四個後續功能分頁明示尚未完成，沒有可提交的假控制項。

傳輸沿用 Stage 1 通過的同源 HTTP 輪詢；全部 Gradio callbacks 為 client-only，
`backend_fn=false`、`connect_heartbeat=false`，不使用 Quick Tunnel 不支援的 SSE。
登入保護涵蓋 UI、設定、靜態程式、API、作品；變更 API 另驗證 CSRF 及 Origin。

本地驗證：110 passed，4 個實機 GPU 測試 skipped；ruff、Python 編譯、兩個 JS 語法檢查通過。
其中 30 組正方／橫／直畫布座標回轉全部誤差 ≤1 原圖像素。
故障注入涵蓋草稿 CAS、重複提交、佇列上限、精確種子、結果保存失敗與引擎狀態不明。
引擎未確認結束時，工作為 interrupted，後續 GPU 工作被阻擋，不偽報 cancelled。

`scripts/benchmark_http.py` 透過產品 API 執行暖機一次及五次正式 1024²／50 步工作，
逐張保存 benchmark JSON、JobRecord、完整 PNG 與 SHA256。`tests/gpu/test_t2i.py`
需明確設定 `MOSS_RUN_LONG_GPU=1`、`MOSS_EVIDENCE_ROOT` 及記憶體內的入口密碼才執行。

## 中斷與恢復證據

第一次長測曾完成暖機 124.142 秒、第一筆 112.485 秒；之後 Colab 換到新 VM，
其餘結果與完整圖檔沒有取回，因此不計為 AC-04 通過。

新 VM 恢復時 Hugging Face Xet CDN 回報 429。保留已校驗 SFT，
在固定 hf_xet 1.8.0 上實際檢查 `XetConfig`，確認下載併發上限 2、初始 1、單檔下載組 1
的環境設定生效，再以官方客戶端續傳。外層最多三次重試，尊重 Retry-After；
401／403／404／hash 錯誤不重試。不記錄 token 或簽名 CDN URL。

正式 UI 已觀察登入、拉框、文字與數值編輯、非法 JSON 保留畫布、有效 JSON 套用、
草稿保存、reload 找回同一 queued 工作，以及該工作的真實 sampling 25/50。
實機修正包含收合 accordion 尚未建立 DOM、深色模式對比，以及 SVG focus 自動捲動造成的拖曳偏移。

新基準已取回暖機 127.616 秒及第一筆正式 113.801 秒的紀錄；完整暖機原圖與 hash 已保存。
`docs/evidence/stage2/benchmark.json` 是中途 checkpoint，不是完整 PASS 報告。
其餘原圖及後續結果尚未取回，不能假設背景程序已完成。

剩餘實測遭瀏覽器自動審核系統阻擋（usage limit）；沒有繞過限制。
完成條件仍待：排版最終結果／保存／下載，以及完整五筆正式 GPU 基準。
最新 request-id 找回端點及前端 pending request 去重僅通過本地驗證，仍須同步 Colab 重測。
