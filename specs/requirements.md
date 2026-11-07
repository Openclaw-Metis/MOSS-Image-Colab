# 規格整理 v1.3.0

## 版本變更摘要（v1.2.0 → v1.3.0）

文件日期 2026-11-07（臺灣時間）。v1.3.0 依據兩類新證據修訂：一是 v1.2.0 發布後的上游查證（官方 repo、ComfyUI 固定 commit 原始碼、權重清單、社群模型卡）；二是本專案 Stage 0～2 的實測紀錄（`docs/stages/`、`docs/compatibility.md`）。未實測的事項仍是待測假設，不因改版變成承諾。

| 編號 | 變更 | 理由與證據 |
|---|---|---|
| C1 | 視覺參考由「必要」降為「實驗能力」，不阻擋發布 | ComfyUI 官方文件寫明 MOSS-Image 本身沒有圖片輸入、不能複製參考圖 [R2]；原生做法是把圖縮到 384² 內送進文字編碼器 [R9]，主幹未針對此訓練 |
| C2 | 「原生 2K」改為「高解析」：原生上限 2.2 MP 為必要，2048² 以分段放大為正式路徑，原生 2048² 為實驗 | 官方建議 1～2 MP、外推上限 4 MP [R1]；ComfyUI 建議超過 2 MP 用多次放大重繪 [R2]；原討論本意是「放大」 |
| C3 | 刪除 FP8 文字編碼器 | 官方只提供 bf16、int8_convrot、w4a8_gptq 三種 [R8] |
| C4 | 8-step 改依當版作者 Space 設定：`lora_latest` 強度 0.7、8 步、CFG 1、無負向分支與 SLG | [R3][R11]；舊 fp32 與 data-space 取樣器段落已 deprecated |
| C5 | 排版接受官方 schema：`character` 標籤、選用 `palette`、`summary.meta/canvas` 選填 | 固定 commit 的 `MOSSImageLayoutPrompt` 會輸出這些欄位 [R9] |
| C6 | 繁中字形可行性提前到 Stage 2 的 GPU 批次（新增 AC-19） | 繁中海報是主要用途，官方範例只有簡體 [R1]；v1.2 排在 Stage 9 才驗 |
| C7 | 筆刷重繪改用自訂畫布，不用 `gr.ImageEditor` | Stage 1 驗證的傳輸是「Gradio 只做外殼、所有呼叫走同源 HTTP」；ImageEditor 的值要走 Gradio 後端 callback，Quick Tunnel 不支援 SSE [R5][E1] |
| C8 | 筆刷重繪加入 Edit-HQ 局部修改作為選用對照路線 | MOSS 沒有專用 inpaint 模型；Edit-HQ v4 起主打單圖局部修改 [R12][R14] |
| C9 | 新增使用限制：不得以真人照片做換臉、私密或冒名內容 | Colab 對所有執行環境禁止 creating deepfakes [R6] |
| C10 | 模型下載縮為：固定清單＋使用者指定的 HF repo／revision／檔名／SHA256 LoRA；Civitai 改為 P2 選用 | 降低 SSRF 與授權風險；單人工具不需通用下載器 |
| C11 | GPU 驗收批次化：階段分「程式完成（CPU DoD）」與「PASS（GPU 批次通過）」 | Stage 2 實測中 Colab VM 曾被回收、瀏覽器自動化遇到額度限制 [E2]；每階段各開一次 Colab 成本高且易中斷 |
| C12 | 引擎 VRAM 模式納入 Stage 3 量測 | 目前以 `--lowvram` 啟動，1024² 50 步實測約 113～128 秒 [E2]；官方最小記憶體模式 GPU 峰值 3.65 GiB [R7]，L4 可能不需 lowvram，需實測比較 |
| C13 | Codex／Claude Code 兩套重複指令合併為一套；移除每階段重複的 LLM Streaming 條文 | 降低維護成本；本版不含 LLM 文字輸出 |
| C14 | CPU 測試可在 Windows 維護機執行，Linux 行為不變 | 維護者主要平台為 Windows 11；`fcntl` 等僅限 POSIX |

## 技術規格文件

### 1. 文件目的、假設與前提

**專案名稱：MOSS-Image Colab Studio。產品路線：方案 A，Colab 上執行 ComfyUI 無頭引擎，以單一 Gradio 介面操作。** 本文件供開發、測試與維護使用。

目標使用者是單人創作者：製作繁體中文海報、參考圖修圖與局部修補，不操作節點圖。維護者需能替換固定版本的模型與工作流，並判斷功能是否真的通過驗收。

| 項目 | 規格假設與完成條件 |
|---|---|
| 目標環境 | Colab 付費方案、維持正的 compute unit 餘額；實測分配 NVIDIA L4，23,659,151,360 bytes VRAM、56,863,301,632 bytes RAM [E1]。啟動時讀實際值，不依方案名稱推定 |
| 已驗證基底 | Python 3.13.16、PyTorch 2.14.1+cu130、CUDA 13.0、ComfyUI 0.44.0（commit `1332fabf`）、Gradio 6.31.0 [E1] |
| 使用模式 | 單一擁有者、單 GPU、一次一個 GPU 工作；不做公開多人服務 |
| 核心交付 | 可從乾淨 Colab 啟動的 `.ipynb`、模組化 Python、依賴與模型鎖、API 格式工作流、測試、操作文件 |
| 核心體驗 | 五分頁：文生圖／拉框排版、多圖修圖、筆刷重繪、視覺與深度控制、模型與 LoRA 管理 |
| 模型策略 | bf16 SFT 主幹＋int8_convrot 文字編碼器＋`flux2-vae_small`；記憶體由 ComfyUI 管理，VRAM 模式依 Stage 3 實測決定 |
| 保存方式 | 預設寫入 Colab 本地；以專案 ZIP 匯出／匯入續編。Google Drive 為選用 |
| 連線要求 | `share=False`、ComfyUI 只綁 loopback、入口需本工具密碼登入；Quick Tunnel 只走同源 HTTP 輪詢 |
| 未定版本 | 不虛構 commit、套件版本或權重 SHA256；未鎖定者不得列為 released |

**完成判定分兩層：規格可供開發；產品全功能發布須通過本文件全部必要 GPU、傳輸與品質關卡。** 實驗能力（C1、原生 2048²）不阻擋發布，但介面須標示「實驗」。

### 2. 查證結論

外部事實摘要如下。標為「產品決策」或「門檻」的數值為本案設計，不是上游效能保證。

