# SNAPSHOT
2026-11-07（Claude Code）：規格升為 v1.3.0（specs/requirements.md）。Stage 0/1 PASS；Stage 2～8 程式完成，
GPU 批次 A～D 全部未執行，沒有新的 PASS。本機（Windows 11、Python 3.13.15）189 passed、7 skipped，ruff 通過。
五分頁全部有實作：文生圖與排版、多圖修圖、筆刷重繪、視覺與深度控制、模型與高解析；專案選單可匯出入。
本次變更尚未 commit／push；Colab Notebook 從 GitHub main 取碼，推送前 Colab 用不到這些改動。

# DECISIONS
v1.3：視覺參考降為實驗；2K 改為原生 ≤2.2 MP＋分段放大，原生 2048² 為實驗；刪 FP8 編碼器；
fast8 依作者 Space（lora_latest 0.7、8 步、CFG 1）；edit／control 依官方 workflow_templates 參數。
GPU 驗收批次化：前一階段程式完成即可開發下一階段，PASS 需 GPU 批次證據。
Gradio 只當外殼；新分頁都用自訂 HTML＋static/*.js（api.js 共用），不用 gr.ImageEditor（需 SSE）。
inpaint 柔邊外逐像素保留原圖由後端合成保證；遮罩在工作尺寸繪製以限制 undo 記憶體。
模型頁只能下載 models.lock.json 內項目；使用者自加 HF LoRA 延後。專案匯入一律新 id、不帶工作歷史。

# VALIDATION
CPU：189 passed／7 skipped（3 載入探測、2 長 GPU、1 /proc、1 symlink）。node --check 全部前端模組。
假引擎瀏覽器（scripts/dev_server.py，非 GPU 證據）：五分頁主流程、fast8 負向詞攔截、修圖空格重編號、
重繪空遮罩攔截與原圖保留、控制兩子模式、模型表與分段放大、專案匯出→匯入→開啟。
GPU 證據仍只有 Stage 1 與 docs/evidence/stage2/benchmark.json（未完成的 checkpoint）。
曾出現一次 test_saved_result 間歇失敗，推測為 Windows LK_LOCK 1 秒重試；改非阻塞輪詢後連跑 4 次全過。

# LANDMINES
不要把假引擎、CPU 測試或 docs/stages/stage3-8.md 的「程式完成」寫成 PASS。
瀏覽器工具的 type 動作不觸發 Gradio input 事件；測試草稿保存要用實際按鍵（key）。
Gradio 收合區塊與分頁延遲建立 DOM：新分頁用 tab.select 載入模組，專案選單用事件委派。
Windows 預設 cp950：讀 JSON 設定一律 encoding="utf-8"。
runtime.lock.json 的 engine_vram_mode 仍是 lowvram；批次 B 量測後才改。
引擎輸入檔名必須以 moss_ 開頭（ComfyClient.upload_image 檢查）。
Colab：ROOT=/content/moss-stage1、資料 /content/moss-studio、證據 /content/moss-evidence；勿提交私有 URL／密碼／輸出。
上一輪（GPT）Colab 自動化曾遇瀏覽器審核額度限制，未繞過；重跑前先讀 benchmark.json，不重送。

# HISTORY
建立公開 GitHub 倉庫後開始 Stage 0；使用者授權用瀏覽器開 Colab 執行驗證（GPT 階段）。
2026-11-07：Claude Code 依審查改寫規格 v1.3.0，完成 Stage 2 收尾與 Stage 3～8 程式；未執行 GPU 批次、未推送。
