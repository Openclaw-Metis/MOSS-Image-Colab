# SNAPSHOT
2026-11-08（Claude Code）：規格 v1.3.0。PR #2（8218cc3）、PR #3（b00af07）已合併進 main；目前分支 stage10-rehearsal-2026.11.08。
Stage 0～3、5、7、8 PASS；Stage 4、6 有條件通過（修圖 3～4 張、輪廓控制未通過，使用者接受限制並在介面標示）。
GPU 批次 C、D、兩次重測與 AC-15 新 VM 匯入都已完成，證據在 docs/evidence/stage4-6-batch-c、stage7-8-batch-d。
Stage 9 精簡批次 E（AC-01、preflight、契約測試、AC-06、AC-18）與 AC-03 通道實測都已完成（docs/evidence/stage9-batch-e、stage9-ac03）；
必要 AC 除 AC-08、AC-11 有條件通過外全數 PASS。Stage 10 文件完成（docs/stages/stage10.md），
使用者已依 README 在乾淨 L4 重演並回報正常（含第 2 格預設下載，未取回證據檔），Stage 10 完成；仍是開發版。
剩下未驗：自加 HF LoRA 的 GPU 實測。
本機（Windows 11、Python 3.13.15）213 passed、7 skipped，ruff 通過。

2026-11-11（Claude Code）：UI／UX 優化（分支 claude/modest-pascal-yhdct5）屬「程式完成」，只在假引擎驗過，未在 L4 重跑；
沒有改任何工作流、profile 或 JobSpec，既有 GPU 證據不受影響。Linux、Python 3.13.18：218 passed、5 skipped，ruff 通過。