| 編號 | 已查證重點 | 規格處理 |
|---|---|---|
| S1 | 官方指南：中心原點、絕對像素、`yxyx` 排版；Euler、≥50 步、CFG 3（範圍 3～6）、shift 5；SLG 建議只跳第 22 層，22／24／26 各自有幫助 [R1] | 精細模式用單層 22；多層組合是另一次實驗 |
| S2 | 建議輸出 1～2 MP，可外推 0.25～4 MP；寬高為 16 的倍數 [R1]；超過 2 MP 建議分段放大重繪 [R2] | 見 C2 與 §7 |
| S3 | ComfyUI 原生支援 T2I、排版、Edit LoRA（最多四張參考、CFG 4、`edit_format=Moss-Image-Edit`）、色彩／深度控制；後兩者需 ComfyUI ≥0.43.0 [R2] | 固定 0.44.0；節點與參數以 [R9][R10] 為準 |
| S4 | `TextEncodeMOSSImageEdit`：接 VAE 時用參考 latent；不接 VAE 時把每張圖縮到 ≤384² 並加 `Picture N:` 標記送入視覺塔；`image_strength` 調整注意力 [R9] | 視覺參考走原生節點、不裝社群外掛；列為實驗 |
| S5 | 色彩／深度：`LoadMoGeModel`→`MoGeInference`→`MoGeRender`（`mask` 或 `depth`）→`MOSSImageControl`，並需控制 LoRA；`color_map` 為每區一色、須與輸出同尺寸 [R2][R9][R10] | 色塊圖由使用者繪製或上傳，不宣稱自動提取 |
| S6 | 8-step：作者 Space 以 bf16 主幹＋`lora_latest` 強度 0.7（建議 0.6～0.8）、release 排程器 shift 5、8 步、無 CFG [R3][R11] | fast8 profile 依此鎖定；不混用 deprecated 段落 |
| S7 | 權重檔：SFT／Base bf16 各 10,164,655,808 bytes；文字編碼器 bf16 19.31 GB、int8_convrot 9,748,121,532 bytes、w4a8 7.34 GB；`flux2-vae_small` 249,521,340 bytes；沒有 FP8 編碼器 [R8] | 見 C3、§6 |
| S8 | 官方 Gradio 有四種記憶體模式；minimal 模式 1024² 50 步 GPU 峰值 3.65 GiB、系統 RAM 14 GiB [R7] | L4 OOM 風險低；Stage 3 比較 VRAM 模式 |
| S9 | Quick Tunnel：持有網址者即可存取、無可用性保證、不支援 SSE；可用 `--allowed-mail` 加 Email OTP [R5] | 傳輸只走同源 HTTP；OTP 為選用附加層 |
| S10 | Colab：付費且餘額為正可用 Web UI；所有執行環境禁止 deepfakes、remote proxies 等 [R6] | 見 §17 使用限制 |
| S11 | 社群：Kromoss 為 Base 全量微調（主要修正模糊，diffusers 格式）[R13]；Edit-HQ 已到 v6，使用 `edit_format=ai-toolkit` [R12]；WanGP 已支援 MOSS Image／Edit [R14] | 皆為選用；不在必要範圍 |

原討論中的「100% 無損」「8-bit 與原版完全一致」「8 步固定 3～4 秒」「秒級切換」「零樣本複製構圖」「防審查／防風控」全部不成立或未證實，不寫成承諾。

### 3. 目標、範圍與優先級

唯一主任務是「把目前創作意圖與素材轉成一張可保存的圖片」。模型管理、安裝與診斷只為這項任務服務。

| Goal | Measures | Methods |
|---|---|---|
| 一般使用者可完成創作 | 依教學完成首次 1024² 圖與作品下載；不需編輯節點 | 一鍵啟動、預設檔、五分頁、單一生成按鈕 |
| L4 可完成必要功能 | 必要 AC 各有可追溯結果，必要案例不得 OOM | 單 GPU 排程、固定工作流、批次 GPU 驗收 |
| 工作可續編 | 專案匯出後在新 VM 匯入，輸入、排版、遮罩、設定一致 | 版本化專案格式、資產雜湊、原子寫入 |
| 功能宣稱有證據 | 每個 released 能力有版本、工作流 hash、GPU 報告 | 能力登錄與驗收矩陣 |

**必要範圍**：五分頁、SFT／Base、1～4 圖修圖、筆刷重繪、8／50 步預設、色彩／深度控制、高解析（原生 ≤2.2 MP＋分段放大）、模型下載與切換、專案匯出入、取消與失敗恢復。

**實驗範圍**（介面標示「實驗」，不阻擋發布）：視覺參考、原生 2048²、多層 SLG。

**選用範圍**（驗證後才加入能力清單）：Kromoss、Edit-HQ、使用者自加的 HF LoRA、Civitai（P2）、Drive、Quick Tunnel Email OTP。

不包含：訓練 LoRA、影片、多人帳號、付費後端、任意節點安裝器、規避服務商規範、保證「無審查」、保證人物／文字／姿勢完全正確、OpenPose 骨架控制、光學景深。

### 4. 能力登錄

| capability_id | 類別 | 驗收依賴 | 尚未證實 |
|---|---|---|---|
| t2i_layout | 必要 | T2I／排版工作流、排版編譯（含 character） | 繁中字形成功率（AC-19） |
| quality_50 | 必要 | 50 步 Euler／CFG 3／shift 5／SLG 22 | L4 實際耗時與 VRAM 模式 |
| fast_8 | 必要 | 固定 revision 的 DMD LoRA、8 步、CFG 1 | ComfyUI 路徑與作者 Space 的一致性、速度 |
| instruction_edit_4 | 必要 | Edit LoRA、1／2／4 圖、圖號對應 | 四圖峰值與複合指令效果 |
| masked_inpaint | 必要 | 遮罩、latent noise mask、柔邊合成 | MOSS 遮罩重繪接縫品質 |
| color_depth | 必要 | MoGe 3、控制 LoRA、`MOSSImageControl` | 幾何跟隨程度 |
| hires | 必要 | 原生 ≤2.2 MP、分段放大至 2048² | L4 峰值與放大細節 |
| model_manager | 必要 | 固定清單下載、雜湊、SFT↔Base 切換、HF LoRA 加入 | 外部 LoRA 品質與授權 |
| vision_reference | 實驗 | 原生無 VAE 的 `TextEncodeMOSSImageEdit` | 參考效果是否可感知 |
| native_2048 | 實驗 | 2048² 單次採樣 | 外推品質 |
| edit_hq | 選用 | 精確 repo／revision／license、`edit_format=ai-toolkit` | 與官方 Edit 的差異 |

每項狀態為 `unverified → probing → verified → released`，失敗為 `blocked`，回歸為 `disabled`。`verified` 表示 GPU 實驗通過；`released` 還需整合測試與文件。UI 依 `configs/capabilities.json` 控制選項與原因文字，不以「檔案存在」判定可用。

### 5. 架構與資料流

1. Notebook 偵測 GPU／RAM／磁碟，安裝固定依賴；下載最小模型集合並驗證 SHA256。
2. 啟動 ComfyUI（loopback）與本工具 app（loopback），通過健康檢查與 `/object_info` 節點查詢。
3. 啟動通道；使用者以單次密碼登入。
4. 使用者在分頁編輯草稿；前端透過同源 HTTP 保存草稿（revision CAS）。
5. 提交時建立不可變 JobSpec 快照；單 GPU 排程器編譯固定 API graph 並送入 ComfyUI。
6. 後端經 ComfyUI WebSocket 取得真實階段與步數，寫入 SQLite 事件；前端以 HTTP 輪詢讀取。
7. 成功後原子寫入圖檔與 JobRecord；使用者下載作品或匯出專案。

| 模組 | 路徑 | 責任 |
|---|---|---|
| Notebook bootstrap | `notebooks/`、`services/bootstrap.py`、`services/processes.py` | 安裝、校驗、啟停；只停止自己啟動且驗證所有權的程序 |
| Gradio 外殼與前端 | `ui/app.py`、`ui/static/*.js` | 五分頁版面；所有 callback 為 client-only（`fn=None`），不依賴 SSE |
| HTTP adapter | `adapters/http.py` | 登入、CSRF、Origin 檢查、同源 API、素材與作品下載 |
| Application service | `services/studio.py` | 驗證、工作提交、單 GPU 排程、取消、保存 |
| Workflow compiler | `adapters/workflow.py`、`workflows/` | JobSpec→固定 API graph；以 `/object_info` 驗證節點、必要輸入與 enum |
| Comfy client | `adapters/comfy.py`、`adapters/execution.py` | 提交、WebSocket 事件、history、定向取消、輸出讀取 |
| Storage | `storage/` | 原子 JSON、SQLite ledger、素材、專案 CRUD、匯出入 |
| Model registry／downloader | `configs/models.lock.json`、`services/downloads.py` | 固定來源、雜湊、授權、下載與相容資訊 |

傳輸決策（已實測）：Gradio 6.31.0 的 queue 依賴 SSE；Quick Tunnel 不支援 SSE [R5]。因此 Gradio 只負責畫面，所有生成、查詢、上傳與下載走需登入的同源 HTTP。callback 的 `backend_fn` 全為 false、`connect_heartbeat=false` [E1]。

### 6. 環境、安裝與模型配置

安裝器不執行 `pip install -U`；依 `configs/runtime.lock.json` 與 `configs/requirements-colab-py313.lock` 安裝。重跑 Notebook 不重複建立程序，不重下載已通過校驗的檔案。

| 模型角色 | 檔案（Comfy-Org/MOSS-Image 或另列） | 策略 |
|---|---|---|
| 預設主幹 | `moss_image_sft_bf16.safetensors` | 第一次下載 |
| 第二主幹 | `moss_image_base_bf16.safetensors` | 首次選用時下載；同時最多一個主幹在 GPU |
| 文字／視覺編碼器 | `qwen3.5_9b_int8_convrot.safetensors` | 預設；官方 T2I／Edit 範本用 w4a8，色彩／深度範本用 int8 [R2]，本案統一 int8 並記錄差異 |
| VAE | `flux2-vae_small.safetensors` | 預設 |
| Edit LoRA | `moss_image_edit_lora_rank_64_bf16.safetensors` | 進入修圖時下載 |
| 控制 LoRA | `moss_image_color_depth_control.safetensors` | 進入色彩／深度時下載 |
| 幾何估計 | `moge_3_vitg_fp16.safetensors`（Comfy-Org/MoGe） | 進入色彩／深度時下載 |
| 8-step LoRA | `lora_latest.safetensors`（lodestones/MOSS-Image-SFT-8-steps-dmd，revision `f95df83b5e90ae91ea412434b3f9b7f1c8c6314f`，1,189,176,800 bytes） | 進入 fast8 時下載；不追蹤 latest 名稱的後續變更 |

`models.lock.json` 每筆至少含 id、provider、repo、revision、filename、size_bytes、sha256、license_url、role、dtype、base_family、supported_tasks、tested_workflow_hash。缺任一欄位不得 released。

模型根目錄 `/content/models`；ComfyUI 以 `extra_model_paths.yaml` 讀取，不複製第二份。磁碟下載前要求「剩餘下載大小＋10 GiB 工作空間」。

**維護機**：CPU 測試須能在 Linux 與 Windows 執行。Windows 分支只用於本機測試（檔案鎖用 `msvcrt`、明確拒絕符號連結），不得改變 POSIX 行為；依賴 `/proc` 或符號連結權限的測試在 Windows 上 skip，且必須在 Linux／Colab 實跑。

### 7. 記憶體、高解析與效能

**記憶體交給 ComfyUI 管理，不另建資源管理器。** 本工具只負責：單 GPU 鎖、啟動前資源檢查（L4、可用 RAM ≥6 GiB、磁碟）、OOM 時清理本工作並以相同參數重試一次、引擎狀態不明時封鎖後續工作。

引擎 VRAM 模式（`--lowvram`／預設）為 `runtime.lock.json` 的設定值，Stage 3 以同一工作比較兩種模式的耗時與峰值，選較快且無 OOM 者為預設。現況 `--lowvram`：1024² 50 步約 113～128 秒 [E2]。

| 情境 | 必要調度 | 失敗處理 |
|---|---|---|
| 1024² 單圖 | 單 GPU 鎖 | OOM 清理後同參數重試一次 |
| 四參考圖 | 每圖等比縮至已驗證上限；保留圖號 | 提供減少參考或降低參考解析度；不自動刪圖 |
| 色彩／深度 | MoGe 前處理與採樣在同一 graph；ComfyUI 自行卸載 | 前處理失敗不提交空控制 |
| 高解析原生 | 總像素 ≤2,166,784（例：1456×1456、1472×1472） | OOM 則 blocked，不以插值冒充 |
| 分段放大 | 第一段 ≤2.2 MP → 像素空間放大（`ImageScale` 系列）→ `VAEEncode` → 重新採樣 denoise 預設 0.6；每段放大倍率 ≤1.5；最大 2048² | 每段獨立計時；最終輸出標示「分段放大」 |
| 原生 2048²（實驗） | 單次 2048² 採樣，可用 tiled VAE 解碼 | 失敗只影響實驗標記 |
| 主幹切換 | 等候任務結束再切換 | 失敗回到原可用模型 |