# DECISIONS
v1.3：視覺參考降為實驗；2K 改為原生 ≤2.2 MP＋分段放大，原生 2048² 為實驗；刪 FP8 編碼器；
fast8 依作者 Space（lora_latest 0.7、8 步、CFG 1）；edit／control 依官方 workflow_templates 參數。
GPU 驗收批次化：前一階段程式完成即可開發下一階段，PASS 需 GPU 批次證據。
Gradio 只當外殼；新分頁都用自訂 HTML＋static/*.js（api.js 共用），不用 gr.ImageEditor（需 SSE）。
inpaint 柔邊外逐像素保留原圖由後端合成保證；遮罩在工作尺寸繪製以限制 undo 記憶體。
模型頁只能下載 models.lock.json 內項目與自加 LoRA；專案匯入一律新 id、不帶工作歷史。
自加 HF LoRA：使用者給 repo＋40 碼 commit＋路徑，向 Hub 匿名查 paths-info 取 LFS SHA256 與大小鎖定（≤2 GiB、最多 20 個），
存 data_root/user_loras.json（載入時重驗），檔名固定 loras/user_<sha12>.safetensors；只有宣告 user_loras 的預設（quality50）可疊加，最多 2 個、強度 0～2。
介面上「已通過／尚未通過 GPU 驗收」一律取自 capabilities.json，不在前端寫死。
HF token（選填）：第 2 格勾 USE_HF_TOKEN 時只從 Colab Secrets 讀 HF_TOKEN 放進環境變數（不提供明文表單欄位，
@param 會留在 Notebook 原始碼）；downloads.hub_token() 給下載與自加 LoRA 查詢用，沒設就匿名。huggingface_hub 1.33.0 在轉址到他站 CDN 前會移除 authorization（file_download.py 1820 行，已在 VM 確認）。
登入：保留密碼（通道網址公開，必須認證），另加一次性登入連結：Notebook 第 4 格以密碼在 loopback 呼叫 POST /login-link，
取得 30 分鐘、單次有效的 token（記憶體內、最多 5 條未用，工作台重啟即全部失效）；GET /login?token= 兌換成同一個 session cookie。
第 2 格預設下載 Base 以外的全部模型（DOWNLOAD_FEATURE_MODELS 預設勾選，多 4.3 GB：dmd8、edit、color_depth LoRA 與 MoGe），
避免第一次用加速 8 步、修圖或控制就被「請先到模型頁下載」擋下；Base（10 GB）只在模型頁下載。使用者 2026-11-08 指定。
模型刪除：使用中主模型、共用編碼器／VAE、工作進行中、下載中一律 409；工作快照自帶 model_artifact_id，伺服器不強制等於使用中主模型。
批次 C 素材用 fast8 在同一工作階段生成再以 kind=input 上傳（無真人照片、無授權問題）；AC-09 柔邊外逐像素由腳本自動量測，其餘人工評分。

前端共用件集中在 static/widgets.js（狀態列、拖放／貼上、結果面板、接力、作品集）與 ui/workbench_parts.py（樣式與標記）；
studio.js 改用 api.js 的 request／pollJob，不再自帶一份。分頁版面一律「左輸入、右狀態＋結果」，窄螢幕上下堆疊。
「接著做」把作品當檔案走既有上傳路徑（kind=input），因為修圖／重繪／控制的參考圖只收 input；放大可直接選 output。
縮圖 GET /api/assets/{p}/{a}/thumbnail（384 px JPEG、記憶體快取）；專案改名 PATCH、刪除 DELETE /api/projects/{id}（移入 trash、有未完成工作時 409）。
工作回應多了 created_at；inpaint 的 JobRecord 多了 source_asset_id（比較原圖用）。

# VALIDATION
CPU：189 passed／7 skipped（3 載入探測、2 長 GPU、1 /proc、1 symlink）。node --check 全部前端模組。
假引擎瀏覽器（scripts/dev_server.py，非 GPU 證據）：五分頁主流程、fast8 負向詞攔截、修圖空格重編號、
重繪空遮罩攔截與原圖保留、控制兩子模式、模型表與分段放大、專案匯出→匯入→開啟。
GPU 證據：Stage 1；docs/evidence/stage2-batch-a（AC-04 通過 p50 111.5 s；AC-19 初評 7/10）；
docs/evidence/stage3-batch-b（AC-06 通過 10.4–10.5 s；auto 111.06 s vs lowvram 111.44 s）。舊 docs/evidence/stage2/ 為 GPT 未完成的 checkpoint。
Windows 間歇失敗的真因是讀檔與 os.replace 互斥（PermissionError）；atomic.py Windows 分支加短暫重試後連跑 6 次全過。
批次 C、D 腳本已在假引擎全段試跑（含中斷重跑取回原工作、AC-15 匯入比對與續編）；假引擎輸出不是 GPU 證據。

2026-11-11 假引擎瀏覽器（Playwright，1366 與 390 寬，非 GPU 證據）：生成→進度／剩餘時間→結果→接力到修圖→重繪→放大、
空提示詞與空遮罩攔截、重整後接回工作、取消、專案改名與刪除、作品集；無 console 錯誤。
tests/unit/test_ui_transport.py 會比對腳本用到的元素 id 是否都在標記裡。

# LANDMINES
不要把假引擎、CPU 測試或 docs/stages/stage3-8.md 的「程式完成」寫成 PASS。
瀏覽器工具的 type 動作不觸發 Gradio input 事件；測試草稿保存要用實際按鍵（key）。
Gradio 收合區塊與分頁延遲建立 DOM：新分頁用 tab.select 載入模組，專案選單用事件委派。
窄螢幕時 Gradio 把放不下的分頁收進 .overflow-dropdown（沒有 role=tab）；程式切分頁要兩處都找（widgets.js sendTo）。
自訂 HTML 內用 hidden 屬性的元素不要再給 inline display，否則 hidden 失效（舊版重繪分頁的破圖示就是這樣來的）。
Windows 預設 cp950：讀 JSON 設定一律 encoding="utf-8"。
runtime.lock.json 的 engine_vram_mode 已依批次 B 改為 auto（與 lowvram 差異在雜訊內）。
AC-19 未達 8/10：README 與文生圖分頁已標示繁中限制；失敗型態為近形字替換與框描述字詞滲入標題。
Colab 的 subprocess.run 輸出不會顯示在儲存格；看批次進度要用 Colab 終端機讀 benchmark.json／report.json。
批次 A、B 儲存格結尾會 files.download；第 7～9 格只打包不下載，下載前須取得使用者同意。
批次腳本把 payload 先存進 report.json 再送出：重跑必須沿用同一份（同 request id＋同 revision），改寫 payload 會被 409 擋下。
假引擎試跑模型區段要有大小相符的權重檔；可用 fsutil sparse 建稀疏佔位檔，用完要刪（.runtime/dev/models）。
用 Python write_text 改檔在 Windows 會寫成 CRLF；本倉庫多數檔案是 LF（少數 CRLF），提交前用 git ls-files --eol 檢查。
引擎輸入檔名必須以 moss_ 開頭（ComfyClient.upload_image 檢查）。
假引擎（AnyNodes）接受任何節點與輸入，抓不到真引擎的 object_info 驗證問題：開跑 GPU 批次前先在 VM 執行
scripts/engine_preflight.py（11 種圖、零上傳零排隊；它要求所有 LoRA 與 MoGe 都已下載，新 VM 上先下載再跑）。已踩過：LoadImage 的 image 列舉只含既有輸入檔（自家待上傳檔名需豁免）；
TextEncodeMOSSImageEdit.images 是 COMFY_AUTOGROW_V3，API 以 images.image_N 攤平送出。
Colab 終端機剛開時第一次輸入會混入 "1;2c0;276;0c" 之類回應碼，先打 clear 再下指令；點擊要落在終端機文字區內。
Colab：ROOT=/content/moss-stage1、資料 /content/moss-studio、證據 /content/moss-evidence；勿提交私有 URL／密碼／輸出。
上一輪（GPT）Colab 自動化曾遇瀏覽器審核額度限制，未繞過；重跑前先讀 benchmark.json，不重送。

# HISTORY
建立公開 GitHub 倉庫後開始 Stage 0；使用者授權用瀏覽器開 Colab 執行驗證（GPT 階段）。
2026-11-07：Claude Code 依審查改寫規格 v1.3.0，完成 Stage 2 收尾與 Stage 3～8 程式，推送 PR #1。
同日透過使用者 Chrome 在 Colab L4 跑 GPU 批次 A、B，證據下載後整理入 docs/evidence；執行階段已刪除。
PR #1 合併進 main（8a6f07f）。使用者接受 AC-19 限制並指示續做批次 C、D 腳本、程式缺口與 Stage 9～10。
2026-11-08：批次 C／D 腳本、模型刪除與主模型同步修正完成並通過假引擎試跑，推送分支 batch-cd-2026.11.07。
2026-11-08：GPU 批次 C 抓到兩個只在真引擎出現的驗證錯誤（LoadImage 列舉、autogrow），修正並加 engine_preflight；
評分後修正多圖參考圖尺寸與重繪預設強度並重測；批次 D 與 AC-15（新 VM）通過；新增一次性登入連結、比例預設、HF_TOKEN 選項。
2026-11-08：精簡批次 E 通過；同一台 VM 經 Cloudflare 通道實測 AC-03（登入連結、上傳、進度、取消、重連、下載、無 SSE）通過。
2026-11-08：Stage 10 文件完成，PR #2 合併進 main（8218cc3）；第 2 格改為預設下載 Base 以外的全部模型（PR #3）。
2026-11-08：使用者自行依 README 在乾淨 L4 重演（main b00af07），回報各項正常；Stage 10 完成。
2026-11-11：UI／UX 優化（狀態列與進度、拖放貼上、作品接力、作品集、專案改名刪除、重繪筆刷游標與比較、版面與手機寬度）；假引擎驗證。