初始上限：batch=1；最多 4 參考；寬高為 16 的倍數、單邊 512～4096、總像素 ≤4,194,304。超出已測集合提示實驗性。

效能報告記錄硬體、driver、版本、模型 hash、種子、解析度、參考圖數、VRAM 模式與冷／熱啟動。每 profile 暖機 1 次、量測 5 次，報 p50、max、各階段時間與記憶體峰值。**本規格不承諾未量測的秒數。** 若 fast8 實測無明顯加速，不得命名「極速」。

### 8. 五分頁功能規格

#### 8.1 文生圖與排版

提供提示詞、預設檔（精細 50／加速 8）、尺寸、種子、產生按鈕與結果。負向詞與種子放進階區。種子空值表示自動產生，提交時固定寫入快照。

拉框器為自訂 SVG 畫布：新增、拖移、調整、刪除、復原；上限 32 框。**框種類 `text`／`object`／`character`**：text 必填顯示文字；object 與 character 不得帶 text。繪製順序即輸出順序（背景先、前景後）[R2]。

座標：contain 等比顯示，`(x,y)=((u-ox)/s,(v-oy)/s)`；儲存 normalized `[x0,y0,x1,y1]`；送出時四捨五入為整數像素並編譯為 `bbox=[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`。

匯入 JSON 接受官方格式：`summary.caption` 必填，`summary.meta`、`summary.canvas` 選填；items 可帶 `palette`（顏色字串陣列，最多 8 個）。非法 JSON 保留上一次有效畫布。排版模式不使用提示詞增強器。

#### 8.2 採樣預設

| 預設 | 模型／LoRA | 行為 | 相容規則 |
|---|---|---|---|
| quality50 | SFT（或 Base） | 50 步 Euler、simple、CFG 3、shift 5、SLG 單層 22 | 手動改值記為 custom |
| fast8 | SFT＋DMD LoRA（`lora_latest` 0.7） | 8 步 Euler、simple、CFG 1、shift 5；無負向分支、無 SLG | 只允許 SFT；不可疊加 Edit／風格 LoRA |
| edit | SFT＋Edit LoRA | CFG 4、`edit_format=Moss-Image-Edit`；步數由 edit profile 固定 | 不預設可與 DMD 疊加 |
| control | SFT＋控制 LoRA 1.0 | `MOSSImageControl` strength 1.0、end_percent 預設 0.6 | 不與 edit 同時使用 |

負向詞預設空白；使用者可填官方建議詞。不提供「NSFW 開關」，模型選擇與內容篩選分開；未安裝本機篩選器時不顯示假開關。

#### 8.3 多圖指令修圖

四個上傳格，各有預覽、圖號、替換與移除；第 1 張為主圖。提交需至少 1 張圖與非空指令；中間留空的格子須先確認重新編號，不能靜默改變「圖 2」的語意。

工作流：`LoraLoaderModelOnly`（Edit LoRA 1.0）＋兩個 `TextEncodeMOSSImageEdit`（正負向皆接 VAE、同一 `edit_format`、同一組圖片 `images.image_0..3`）。輸出尺寸預設跟隨主圖等比縮放至 ≤1 MP 並對齊 16。圖片經 `/upload/image` 以 UUID 檔名送入 ComfyUI，不使用原始檔名。

指令範例提示：「Change only the X to Y. Keep the character, face, hair, pose, background and composition unchanged.」[R2]。

#### 8.4 筆刷局部重繪

自訂畫布（HTML Canvas）：筆刷、橡皮擦、筆刷大小、復原、清除、反轉、遮罩預覽。白＝重繪、黑＝保留。遮罩以 PNG 素材保存（`kind=mask`），與來源圖共用同一座標與尺寸。

`edge_softness`（0～1，預設 0.15）為本產品參數，映射 `feather_radius_px=round(0.1*min(W,H)*edge_softness)`。工作流：`VAEEncode` 來源 → `SetLatentNoiseMask`（羽化後遮罩）→ 採樣（denoise 0.05～1.0，預設 0.65）→ `VAEDecode` → 以羽化遮罩與原圖合成；柔邊支撐區以外逐像素保留原圖。

空遮罩阻擋；全白遮罩須確認。輸出可並排原圖、遮罩、結果。Edit-HQ 局部修改為選用對照路線，通過 AC-09 對照後才可出現在選單。

#### 8.5 視覺與深度控制

- **色彩／深度（必要）**：來源圖經 MoGe 3 產生 `mask` 或 `depth`（使用者選），可預覽；也可上傳或手繪 depth map（白近黑遠）與 color map（每區一色、與輸出同尺寸）。提供 strength 與 end_percent。只有實際接入 graph 的圖標示「已套用」。
- **視覺參考（實驗）**：1～4 張圖送入原生 `TextEncodeMOSSImageEdit`（不接 VAE、不掛 Edit LoRA），提供 `image_strength`。介面註明「模型沒有正式圖片輸入，效果不保證」。

文案用「跟隨大致構圖／幾何」，不用「精準複製姿勢」。

#### 8.6 模型與 LoRA 管理

模型表顯示角色、大小、狀態（未下載／下載中／已校驗）、授權連結與相容任務。可下載固定清單項目、切換 SFT／Base（工作進行中不可切換）。

使用者自加 LoRA 只接受 Hugging Face 精確 `repo`＋`revision`（40 碼 commit）＋`filename`（`.safetensors`）；SHA256 與大小由 HF API 的 LFS 資訊取得並校驗。自加 LoRA 標示「未驗證」，只能在 quality50 套用並記錄於 JobRecord。token 來自 Colab Secrets，不進專案、網址、日誌或匯出。Civitai 為 P2 選用。

### 9. 任務模型與資訊揭露

| 層級 | 使用者任務 | 首屏支援 |
|---|---|---|
| 主目標 | 提交目前創作並看到結果 | 是，主 CTA 隨分頁命名「產生圖片／開始修圖／開始重繪」 |
| 次目標 | 編輯提示、素材、框、遮罩與重試 | 是，只顯示當前模式必要欄位 |
| 低頻 | 改模型、下載 LoRA、匯出專案 | 模型頁／專案選單 |
| 罕見 | 查錯、恢復、重建環境 | 出錯時展開 |

輸入為 must-see-now；下載為 next-step-only；錯誤為 error-only；JSON 與採樣進階為 on-demand-reference；歷史與診斷為 keep-off-first-viewport。

### 10. 狀態模型

UI 狀態：`empty → editing → validating → submitted → running → resolved`，例外 `blocked`、`reconnecting`。Job 狀態：`created → validating → queued → encoding → sampling → decoding → saving → succeeded`；未完成狀態可進 `cancelling → cancelled` 或 `failed`；引擎狀態不明為 `interrupted`，並封鎖後續 GPU 工作直到核對。禁止失敗狀態寫成 succeeded。

執行中仍可編輯下一份草稿，但不影響已提交快照。

### 11. UI 風格

淺色專業創作工具；主色 `#1D4ED8`、完成 `#0F766E`、底色 `#F8FAFC`、待確認 `#B45309`、錯誤 `#B91C1C`（搭配文字）。首屏最多三組：輸入／畫布、結果、窄狀態列；每分頁一個主 CTA。窄螢幕改上下堆疊。畫布與預覽保持比例。

### 12. 專案目錄

| 路徑 | 責任 |
|---|---|
| `notebooks/MOSS_Image_Colab.ipynb` | 啟動入口（產品 app，不是探測 app） |
| `src/moss_studio/domain/` | 契約、工作狀態、排版、遮罩、參考圖規則 |
| `src/moss_studio/storage/` | 原子 JSON、ledger、素材、專案、匯出入 |
| `src/moss_studio/services/` | studio、bootstrap、processes、downloads、resources、capabilities |
| `src/moss_studio/adapters/` | comfy、execution、workflow、http、transport |
| `src/moss_studio/ui/` | `app.py`、`static/*.js` |
| `workflows/` | 各任務 API graph 範本；`probes/` 為 Stage 1 探測 |
| `configs/` | 鎖定清單、能力、profiles |
| `scripts/` | 基準、開發伺服器、探測 |
| `tests/` | `unit/`、`integration/`、`gpu/`、`fixtures/` |
| `docs/` | 相容性、stage 證據、evidence |

### 13. 資料模型

| 實體 | 欄位 | 生命週期 |
|---|---|---|
| Project | schema_version、id、name、revision、時間、五分頁 drafts、asset_ids、job_ids、extensions | revision CAS；刪除移入 trash 可恢復 |
| Asset | id、project_id、kind（input／output／mask／control）、path、mime、寬高、bytes、sha256、transform、source_order | 上傳解碼、去除 metadata、以 UUID 命名 |
| Job | id、project_id、request_id、snapshot、snapshot_hash、status、comfy_prompt_id、時間；events | 快照不可變（SQLite trigger） |
| JobRecord | output_assets、workflow_hash、profile、seconds、seed、snapshot_hash | 成功後原子寫入 |
| ModelArtifact | lock 欄位＋下載狀態 | 權重變更建新 revision |

JobSpec v1 欄位：project_id、client_request_id、project_revision、task、profile_id、model_artifact_id、prompt、negative_prompt、width、height、seed、references、layout、mask_asset_id、control、lora_stack。task 為 `t2i／layout／instruction_edit／inpaint／vision／color_depth／upscale`。

### 14. 持久化與續編

草稿 500 ms debounce 保存；revision 不符回報 conflict，不覆蓋較新資料。本地保存可承受瀏覽器關閉，**不能承受 VM 回收**；持久續編靠下載專案 ZIP 或選用 Drive。

專案 ZIP 含 `project.json`、素材、遮罩、結果、JobRecord；不含權重、secret、session。匯入先檢查 manifest 與所有 hash，以新 project_id 寫入，不覆寫既有專案。限制：壓縮 ≤1 GiB、展開 ≤4 GiB、≤5000 entries、單檔 ≤256 MiB、壓縮比 ≤100；拒絕 `..`、絕對路徑、符號連結、重名。

### 15. 服務介面

同源 HTTP，全部需登入；變更請求需 CSRF header 與同源 Origin。

| 方法 | 路徑 | 語意 |
|---|---|---|
| GET | `/api/session`、`/api/runtime` | CSRF、能力、預設 profile；GPU／RAM／磁碟 |
| GET／POST | `/api/projects` | 列出／新建 |
| GET | `/api/projects/{id}` | 讀取 |
| PUT | `/api/projects/{id}/draft` | 保存草稿（需 tab 與 expected_revision） |
| POST | `/api/projects/{id}/assets` | 上傳圖片（raw bytes，≤20 MiB） |
| POST | `/api/layout/validate` | 驗證並回傳排版 |
| POST | `/api/jobs` | 提交 JobSpec |
| GET | `/api/jobs/{id}?after_seq=`、`/api/jobs/request/{project}/{request}` | 狀態與事件；以 request id 找回 |
| POST | `/api/jobs/{id}/cancel` | 取消 |
| GET | `/api/assets/{project}/{asset}`、`/api/works/{project}.zip` | 下載素材／作品 |
| GET／POST | `/api/models`、`/api/models/{id}/download`、`/api/models/activate` | Stage 7 |
| GET／POST | `/api/projects/{id}/export`、`/api/projects/import` | Stage 8 |

錯誤格式 `{code,message}`；400／422 輸入、401／403 認證與 CSRF、404 不存在、409 衝突或忙碌、413 過大、503 引擎。ComfyUI 端點只在後端使用：`/object_info`、`/prompt`、`/ws`、`/history/{id}`、`/queue`、`/upload/image`、`/view`、`/interrupt`。

### 16. 背景工作、取消與重試

排程上限 1 執行＋2 等候。以 project_id＋client_request_id 去重；相同 key 不同內容回報 conflict；前端重連不重送。取消：等候中直接移除；執行中以 prompt_id 定向 interrupt；引擎未確認結束時標 interrupted 並封鎖後續工作。推論 OOM 只同參數重試一次；其他錯誤需使用者重跑。下載網路錯誤最多 3 次退避，尊重 Retry-After；401／403／404／hash 錯誤不重試。

### 17. 連線、隱私、安全與使用限制

ComfyUI 綁 `127.0.0.1:8188`，app 綁 `127.0.0.1:7860`，只對通道公開 app。單次高熵密碼登入；驗證覆蓋頁面、API、素材與作品下載。

| 通道 | 定位 |
|---|---|
| Quick Tunnel＋同源輪詢 | 預設；已實測登入、上傳、生成、取消、重連、下載 [E1] |
| Quick Tunnel＋`--allowed-mail` | 選用附加層；Email 會交給 Cloudflare |
| Named Cloudflare Tunnel | 選用；需使用者帳號與網域 |
| Colab 受保護預覽 | 非預設；實測在第三方 Cookie 限制下空白 [E3] |

HTTPS 不代表運算或通道供應者看不到資料，也不保證內容無限制或帳號不受影響。

**使用限制**：不得以真人照片製作換臉、私密內容或冒用他人身分的圖片（Colab 對所有執行環境禁止 deepfakes [R6]）。修圖與控制分頁在上傳區顯示此提醒。工具不提供規避平台或模型授權限制的功能。

### 18. 上傳、下載與匯入防錯

圖片 ≤20 MiB／20 MP；PNG、JPEG、靜態 WebP；先解碼、處理 EXIF 方向、重建像素並移除 metadata；以 UUID 命名。模型下載只接受固定清單或 §8.6 的 HF 精確來源；寫入 staging、校驗大小／SHA256／safetensors 檔頭後原子搬移。token 不得跟隨跨站轉址或寫入日誌。

### 19. 錯誤與可觀測性

| code | 顯示 | 回復 |
|---|---|---|
| E_GPU_PROFILE | 實際環境不符已驗證設定 | 顯示偵測值 |
| E_CAPABILITY | 功能尚缺已驗證節點、權重或證據 | 指向模型頁與缺項，保留草稿 |
| E_TRANSPORT | 通道無法完成通訊 | 顯示測試結果 |
| E_OOM | 記憶體不足 | 清理後重試一次，再失敗提供降載選項 |
| E_MASK_EMPTY | 請先塗抹要修改的區域 | 回畫布 |
| E_MODEL_INCOMPATIBLE | 此組合未通過相容測試 | 顯示可用組合，不靜默忽略 |
| E_DOWNLOAD_AUTH／HASH | 需授權／檔案驗證失敗 | 不登錄 ready |
| E_CONFLICT | 專案已在另一頁面更新 | 重新載入或另存 |
| E_ENGINE／E_ENGINE_UNCERTAIN | 引擎中斷或狀態不明 | 查 history 後再提供重跑 |

日誌不記 token、cookie、原圖 bytes 或完整提示詞。

### 20. 非功能需求與驗收條件

可用性：一般創作不需接觸節點或命令。可靠性：重連依 ledger 對帳、原子保存、單 GPU 不競態。可維護性：UI、domain、adapter 分離；升級上游需重跑契約與 GPU 回歸。

**階段完成分兩層（C11）**：
- **程式完成**：該階段 CPU 測試、lint、本機假引擎 UI 檢查全數通過，GPU 測試已寫好但尚未在 L4 執行。可接著開發下一階段。
- **PASS**：該階段的 GPU 批次在 L4 實跑通過並取回證據。
- **發布**：所有必要 AC 為 PASS；實驗能力只需有證據紀錄。

| ID | 驗收情境 | 證據 | 類別 |
|---|---|---|---|
| AC-01 | 乾淨 L4 安裝、啟動；重跑不產生第二個引擎、不重下載已校驗檔 | Notebook 記錄、PID、hash | 必要 |
| AC-02 | 未登入的頁面、API、上傳、素材、作品下載均被拒；ComfyUI 無公開入口 | HTTP 測試 | 必要 |
| AC-03 | 通道完成上傳→生成→進度→取消→重連→下載；無 SSE 依賴 | 傳輸契約測試 | 必要 |
| AC-04 | 1024² SFT quality50 暖機 1 次＋5 次成功；無 NaN／OOM／黑圖 | benchmark JSON 與輸出 | 必要 |
| AC-05 | 正方／橫／直畫布 30 組座標誤差 ≤1px；官方 schema（character、palette）可匯入 | 單元測試 | 必要 |
| AC-06 | fast8 5 次成功，graph 確實含 DMD LoRA 0.7、CFG 1、無 SLG；與 50 步比較耗時與品質 | profile、workflow hash、benchmark | 必要 |
| AC-07 | quality50 graph 與 profile 一致；切回 fast8 無殘留參數 | graph 契約 | 必要 |
| AC-08 | 1／2／4 圖各 3 例；主圖比例、圖號、指令對應正確；四圖無 OOM | 素材與量表 | 必要 |
| AC-09 | 遮罩方向正確；柔邊外逐像素一致；空白與全白路徑正確；5 例品質 | 遮罩單測、差分圖 | 必要 |
| AC-10 | 視覺參考開／關與 image_strength 對照 5 例，記錄效果 | workflow trace | 實驗 |
| AC-11 | mask／depth 各有接入對照；5 例至少 4 例保留主要幾何 | 控制圖與輸出 | 必要 |
| AC-12 | 原生 ≤2.2 MP 連續 3 次；分段放大至 2048² 連續 3 次；記錄峰值與耗時 | GPU 報告 | 必要 |
| AC-13 | SFT↔Base 各 3 次；忙碌時不切換；失敗回復 | 切換紀錄 | 必要 |
| AC-14 | 不支援的 LoRA／profile 組合被攔截；刪除使用中檔案被阻擋 | 相容矩陣測試 | 必要 |
| AC-15 | 專案 ZIP 匯出後在新 VM 匯入，輸入、遮罩、排版、設定、作品 hash 一致 | round-trip 測試 | 必要 |
| AC-16 | 重複提交僅一工作；斷線不重跑；取消只影響自己；故障不誤報成功 | 故障注入 | 必要 |
| AC-17 | 網址／ZIP／圖檔異常、路徑穿越、大小限制、token 遮罩 | 邊界測試 | 必要 |
| AC-18 | 固定 5 個局部修補、5 個一般生成案例，各類 ≥80% 達品質標準 | 原圖、輸出、評分表 | 必要 |
| AC-19 | 固定 10 個繁中排版海報：標題逐字正確且位置合理的比例 | 原圖、輸出、OCR 輔助的人工評分 | 決策關卡 |
| AC-20 | 原生 2048² 3 次 | GPU 報告 | 實驗 |

品質量表：每案例預先標 3 項必要特徵，滿足至少 2 項且無黑圖或嚴重破圖才算成功。評分案例與標準在跑模型前固定。

**AC-19 決策關卡**：≥8/10 時繁中海報列為已驗證用途；低於 8/10 時產品仍可繼續，但 README 與文生圖分頁須明示繁中字形限制，並把結果交給使用者決定是否調整目標（例如改以英文標題或後製加字）。

### 21. 邊界與風險

| 邊界 | 行為 |
|---|---|
| 上傳解碼失敗 | 不替換既有素材 |
| 4K tokens 或多圖超長 | 以實際 tokenizer 驗證；不靜默截尾 |
| 多頁面同時編輯 | revision conflict，提供另存 |
| 下載 HTML 冒充權重 | 檔頭與 hash 失敗，不列 ready |
| VM 回收 | 只有匯出副本或 Drive 可恢復 |
| JSON 嵌入指令或路徑 | 只解析允許欄位，不執行或載入 graph |
| 引擎成功但保存失敗 | 標 failed，不顯示已保存 |
| 上游社群 LoRA 更新 | 以 revision 固定；升級需重跑對應 AC |

主要風險：繁中字形（AC-19）、L4 效能（VRAM 模式）、遮罩重繪接縫、Quick Tunnel 可用性、Colab 政策變動。

### 22. 來源

查閱日期 2026-11-07。

- [R1 OpenMOSS USERGUIDE](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md)
- [R2 ComfyUI MOSS-Image 文件](https://github.com/Comfy-Org/docs/blob/main/tutorials/image/moss-image/moss-image.mdx)
- [R3 lodestones 8-step 模型卡](https://huggingface.co/lodestones/MOSS-Image-SFT-8-steps-dmd)
- [R4 ThetaCursed 視覺節點](https://github.com/ThetaCursed/ComfyUI-MOSSImageTextEncoder)（本案不安裝，原生節點已涵蓋）
- [R5 Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [R6 Colab FAQ](https://research.google.com/colaboratory/faq.html)
- [R7 OpenMOSS 官方 repo README](https://github.com/OpenMOSS/MOSS-Image)
- [R8 Comfy-Org/MOSS-Image 權重](https://huggingface.co/Comfy-Org/MOSS-Image)
- [R9 ComfyUI nodes_moss_image.py @1332fab](https://github.com/Comfy-Org/ComfyUI/blob/1332fabfcc507aa7c548cd5152071ed494c207e8/comfy_extras/nodes_moss_image.py)
- [R10 ComfyUI nodes_moge.py @1332fab](https://github.com/Comfy-Org/ComfyUI/blob/1332fabfcc507aa7c548cd5152071ed494c207e8/comfy_extras/nodes_moge.py)
- [R11 8-step 示範 Space app.py](https://huggingface.co/spaces/hugging-apps/moss-image-8-step-dmd/blob/main/app.py)
- [R12 akhaliq/MOSS-Image-Edit-HQ](https://huggingface.co/akhaliq/MOSS-Image-Edit-HQ)
- [R13 lodestones/Kromoss](https://huggingface.co/lodestones/Kromoss)
- [R14 WanGP README](https://github.com/deepbeepmeep/WanGP)
- E1 `docs/stages/stage1.md`、E2 `docs/stages/stage2.md`、E3 `docs/compatibility.md`（本專案實測紀錄）

## 非技術規格文件

### 這個工具是給誰用的

給想在 Colab 製作圖片、海報或修圖的人。你在一個網頁選擇工作方式，不需要自己連接運算節點。前提是付費 Colab 並分配到 L4 顯示卡；工具會先檢查設備，符合才開放已驗證的功能。

### 你能完成哪些工作

| 頁面 | 你能做的事 |
|---|---|
| 文生圖與排版 | 描述想要的畫面，拉框安排標題、物件和人物位置，選擇精細或加速 |
| 多圖修圖 | 放入一到四張圖，說明每張用途，再描述要改的內容 |
| 筆刷重繪 | 塗抹要改的區域，確認遮罩後重新繪製 |
| 視覺與深度 | 依參考圖的輪廓或深度產生新內容；參考圖風格功能屬實驗 |
| 模型管理 | 下載已驗證的模型、切換主模型、加入指定的風格檔 |

### 你會怎麼使用它

開啟提供的 Colab 筆記本，依序執行儲存格，等待檢查、下載與載入完成。筆記本會顯示一個網址和一次性密碼，用密碼登入創作頁面。按「產生圖片」或「開始修圖」後，畫面顯示目前階段與步數；完成後下載作品。可以取消未完成的工作，原本輸入會保留。

### 保存與續編

工具會在目前 Colab 保留進度，但 Colab 結束或重建後本地內容會消失。想保留工作，請下載專案檔；下次開啟專案即可接著修改。

### 限制與注意事項

- 精細模式一張 1024 圖目前約需 2 分鐘；加速模式的實際速度要測試後才知道。
- 中文字、手指、人物身分、接縫和姿勢仍可能畫錯，需要你檢查。繁體中文標題的準確度會在早期測試後公布。
- 參考圖只能協助跟隨大致輪廓或深度，不保證完全一致。
- 不可用真人照片做換臉、私密或冒名內容；這也是 Colab 的使用規定。
- 登入保護與加密連線能降低未授權存取，但不代表服務供應者看不到資料。

## 分階段開發計畫

### 執行總則

每階段先讀 `DEVNOTE.md`、`todo.md`、本規格與 `AGENTS.md`。完成後留下檔案變更、實際命令、測試結果、未決風險與回滾點。不可把未跑的 GPU 測試寫成 PASS；CPU／mock 測試不代表 GPU、畫質或通道通過。

**階段推進規則（C11）**：前一階段「程式完成」即可開始下一階段開發；階段標 PASS 需其 GPU 批次通過。GPU 批次在同一個 Colab 工作階段集中執行，每完成一項就把報告與圖檔拉回 `docs/evidence/`，避免 VM 回收造成遺失。

**本機 UI 檢查**：`scripts/dev_server.py` 以假引擎啟動完整 HTTP＋Gradio app（產生佔位圖、模擬進度），用瀏覽器檢查 UI 流程。它只證明 UI 與 API 串接，不證明 GPU 或畫質。

| GPU 批次 | 涵蓋 | 內容 |
|---|---|---|
| A | Stage 2 | AC-04、排版結果下載、AC-19 繁中 10 例 |
| B | Stage 3、4 | VRAM 模式對照、AC-06、AC-07、AC-08 |
| C | Stage 5、6 | AC-09、AC-10（實驗）、AC-11 |
| D | Stage 7、8 | AC-12、AC-13、AC-14、AC-15、AC-20（實驗） |
| E | Stage 9 | AC-01～19 全面回歸、AC-18 |

### 狀態起點（v1.3.0 發布時）

| 階段 | 狀態 |
|---|---|
| Stage 0 | PASS（2026-11-07，CPU 範疇）；v1.3 新增 Windows 測試路徑 |
| Stage 1 | PASS（2026-11-07，真實 L4） |
| Stage 2 | 程式大致完成；GPU 批次 A 未完成 |
| Stage 3～10 | 未開始 |

### Stage 0：專案骨架與資料契約（PASS）

目標：可測的模組與資料契約。內容：domain 驗證、原子 JSON、revision CAS、SQLite ledger、schema v1。
**v1.3 差異**：CPU 測試可在 Windows 執行（`storage/atomic.py` Windows 分支；`/proc` 與符號連結測試在 Windows skip）。
DoD：Linux 與 Windows 的 CPU 測試、ruff 通過。回滾：回到 Initial commit。

### Stage 1：環境、權重與通道（PASS）

目標：固定版本、權重校驗、text／edit／vision 載入探測、認證通道端到端。已完成，證據見 E1。
**v1.3 差異**：無新增必要項目；FP8 不再列入測試矩陣。

### Stage 2：文生圖與排版垂直切片

目標：第一條可由正式 UI 完整產圖並保存的流程。

指令：
1. 排版：domain 與前端支援 `character` 標籤與 `palette`；`summary.meta／canvas` 選填；官方 JSON 可匯入。
2. Notebook 改為啟動正式 app（`moss_studio.ui.app`），保留 Stage 1 探測為獨立選用儲存格。
3. 新增 `scripts/dev_server.py` 假引擎開發伺服器；以瀏覽器檢查拉框、JSON、提交、進度、結果、下載。
4. 固定 AC-19 的 10 個繁中案例（`tests/fixtures/zh_tw_layouts.json`）與評分表，在跑模型前提交。

CPU DoD：單元與整合測試、ruff、假引擎 UI 流程通過。
GPU 批次 A：AC-04 五筆基準、排版結果保存與下載、AC-19。
回滾：自訂畫布出問題時，可暫以數值框編輯，但 AC-05 不通過。

### Stage 3：8／50 步預設與 VRAM 模式

目標：可重現切換採樣模式而不殘留設定；決定引擎 VRAM 模式。

指令：
1. `configs/profiles/fast8.json`：8 步、Euler、simple、CFG 1、shift 5、DMD LoRA 0.7、無 SLG；`models.lock.json` 加入 `lora_latest` 的固定 revision、大小、SHA256。
2. 編譯器依 profile 加入 `LoraLoaderModelOnly`；fast8 不送負向分支效果（CFG 1）、不加 SLG；只允許 SFT。
3. UI 預設檔切換（精細 50／加速 8）；session 回傳可用 profile 與能力狀態。
4. `runtime.lock.json` 新增 `engine_vram_mode`；bootstrap 依設定啟動。
5. 基準腳本支援 profile 與 VRAM 模式參數。

CPU DoD：graph 契約（AC-07）、profile 切換無殘留、相容規則攔截。
GPU 批次 B：兩種 VRAM 模式各跑 quality50 一次比較；AC-06。
回滾：fast8 不相容時標 blocked，保留 quality50。

### Stage 4：多圖指令修圖

目標：1～4 張參考圖、圖號與指令一致。

指令：
1. 上傳 API：`POST /api/projects/{id}/assets`（raw bytes），回傳素材 metadata；素材以 UUID 經 `/upload/image` 送入 ComfyUI。
2. 編譯器：Edit LoRA＋正負兩個 `TextEncodeMOSSImageEdit`（接 VAE、`Moss-Image-Edit`、`images.image_0..3`）、CFG 4；輸出尺寸跟隨主圖。
3. UI：四個上傳格、圖號、替換／移除、空槽重排確認、使用限制提醒。
4. 草稿依分頁保存（`drafts.edit`）。

CPU DoD：參考圖順序、空槽、尺寸計算、graph 契約、上傳邊界測試。
GPU 批次 B：AC-08。
回滾：停用修圖分頁不影響 T2I。

### Stage 5：筆刷局部重繪

目標：可檢查的遮罩、局部修改、柔邊外原圖保護。

指令：
1. 自訂 Canvas 筆刷：筆刷、橡皮擦、大小、復原、清除、反轉；遮罩上傳為 `kind=mask` 素材。
2. `domain/masks.py`：二值化、羽化（edge_softness 映射）、空／全白判斷、最終合成。
3. 編譯器：`VAEEncode`→`SetLatentNoiseMask`→採樣→`VAEDecode`；後端以羽化遮罩合成原圖。
4. 選用：Edit-HQ 局部修改對照工作流（未通過對照不出現在選單）。

CPU DoD：遮罩方向、羽化寬度、柔邊外逐像素一致、空／全白路徑。
GPU 批次 C：AC-09、AC-18 局部修補部分。
回滾：latent mask 不相容先阻擋重繪。

### Stage 6：色彩／深度控制與視覺參考（實驗）

目標：證明控制訊號真的生效。

指令：
1. 下載 MoGe 3 與控制 LoRA；編譯器：`LoadMoGeModel`→`MoGeInference`→`MoGeRender(mask|depth)`→`MOSSImageControl`（strength、end_percent）＋控制 LoRA。
2. 支援上傳／手繪 depth map 與 color map（尺寸須等於輸出）。
3. 視覺參考（實驗）：無 VAE 的 `TextEncodeMOSSImageEdit`＋`image_strength`。
4. UI：子模式切換、控制圖預覽、「已套用」標示、實驗標示。

CPU DoD：graph 契約、控制圖尺寸驗證、子模式互斥。
GPU 批次 C：AC-11、AC-10（實驗）。
回滾：控制失效時標 blocked。

### Stage 7：模型管理與高解析

目標：安全管理模型並完成高解析路徑。

指令：
1. 模型頁：固定清單狀態、下載、SFT↔Base 切換（工作中不可切換）、HF 精確來源的 LoRA 加入（自動取 LFS SHA256 與大小）。
2. 高解析：原生 ≤2.2 MP；`upscale` 工作（第一段→像素放大→VAEEncode→重新採樣，每段 ≤1.5 倍，最大 2048²）。
3. 原生 2048² 標示實驗。

CPU DoD：下載校驗、惡意來源拒絕、切換屏障、放大段數計算、graph 契約。
GPU 批次 D：AC-12、AC-13、AC-14、AC-20（實驗）。
回滾：切換失敗回到最後可用模型。

### Stage 8：專案匯出、匯入與工作恢復

目標：成果與創作狀態能在新 VM 復原。

指令：專案 ZIP 匯出（manifest＋hash）、匯入驗證（大小、路徑、壓縮比、重名）、以新 id 寫入；專案選單（新建、開啟、改名、匯出、匯入、刪除）。
CPU DoD：round-trip hash 一致、zip slip／bomb 拒絕。
GPU 批次 D：AC-15 新 VM 匯入後續編生成。

### Stage 9：整合與回歸

目標：全案放行證據。固定品質評測集後在乾淨 L4 跑 GPU 批次 E（AC-01～19）。不新增功能、不降門檻。任何未跑或失敗都標 FAIL／BLOCKED。

### Stage 10：文件與交付

README、操作說明、疑難排解、相容性、隱私與使用限制；依 README 在乾淨 L4 重演一次完整流程。Stage 9 未全過時只交付標明未完成的開發包。
