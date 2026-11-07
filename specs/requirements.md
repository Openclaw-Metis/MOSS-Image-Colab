# 規格整理 v 1.2.0

## 技術規格文件

### 1. 文件目的、假設與前提

**專案名稱：MOSS-Image Colab Studio。產品路線：方案 A——Colab 上執行 ComfyUI 無頭引擎，以單一 Gradio 介面操作。** 本文件供開發、測試及後續維護使用；文件日期為 2026-11-07（臺灣時間）。本次交付規格，未宣稱完成程式、GPU 測試或部署。

目標使用者為 Oberon 等單人創作者：希望製作繁體中文海報、參考圖修圖與局部修補，但不希望操作節點圖。維護者需能替換固定版本的模型與工作流，並判斷功能是否真的通過驗收。

| 項目 | 規格假設與完成條件 |
|---|---|
| 目標環境 | Colab 付費使用者，分配到 NVIDIA L4、約 24 GB VRAM 與約 53 GB 系統 RAM；啟動時讀取實際值，不依訂閱名稱推定 |
| 使用模式 | 單一擁有者、單 GPU、一次僅一個 GPU 任務；不做公開多人服務 |
| 核心交付 | 可從乾淨 Colab 啟動的 `.ipynb`、模組化 Python 程式、依賴及模型清單、API 格式工作流、測試與操作文件 |
| 核心體驗 | 五分頁；文生圖／拉框排版、多圖修圖、筆刷重繪、視覺參考／深度控制、模型與 LoRA 管理 |
| 模型優先策略 | bf16 SFT 主幹＋已驗證的 8-bit 編碼器＋相容 FLUX.2 VAE，元件依階段交換；不預設同時全部常駐 GPU |
| 保存方式 | 預設寫入 Colab 本地；以專案 ZIP 匯出／匯入續編。Google Drive 為選用且需使用者自行啟用 |
| 連線要求 | `share=False`、ComfyUI 僅 loopback；對外入口需認證。Cloudflare 通道模式須先通過傳輸驗證 |
| 未定版本 | 本文不虛構已驗證的 commit、套件版本或權重 SHA256；Stage 1 以實驗填妥鎖定清單，未填妥不得進入發布 |

**完成判定分兩層：規格可供開發；產品全功能發布必須通過本文件全部必要 GPU、傳輸與品質關卡。** 將選項灰階顯示只能作為開發期間狀態，不能據此宣稱已完成原要求的全功能版本。

### 2. 查證結論與原討論修正

以下為外部事實摘要，其餘數值若標為「產品決策」或「門檻」，均為本案設計，並非上游效能保證。

| 編號 | 已查證重點 | 規格處理 |
|---|---|---|
| S1 | 官方指南給出中心原點、絕對像素、`yxyx` 排版格式；建議 Euler、50 步以上，Base CFG 預設 3，SLG 建議 skip layer 22 [R1] | 寫成獨立排版編譯器；精細模式先使用單層 22，不直接同時跳 22／24／26 |
| S2 | ComfyUI 文件列出原生 T2I／排版、Edit LoRA 最多四參考與色彩／深度工作流；後兩者要求 0.43.0 以上 [R2] | 優先原生節點；仍以固定 commit 與實際節點結構為準 |
| S3 | 作者目前 8-step 卡片提供 LoRA 使用方式，舊 fp32／data-space 說明已標 deprecated [R3] | 各版本 sampler、CFG、精度及強度獨立鎖定；禁止混用舊教程 |
| S4 | 社群視覺節點把圖片送入 Qwen 視覺塔，定位為條件控制而非修圖 [R4] | 與 Edit 分開；不承諾精準複製構圖或零額外記憶體 |
| S5 | Quick Tunnel 預設網址可被持有網址者存取、無可用性保證且不支援 SSE [R5] | 通道與 Gradio 事件相容性為 P0 gate；隨機網址不能替代認證 |
| S6 | Colab 資源不保證；付費且維持正的 compute unit balance 涉及網頁介面使用條件 [R6] | 啟動前提示使用者確認方案與餘額；不宣稱 Pro 固定分配 L4／RAM／磁碟 |

原討論的「100% 畫質無損」「8-bit 與原版完全一致」「8 步固定 3～4 秒」「下載固定兩分鐘」「秒級切換」「A100 等級流暢」「無縫重繪保證」全部改為待測假設，不寫成承諾。bf16 也是低精度浮點，本文稱「bf16 主幹」，不用「全精度」表示。

權重檔案大小之和不能代表 GPU 峰值；須加上運算暫存、注意力中間值、視覺輸入、LoRA、解碼及配置器保留空間。FP8 文字可載入也不表示視覺分支相容，需分開測試。

研究用量：4 個搜尋 query、6 個頁面開啟（包含 1 次 Gradio 官方頁開啟失敗）；同頁定位不另算新來源。已達本次研究預算，不再補廣泛搜尋。缺口：Gradio ImageEditor／事件機制的固定版本介面、下載平台細節、Kromoss／Edit-HQ 特定版本，以及實際 L4 效能。這些在 Stage 1 或對應階段核對原始碼及實測；不得假裝已驗證。

### 3. 目標、範圍、G3M 與優先級

唯一 primary task 是「把目前創作意圖與素材轉成一張可保存的圖片」。模型管理、安裝與診斷只為這項任務服務。以下 G3M 採本文件定義：Goal、Measures、Methods，不作其他縮寫解讀。

| Goal | Measures | Methods |
|---|---|---|
| 一般使用者可完成創作 | 依教學完成首次 1024 圖與作品匯出；不需編輯節點 | 一鍵啟動、預設檔、五分頁、單一生成按鈕 |
| L4 可完成全功能工作 | AC-01～AC-18 各自有可追溯結果，必要案例不得 OOM | 單 GPU 排程、元件卸載、逐功能固定工作流 |
| 工作可續編 | 專案匯出／新執行階段匯入後，輸入、排版、遮罩與設定一致 | 版本化專案格式、資產雜湊、原子寫入 |
| 功能宣稱有證據 | 每個 released capability 有版本、工作流、GPU 報告 | 能力登錄與驗收矩陣 |

**必要範圍**：五分頁、SFT／Base、四圖修圖、筆刷重繪、8／50 步預設、視覺塔、色彩／深度、2K 模式、下載器、專案匯出入、取消與失敗恢復。**選用範圍**：Kromoss、Edit-HQ 特定版、任意社群風格 LoRA、Drive、提示詞增強器；只有驗證後可加入能力清單。

不包含訓練 LoRA、影片、多人帳號、付費後端、永久 GPU 主機、任意節點安裝器、規避服務商規範、保證內容「無審查」、保證人物／文字／姿勢完全正確。骨架 OpenPose 與光學景深是不同功能，若另增需變更規格。

### 4. 能力登錄與可行性關卡

| capability_id | 納入方式 | 全功能驗收依賴 | 尚未證實的部分 |
|---|---|---|---|
| t2i_layout | 必要，原生 SFT／Base | T2I 工作流、排版編譯 | 繁中文字形成功率 |
| quality_50 | 必要，獨立預設 | 50 步 Euler／CFG／SLG | 參數與 L4 實際效果 |
| fast_8 | 必要，固定社群版本 | 官方作者當版採樣設定、相容 LoRA | 速度與精度路徑 |
| instruction_edit_4 | 必要，原生 Edit | 1／2／4 圖及順序對應 | 四圖時峰值資源與複合指令效果 |
| masked_inpaint | 必要，遮罩工作流及最終合成 | 像素／latent 對齊、接縫評測 | MOSS 遮罩重繪效果，不視為原生專用 inpaint 模型 |
| vision_reference | 必要，原生可行則優先，否則固定外掛 | 視覺編碼器驗證 | 不同精度與參考強度 |
| color_depth | 必要，原生範本 | 控制 LoRA、幾何估計器、控制圖預覽 | 幾何相似度，不能等同骨架精準鎖定 |
| model_manager | 必要，原子下載與交易式切換 | 雜湊、相容矩陣、無任務切換 | 外部 LoRA 品質、授權 |
| native_2k | 必要，高記憶體設定 | 2048×2048 單圖實測 | L4 峰值；失敗不能以插值冒充通過 |
| community_hq | 選用 | 精確 repo／revision／license／測試 | 不以名稱猜測 Edit-HQ v3／v4 相容 |

每項狀態為 `unverified → probing → verified → released`，失敗為 `blocked`，回歸為 `disabled`。`verified` 表示本地實驗通過；`released` 還需整合測試及文件。Gradio 讀此登錄控制選項與原因文字，不以「檔案存在」判定功能可用。

### 5. 核心流程與前後端模組

1. Notebook 偵測環境、磁碟與 GPU，核對固定依賴；下載最小模型集合並驗證雜湊。
2. 啟動 ComfyUI，等健康檢查及節點查詢通過；建立通道能力測試，然後顯示已認證的 Gradio 入口。
3. 使用者選分頁、上傳／預覽素材、設定創作內容。驗證器產生不可變 JobSpec 快照。
4. 排程器取得 GPU 鎖，工作流編譯器只替換白名單節點參數；素材傳給 ComfyUI，建立工作。
5. 編碼／採樣／解碼按資源策略分段執行，回報階段、步數及可用預覽。
6. 成功後原子寫入圖檔與 JobRecord，再更新結果區；失敗保留輸入，提供具體恢復方法。
7. 使用者下載作品或匯出可續編專案；關機停止通道及自己啟動的程序。

| 模組 | 責任與穩定邊界 |
|---|---|
| Notebook bootstrap | 安裝、環境診斷、啟停；不含主要 UI 或工作流邏輯 |
| Gradio UI | 五分頁、ImageEditor、Canvas 拉框、預覽與操作；不直接接觸任意伺服器檔案 |
| Application service | 驗證請求、project/job/model 操作、session 所有權 |
| Job scheduler | 單 GPU 鎖、去重、取消、租約、進度與恢復 |
| Workflow adapter | 將 JobSpec 編譯成固定 API graph；驗證 ComfyUI `/object_info` 相容性 |
| Comfy client | 提交、事件訂閱、狀態查詢、資產上傳、輸出讀取、interrupt 的版本適配 |
| Resource manager | 階段卸載、可用記憶體檢查、模型切換；不繞過 ComfyUI 管理器額外保留模型引用 |
| Asset/project store | 原子 JSON、SQLite job ledger、資產檔案、ZIP 匯出入及版本遷移 |
| Model registry/downloader | 固定來源、雜湊、授權、下載、相容矩陣與移除 |
| Transport adapter | loopback、tunnel、認證、傳輸能力測試；不公開 ComfyUI |

#### 模組架構圖（SVG）

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 520" role="img" aria-label="方案 A 模組與資料流">
 <rect width="1000" height="520" fill="#f8fafc"/>
 <g font-family="sans-serif" fill="#0f172a" font-size="18">
  <rect x="30" y="30" width="940" height="75" rx="10" fill="#dbeafe"/><text x="55" y="75">使用者瀏覽器：五分頁 Gradio、排版畫布、筆刷與作品預覽</text>
  <text x="480" y="133">↓ 認證入口</text>
  <rect x="30" y="150" width="940" height="70" rx="10" fill="#ccfbf1"/><text x="55" y="193">通道適配器 → Gradio 應用服務 → 驗證與單 GPU 排程器</text>
  <text x="235" y="252">↓ 工作快照</text><text x="730" y="252">↓ 保存／恢復</text>
  <rect x="30" y="270" width="560" height="75" rx="10" fill="#dbeafe"/><text x="55" y="315">工作流編譯器與 ComfyUI 本機用戶端</text>
  <rect x="630" y="270" width="340" height="200" rx="10" fill="#e2e8f0"/><text x="655" y="315">專案／素材／工作紀錄</text><text x="655" y="355">模型清單與已驗證權重</text><text x="655" y="395">匯入／匯出與診斷</text>
  <text x="245" y="378">↓ 本機連線</text>
  <rect x="30" y="395" width="560" height="75" rx="10" fill="#ccfbf1"/><text x="55" y="438">ComfyUI：編碼 → L4 採樣 → VAE 解碼</text>
 </g>
</svg>
```

### 6. 環境、安裝與模型配置

安裝器不執行滾動式 `pip install -U`。應提供依 Python／CUDA／PyTorch 相容組合選用的 lock 檔；重跑 Notebook 不重複建立程序，不重下載已通過校驗的檔案。不得為騰空間移除非本工具資料。

| 模型角色 | 初始候選 | 載入／下載策略 |
|---|---|---|
| 預設主幹 | `moss_image_sft_bf16.safetensors` [R2] | 第一次下載；實際 revision、SHA256 與 size_bytes 由 Stage 1 記錄 |
| 第二主幹 | `moss_image_base_bf16.safetensors` [R2] | 使用者首次選取才下載；同時最多一個主幹在 GPU |
| 文字／視覺編碼器 | `qwen3.5_9b_int8_convrot.safetensors` [R2] | 作為 8-bit 候選，逐一驗證 text／edit／vision；FP8 只作通過測試後的替代 |
| VAE | `flux2-vae_small.safetensors` [R2] | 記錄 loader 相容性與實際大小，不沿用草稿 0.34 GB 常數 |
| Edit | `moss_image_edit_lora_rank_64_bf16.safetensors` [R2] | 進入修圖功能才下載 |
| Color/depth | `moss_image_color_depth_control.safetensors`、`moge_3_vitg_fp16.safetensors` [R2] | 前處理完成卸載幾何估計器，再進行生成 |
| 8-step | lodestones 模型卡之固定 revision [R3] | 保存當版推薦強度、採樣與相依檔案；不追蹤 latest 名稱自動變更 |

`models.lock.json` 每筆至少含 id、provider、repo、revision、filename、size_bytes、sha256、license_url、role、dtype、base_family、supported_tasks、tested_workflow_hash。缺任一安全下載或相容性欄位時，不列為 released。

預設模型根目錄 `/content/models`；ComfyUI 透過固定的額外模型路徑設定讀取，不複製第二份。專案根目錄 `/content/moss-studio`。磁碟下載前要求「所選檔案總剩餘大小＋解壓需求＋10 GiB 工作空間」；RAM／VRAM 使用 GiB 顯示，檔案 byte 亦保留，避免 GB／GiB 混用。

### 7. 記憶體、2K 與效能策略

**產品預設為分段卸載，不以權重相加猜測可全部常駐。** 先完成所有文字／視覺條件，釋放編碼器 GPU 佔用；採樣後按需要卸載 DiT，再解碼。只在基準通過後允許「常駐加速」設定，且切換不改變輸入或採樣參數。

| 情境 | 必要調度 | 失敗處理 |
|---|---|---|
| 1024、單圖 | 單 GPU 鎖，編碼後卸載；可依已測 profile 加速 | OOM 清理本工作引用後，同參數保守卸載重試一次 |
| 四參考圖 | 每圖等比縮至已驗證上限；保留圖號；編碼峰值另測 | 提供減少參考圖／降低參考解析度選項；不自動刪圖 |
| 深度控制 | 幾何估計與採樣分時，控制圖轉 CPU | 前處理失敗不提交空控制工作 |
| 2048×2048 | 使用已驗證的保守 profile，可採 tiled VAE | 採樣仍 OOM 則標 blocked；可另提供分段放大方案，必須標為替代路徑 |
| 主幹切換 | 等候任務結束，GPU 卸載舊模型，載入新模型 | 留下原設定；候選載入失敗回復舊可用模型或未載入安全狀態 |

初始產品上限：batch size=1；最多 4 參考；輸出寬高正整數且均為 16 的倍數；最小 512 邊，總像素最多 4,194,304，單邊最多 4096。大長寬比超出已測集合時提示實驗性，不宣稱模型原生保證。1024² 預設；2K 明確指 2048²，不能與 2MP 混用。

RAM 維持至少 6 GiB 可用空間作為初始保護門檻，GPU 開始階段預估保留至少 2 GiB 裕度；這些是可調產品政策，最終以測得峰值及系統訊號決定。不得同時在 RAM 保留 SFT、Base、bf16 編碼器與重複載入副本而宣稱安全。RAM 快取使用 LRU 並設定預算；沒有餘裕即逐出，切換速度據實顯示。

效能報告固定記錄硬體、driver、版本、模型 hash、種子、解析度、參考圖數與冷／熱啟動。每 profile 先暖機 1 次，再測 5 次，報 p50、max、VRAM allocated／reserved 峰值、程序 RSS 與最低 available RAM；同時標示下載、編碼、採樣、解碼、全程時間。**本規格不承諾尚未量測的秒數。** 8-step 若實測無加速，仍保留獨立模式但不得命名「極速」，並須說明瓶頸。

### 8. 五分頁功能規格

#### 8.1 文生圖與排版工作台

提供正向提示詞、預設檔、尺寸／比例、種子、產生按鈕及結果。負向詞、CFG、SLG、sampler 放進階區。種子空值表示建立新 seed，提交時轉為實際整數並固定寫入工作快照；重試沿用原 seed。

拉框器以 Gradio 自訂元件承載 HTML Canvas／SVG 互動，不能假設 `gr.ImageEditor` 具有物件框選資料。每框有穩定 id、`label=text|object`、caption、文字內容與 normalized bbox；可新增、拖移、調整、刪除、選取及還原上一步。上限 32 框；文字框必填 text，物件框不得附帶 text。重疊允許但提示，不自動拆框。

畫布使用 contain 等比顯示。設可視區左上偏移 `(ox,oy)`、比例 `s=min(Vw/W,Vh/H)`，畫面指標 `(u,v)` 對應原圖 `(x,y)=((u-ox)/s,(v-oy)/s)`，先 clamp 到畫布。儲存 normalized `[x0/W,y0/H,x1/W,y1/H]`；送出時先四捨五入成整數像素，再編譯：

`bbox=[y0-H/2, x0-W/2, y1-H/2, x1-W/2]`。

拒絕零面積、NaN、無限、越界與反向框；左上／右下排序由拖曳處理，匯入 JSON 則明確報錯。尺寸改變依 normalized 座標重算，誤差最多 1 原圖像素。正方形與非正方形都測試，不用單一 1024 常數。

```json
{
  "summary": {"meta": ["poster"], "canvas": "single", "caption": "米白色山景旅遊海報"},
  "items": [
    {"label": "text", "caption": "上方深藍標題", "text": "山間慢旅", "bbox": [-416, -384, -288, 384]},
    {"label": "object", "caption": "下半部山景插畫", "bbox": [-160, -400, 400, 400]}
  ],
  "bbox_coord_space": "abs_centralized",
  "bbox_format": "yxyx"
}
```

JSON 與畫框雙向同步；非法 JSON 保留上一次有效畫布，不提交半成品。保留 last_valid_json，採 `editor_revision` 防止兩種編輯覆寫。排版模式預設停用提示詞增強器，避免結構被改寫。進階文字增強器為選用；若加入 LLM 文字輸出，必須 Streaming，並顯示實際送入生成的最終文字。沒有啟用文字生成時不虛構 LLM 串流。

#### 8.2 採樣預設與內容選項

| 預設 | 模型／LoRA | 預設行為 | 相容規則 |
|---|---|---|---|
| 精細 50 | SFT 或 Base；預設 SFT | 50 步、Euler、CFG 初始 3.0、shift 5；SLG profile 初始單層 22 | scheduler 及 SLG 起訖由固定工作流鎖定並量測；手動改值記為 custom |
| 加速 8 | 已驗證 SFT＋固定 DMD LoRA | 8 步；其餘值完全採當版作者及實驗結果 | 不套用 50-step CFG、負向分支或 SLG；若當版不支援則 UI 隱藏並解釋 |
| 指令修圖 | SFT＋Edit LoRA | 初始 CFG 4.0；採樣步數由 edit profile 固定 | 不預設可與 DMD／任意風格 LoRA 疊加 |
| 自訂 | 已驗證能力矩陣 | 允許修改已公開參數 | 不相容組合在提交前攔截 |

SLG 的 22／24／26 為候選替代層；多層組合是另一次實驗。不能以「開啟 SLG」保證手部與多人互動正確。負向詞可由使用者編輯，不與 Base／SFT 選擇綁定。

原討論的「NSFW 無審查切換」落實為：**模型選擇與本機選用內容篩選分開**。只有確實安裝可選本機後處理篩選器時才提供啟停；未安裝則顯示「未設定本機內容篩選」，不放假開關。不得因選 Base 自動宣稱可生成某類內容、關閉平台限制或取得隱私保證；工具仍受實際執行平台及模型授權約束。Kromoss 僅作可新增的模型紀錄，不當成已驗證內建。

#### 8.3 多圖指令修圖室

提供 4 個上傳格，各有預覽、圖號、角色說明、替換與移除；第 1 張為主圖。提交時至少 1 張有效圖片和非空指令；中間留空的格子應先提示重新編號，需使用者確認顯示的新圖號後才可提交，不能靜默改變「圖 2」語意。

工作流採固定版本 Edit 範本，正負編碼節點的 `edit_format` 等設定必須一致。輸出比例預設跟隨主圖，其他參考只作條件，不拼接成一張。明確送出有序 references 陣列，測試「圖 1 保留人物、圖 2 提供服裝」與交換順序的行為。重用參考素材以 asset_id，不靠上傳檔名辨識。Edit-HQ 只有通過自身相容矩陣才列選項。

#### 8.4 筆刷局部重繪

使用 `gr.ImageEditor`，由固定版本元件實際提供的 background／layers／composite 結構建立 adapter。遮罩取筆刷圖層 alpha；不可用 composite RGB 猜遮罩，黑筆、白筆均可代表選區。白=重繪、黑=保留，可反轉、清除、還原並預覽黑白遮罩。

來源依 EXIF 校正後定為工作座標；遮罩與來源共用同一等比縮放／letterbox 變換，分開記錄原始及推論尺寸。影像用高品質等比縮放，binary mask 用 nearest；羽化在推論尺寸上處理，再編碼到 latent 尺寸。`Set Latent Noise Mask` 僅為候選連接點，需驗證 MOSS latent 與固定工作流相容。

將草稿 0.15 定義為本產品的 `edge_softness`（0～1，預設 0.15），**不是 Gradio 或 ComfyUI 的既定 Hardness 參數**。本案映射為 `feather_radius_px=round(0.1*min(W,H)*edge_softness)`，即 1024 正方形約 15px；使用距離轉換建立有限寬度柔邊，UI 同時顯示 px。未選區不做羽化。

採樣 denoise 0.05～1.0，預設 0.65；1.0 僅表示全幅度修改選區，不保證自然接縫。最終依有限柔邊 alpha 與原圖合成，在柔邊支撐區域以外逐像素保留原圖。空遮罩阻擋；全白提示整張重繪並要求確認。輸出可並排原圖、遮罩與結果；自然接縫仍需品質案例驗收。

#### 8.5 視覺參考與色彩／深度控制

分成兩個子模式，避免同時把所有控制堆疊：

- **視覺參考**：先支援 1 張，通過後才開放更多；圖片送入已驗證的視覺編碼路徑。提供參考強度、每圖像素上限及預覽；初始候選 `image_weight=1.0`、`vision_megapixels=1.0` [R4]。不同精度分別驗證，沒有相容權重時停用此功能並指出缺項，不能退成純文字後仍稱視覺成功。
- **色彩／深度**：來源圖先產生可預覽的 depth／silhouette／color map；只有工作流實際使用的圖才標示「已套用」。提供自動估計與上傳控制圖替換、控制強度及結束比例；尺寸變換記錄。幾何估計器卸載後才開始採樣。

文案用「跟隨大致構圖／幾何」，不用「精準複製姿勢」。深度以白近黑遠為本工具標準，匯入需確認方向。色塊圖預設不自動宣稱已提取：須有可重現分群前處理並驗證，否則要求使用者上傳或繪製。控制 adapter 關閉對照組用於確定控制真的生效。獨立 OpenPose 與鏡頭景深控制不在本版。

#### 8.6 模型與 LoRA 管理

下載來源只接受 Hugging Face 的可解析資源與 Civitai 的精確 model version／檔案；網頁網址先解析，不當成 safetensors 直接儲存。token 來自 Colab Secrets 或本次記憶體輸入，不進專案、網址、日誌或匯出。遇到登入／授權頁先顯示原因，不反覆抓 HTML。

下載為 `pending → downloading → verifying → ready`；失敗為 failed，可續傳但須檢查 revision／ETag。寫 `.part`，驗證 byte、檔頭、SHA256、metadata 後 atomic rename。`aria2c` 為可選加速，使用參數陣列呼叫；設定相同站點連線上限，403／429 採有限退避，最多 3 次。網速只顯示實測。

只接受 safetensors；不從 UI 執行 pickle／Python／外部安裝腳本。每個 LoRA 記錄適用主幹、任務、精度與允許疊加組合。使用者可新增、改名稱／強度、卸載、刪除；已被執行中工作引用者不能刪除。候選切換以排程屏障執行，成功才更新 active_model_id，任務固定使用提交時快照。切換不是檔名下拉選單的即時承諾。

### 9. 任務模型、資訊優先級與 content audit

| 層級 | 使用者任務 | 首屏支援與理由 |
|---|---|---|
| 唯一主目標 | 提交目前創作並看到結果 | 是，唯一主 CTA 隨分頁命名「產生圖片／開始修圖」 |
| 次目標 | 編輯提示、素材、框、遮罩與重試 | 是，但僅顯示當前模式必要欄位 |
| 低頻目標 | 改模型、下載 LoRA、匯出專案 | 模型頁／結果工具列，不占創作首屏 |
| 罕見目標 | 查錯、恢復損壞專案、重建環境 | 例外狀態展開診斷，不常駐 |

以下表同時定義資訊分類、資訊架構與揭露策略；`hidden_now_because`、`reveal_trigger`、`container` 是實作必填欄位。

| 資訊項目 | 分類／頻率 | 首屏／階段／content audit | 顯示條件與 container | hidden_now_because／reveal_trigger | 可收合 |
|---|---|---|---|---|---|
| 當前提示與必要素材 | action-critical／高 | 是／editing／must-see-now | 當前 tab 主操作區 | 不適用，持續顯示 | 否 |
| 畫框或筆刷畫布 | action-critical／高 | 條件是／editing／must-see-now | 排版或重繪時替換一般素材區 | 其他模式不用／切換對應模式 | 否 |
| GPU與工作階段 | status-feedback／高 | 是／全部／must-see-now | 頂部窄狀態列 | 不適用 | 否 |
| 最近結果與模型摘要 | decision-supporting／高 | 是／resolved／must-see-now | 結果區次要摘要 | 結果前顯示空預覽 | 否 |
| 下載與匯出 | action-critical／中 | 否／resolved／next-step-only | 結果工具列 | 尚無結果／成功產生 | 否 |
| CFG／SLG／scheduler | decision-supporting／低 | 否／editing／on-demand-reference | 進階 accordion | 一般流程不需／使用者展開且能力支援 | 是 |
| 原始 JSON | reference／低 | 否／editing／on-demand-reference | 排版 drawer | 拉框已足夠／按「檢視 JSON」 | 是 |
| 錯誤與恢復動作 | exception-handling／低 | 否／blocked／error-only | 原欄位旁或狀態列下 | 正常時無錯誤／驗證或執行失敗 | 是 |
| 模型下載／token 輸入 | action-critical／低 | 否／setup／next-step-only | 模型 tab | 創作時不需／管理模型或缺權重 | 是 |
| 歷史與診斷 | audit/history／罕見 | 否／任意／keep-off-first-viewport | 專案選單／診斷 drawer | 避免占用創作空間／明確點選 | 是 |

### 10. 狀態模型與揭露策略

| UI state | 進入條件／使用者目標 | 必顯 | 隱藏／停用 | 主 CTA | 退出條件 |
|---|---|---|---|---|---|
| empty | 新專案無輸入／開始創作 | 模式、提示、空預覽 | 下載、錯誤 | 輸入後可產生 | 編輯有效內容 |
| editing | 已輸入或修改／準備提交 | 當前輸入與預設摘要 | 歷史診斷 | 產生／開始修圖 | 點擊提交 |
| validating | 檢查素材與能力／確認可執行 | 檢查進度 | 重複提交、模型切換 | disabled「檢查中」 | 通過→submitted，失敗→blocked |
| submitted | 工作已入列／等待 | job id 短碼、排隊狀態 | 改已提交快照 | 取消 | 取得 GPU 鎖 |
| running | 正在編碼／採樣／解碼 | 階段、step、有則預覽 | 重複生成、切換模型 | 取消 | 成功／失敗／取消 |
| resolved | 圖片已原子保存／取用結果 | 結果、下載、設定摘要 | 無關錯誤 | 再次產生 | 編輯或新提交 |
| blocked | 能力缺失或執行失敗／恢復 | 具體原因、保留輸入、恢復動作 | 會重複失敗的提交 | 依原因重試或修正 | 修正後 editing |
| reconnecting | UI 連線中斷／找回工作 | 重連提示與最後已知 job | 新提交 | 重新連線 | ledger／history 對帳完成 |

Job 狀態機為 `created → validating → queued → encoding → sampling → decoding → saving → succeeded`。任一未完成狀態可進 `cancelling → cancelled`，或 `failed`；程序重啟遺留狀態標 `interrupted`，查詢 ComfyUI history 後才決定恢復成功或要求重跑。禁止失敗狀態直接寫成 succeeded。

任務執行中仍可編輯下一份草稿，但不能影響已提交 snapshot。重新開始只清目前草稿並要求確認未匯出修改；刪除專案是另一個明確動作。取消後可保留先前已完成作品。

### 11. UI 風格、元件與使用流程

風格為淺色、專業創作工具，主要視覺焦點是畫布／結果。主色深藍 `#1D4ED8` 表示主操作，輔色青綠 `#0F766E` 表示完成，底色灰白 `#F8FAFC`；強調色琥珀 `#B45309` 表示待確認，錯誤深紅 `#B91C1C` 搭配文字與圖示，不只靠顏色。

採「一次啟動設定 → 五 tab 創作 → 結果下載」流程。桌面首屏最多三群：主操作／結果、窄狀態列、次要設定摘要；唯一強調按鈕是當前主要動作。窄螢幕改上下堆疊，生成按鈕固定在可達位置，無橫向溢出。畫布與預覽始終保持比例。

| 元件 | 關鍵行為 |
|---|---|
| 五 tab | 各分頁草稿獨立保留，共用模型與單 GPU 狀態 |
| 提示 Textbox | 文字計數與實際 tokenizer 長度；上限依實測可用上下文，不以字數等同 4096 tokens |
| Profile Dropdown | 顯示名稱、限制，變動後重驗相容性；不覆寫未確認的自訂值 |
| Resolution controls | 比例與像素雙向換算，顯示實際 16 倍數；預覽改尺寸要確認 |
| LayoutCanvas | 自訂拉框、鍵盤刪除、數值微調、序列化 |
| 四個 Image upload | 檔案解碼後預覽、圖號與替換／移除 |
| ImageEditor | 筆刷、擦除、還原、遮罩預覽、原圖重置 |
| Reference／control viewer | 原圖與處理後圖切換，標示真正接入的控制 |
| Progress／Gallery | job 狀態、step、結果；預覽不是最終作品 |
| Model table／download | 大小、相容任務、來源／授權、下載與移除 |
| Project menu | 新建、開啟、重新命名、匯出、刪除、重新開始 |

#### 主要畫面示意（SVG）

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 660" role="img" aria-label="創作工作台配置">
 <rect width="1100" height="660" fill="#f8fafc"/>
 <g font-family="sans-serif" fill="#0f172a" font-size="17">
  <text x="30" y="38">MOSS-Image 創作工作台</text><text x="700" y="38">L4 已就緒 ｜ 專案：山間慢旅</text>
  <rect x="20" y="58" width="1060" height="50" rx="8" fill="#e2e8f0"/><text x="36" y="90">文生圖與排版　｜　多圖修圖　｜　筆刷重繪　｜　視覺與深度　｜　模型管理</text>
  <rect x="20" y="128" width="380" height="475" rx="10" fill="white" stroke="#cbd5e1"/><text x="40" y="160">創作內容</text>
  <rect x="40" y="178" width="340" height="125" rx="6" fill="#f1f5f9"/><text x="55" y="210">描述想要的畫面與文字…</text>
  <text x="40" y="337">預設：精細 50 步</text><text x="40" y="375">尺寸：1024 × 1024　種子：自動</text>
  <rect x="40" y="403" width="340" height="42" rx="6" fill="#f1f5f9"/><text x="55" y="430">▸ 進階設定與排版資料</text>
  <rect x="40" y="517" width="340" height="58" rx="8" fill="#1d4ed8"/><text x="160" y="553" fill="white">產生圖片</text>
  <rect x="420" y="128" width="660" height="475" rx="10" fill="white" stroke="#cbd5e1"/><rect x="545" y="155" width="410" height="360" rx="8" fill="#e0f2fe"/>
  <rect x="595" y="187" width="310" height="60" fill="none" stroke="#1d4ed8" stroke-width="2"/><text x="685" y="224">山間慢旅</text><text x="625" y="385">畫布／等比作品預覽</text><text x="445" y="560">完成後：下載圖片　匯出專案　再次編輯</text>
  <text x="30" y="637">狀態：已就緒；生成期間顯示階段與步數，進階說明預設收合。</text>
 </g>
</svg>
```

### 12. 專案目錄規劃

目錄以責任切分，不建立獨立前端站點或多服務微架構。Python 檔名 snake_case，工作流與 profile 用固定語意 id；所有模型、素材及輸出目錄均在 `.gitignore`，不納入原始碼交付。

| 路徑 | 代表檔案／責任 |
|---|---|
| `notebooks/` | `MOSS_Image_Colab.ipynb`，自足安裝與啟停入口 |
| `src/moss_studio/ui/` | `app.py`、`tabs.py`、`layout_component/`、`editor_adapter.py` |
| `src/moss_studio/domain/` | `jobs.py`、`projects.py`、`profiles.py`、驗證規則 |
| `src/moss_studio/services/` | `scheduler.py`、`resources.py`、`downloads.py`、`capabilities.py` |
| `src/moss_studio/adapters/` | `comfy.py`、`workflow.py`、`transport.py` |
| `src/moss_studio/storage/` | `projects.py`、`ledger.py`、`archive.py`、`migrations/` |
| `workflows/` | t2i／layout／edit／inpaint／vision／color_depth API JSON；UI graph 另存來源供比對 |
| `configs/` | `models.lock.json`、`runtime.lock.json`、`capabilities.json`、`profiles/` |
| `tests/` | `unit/`、`integration/`、`gpu/`、`fixtures/`；素材需可重散布 |
| `docs/` | 設定、操作、相容矩陣、benchmark、已知問題、stage evidence |
| 根目錄 | `pyproject.toml`、依賴 lock、`.env.example`、`README.md`、`AGENTS.md`、`CLAUDE.md`、`DEVNOTE.md` |

### 13. 核心資料模型、CRUD 與生命週期

| 實體／主鍵 | 必要欄位與關聯 | Create／Update／Delete 與狀態 |
|---|---|---|
| Project／UUID | schema_version、name、revision、created_at、updated_at、各分頁 draft、asset_ids、job_ids | 新建；改名／改草稿採 revision CAS；刪除前確認與取消其工作，關聯素材無引用才回收 |
| Asset／SHA256+UUID | project_id、kind、path、mime、width、height、bytes、sha256、transform、source_order | 上傳解碼後建；替換建新版本；移除引用，再清無引用檔；uploaded→validated→ready／rejected |
| LayoutItem／UUID | project_id、label、caption、text、normalized_bbox、z_order | 新增／移動／文字修改／刪除；與 draft revision 同步 |
| Mask／asset_id | source_asset_id、尺寸、mask transform、edge_softness、feather_px | 筆刷變更建遮罩版本，清除成 empty，歷史按保留上限回收 |
| Job／UUID | project_id、client_request_id、snapshot、snapshot_hash、comfy_prompt_id、status、stage、error、output_assets、timestamps、metrics | 建立後 snapshot 不可變；只有狀態／進度更新；取消是狀態操作；完成紀錄可刪但輸出需獨立選擇 |
| ModelArtifact／id | lock 欄位、download_state、local_path、verified_at、capabilities | 新增候選／改顯示名與設定／移除；權重有變更必建立新 artifact revision |
| SamplingProfile／id+version | model_constraints、steps、cfg、sampler、scheduler、shift、slg、lora_stack | 內建版本不可覆寫；另存自訂／改自訂／刪自訂；工作引用其快照 |

Project 一對多 Asset、LayoutItem、Job；Job 以 asset_id 引用輸入與輸出。最近工作依 created_at 排序；模型依 ready 狀態及名稱查詢。刪除不得跟隨 symlink 或跨出本工具 root。被工作引用的資產標 pending_delete，待工作終止再回收。

### 14. State 管理、持久化與續編

`gr.State` 只存 session id、目前 tab、選取框及暫時操作，不當唯一資料來源。草稿更新採 500ms debounce，本機 project JSON 以 temp＋fsync＋rename 保存，revision 不符回報 conflict，禁止覆蓋較新資料；job ledger 用 SQLite 交易記錄，狀態更新與檔案完成後再發成功事件。

Project ZIP 包含 `project.json`、素材、遮罩、排版、參數、結果與 provenance；不包含模型權重、secret、登入 session 或任意外部路徑。匯入先檢查 manifest 及所有 hash，再搬入新 project_id；不覆寫原專案。schema_version 提供逐版 migration 與固定 fixture，新版不識別欄位需保留於 extensions 或拒絕，不靜默遺失。

本地自動保存可承受 UI 關閉與瀏覽器重開，**無法承受 Colab VM 被回收**。持久續編靠使用者下載專案 ZIP，或選用 Drive 並確實寫入。每次結果完成顯示「尚未匯出」狀態；下載只能記為「已提供下載」，無法保證瀏覽器真的寫入磁碟。可選「已自行保存」確認。

### 15. 服務介面、ComfyUI API 與 UI 對照

以同一 Python 程序的 typed service methods 為主，不額外公開一套不必要的 REST 服務。若要 polling transport，提供同源、需認證的薄 HTTP adapter，語意與下表一致；方法名稱為本案設計，非 Gradio 官方介面。

| 本案服務 | 請求 | 回應／語意 | UI 來源 |
|---|---|---|---|
| `inspect_runtime()` | 空 | GPU／RAM／disk／capabilities | 啟動與狀態列 |
| `import_asset()` | project_id、bytes、kind、revision | asset_id、尺寸、preview_ref、new_revision | 各上傳與筆刷 |
| `compile_layout()` | canvas、items、revision | JSON、warnings、new_revision | 拉框／JSON 編輯 |
| `submit_job()` | JobSpec、client_request_id | job_id、status | 唯一主 CTA |
| `get_job()` | job_id、after_seq | 狀態、事件增量、結果 refs | 重連／進度／polling |
| `cancel_job()` | job_id | cancelling／cancelled／already_terminal | 取消 |
| `activate_model()` | artifact_id、expected_generation | switch_id 或 busy | 模型選單 |
| `download_model()` | provider_ref、artifact_spec | download_job_id | 下載器 |
| `save_project()/export_project()` | project_id、revision | new_revision／download_ref | 專案選單 |
| `import_project()/delete_project()` | archive／project_id+confirmation | project_id／deleted | 開啟／刪除 |

示例 JobSpec 為應用層格式，編譯器再轉成真正 ComfyUI API graph；禁止把以下 JSON 原樣傳到 `/prompt`。

```json
{
  "project_id": "a-generated-project-uuid",
  "client_request_id": "a-generated-request-uuid",
  "project_revision": 12,
  "task": "instruction_edit",
  "profile_id": "edit_sft_v1",
  "model_artifact_id": "sft_bf16_pinned",
  "prompt": "保留圖1的角色，參考圖2的配色",
  "negative_prompt": "",
  "width": 1024,
  "height": 1024,
  "seed": 42001,
  "references": [{"asset_id": "asset-1", "slot": 1}, {"asset_id": "asset-2", "slot": 2}],
  "layout": null,
  "mask_asset_id": null,
  "control": null,
  "lora_stack": []
}
```

回應事件格式為 `{job_id, seq, timestamp, type, stage, progress, preview_ref, error}`；seq 單調遞增，client 可依 after_seq 補取。錯誤 `{code,message,retryable,field,details_redacted}`，HTTP adapter 語意 400 輸入、401／403 認證、409 revision／busy、413 大小、422 能力、503 引擎不可用。

ComfyUI adapter 預定整合 `/object_info`、`/prompt`、`/ws`、`/history/{prompt_id}`、`/queue`、`/upload/image`、`/view` 與 `/interrupt`；**確切 method／payload 需對固定版本原始碼做契約測試**。只用 API 格式 graph；含 subgraph 的 UI 範本先轉換／展平並用服務端驗證，不能直接傳 UI JSON。輸出透過受控 asset 路由讀取，永不將 `/content` 整體列為可下載目錄。

### 16. 背景工作、通知、取消與重試

排程上限為 1 running＋2 queued（產品初始值）；模型切換與下載校驗亦受相應鎖保護。去重範圍為 project_id＋client_request_id；同 key 相同 snapshot 返回原 job，不同 snapshot 回報 conflict。前端重連不重新提交。

ComfyUI 的 interrupt 可能影響目前執行工作，因此只在本工具持有獨占引擎且確認 prompt_id 為 current job 時呼叫；queued job 只移除自己的排隊項目。取消須等待執行階段退出並清理後才釋放 GPU 鎖；超過 30 秒仍無回應則顯示「取消尚未完成」，取得使用者操作或以僅屬本工具的 engine restart 恢復，不假裝立刻成功。

進度至少回報 encoding／sampling／decoding／saving；step progress 有事件才顯示，不以假百分比補滿。預覽可限流至每 2 秒最多一次。SSE 相容路徑可使用 Streaming；若啟用 LLM 提示增強，文字亦需 Streaming。Quick Tunnel 路徑只有通過不依賴 SSE 的同源 polling adapter 才可放行，輪詢間隔初始 1 秒、背景頁可放慢至 5 秒。

事件失聯 60 秒進入 stalled，先查 history；不同階段使用可配置 watchdog，不能憑無預覽判定採樣死亡。下載網路錯誤最多 3 次退避；推論僅同參數保守卸載重試一次，且顯示重試原因；其他推論錯誤需使用者明確重跑。失敗保留 ledger 並在狀態列告警，單人版不建外部死信系統，也不寄信／推播。

### 17. 連線、隱私與安全界線

ComfyUI 綁 `127.0.0.1:8188`，Gradio／app 綁 `127.0.0.1:7860`，只向通道公開 app。單次啟動產生高熵密碼或使用使用者提供憑證；驗證必須覆蓋頁面、提交、狀態、預覽、輸入資產與下載，不能只保護首頁。瀏覽器不直連 ComfyUI。

| transport | 產品定位 | 放行條件與 fallback |
|---|---|---|
| Cloudflare Quick Tunnel | 原方案指定候選；非預設可認定相容 | Stage 1 測固定 Gradio 的上傳、生成、進度、取消、下載；標準事件路徑若依賴 SSE 即 blocked |
| Quick Tunnel＋polling adapter | 免帳號候選替代傳輸實作 | 生成及查詢路徑都不能偷偷依賴 SSE；認證、cookies、重連測試通過才啟用 |
| Named Cloudflare Tunnel | 可選相容路徑候選 | 需使用者帳號／網域及憑證；不假設現有。對固定配置完成 SSE、下載與認證驗證 |
| Colab 內可用的受保護預覽 | 開發診斷 fallback | 先驗證實際可用與權限，不承諾未查證的 proxy 機制 |

若 Quick Tunnel 失敗且替代路徑未通過，啟動只顯示本機診斷與具體缺項，不退回 `share=True`。正式部署若需新增帳號／網域或改用 Gradio share，由使用者另行決策；規格可先開發其餘功能，整體發布狀態保持 blocked。

HTTPS 不代表端對端內容保密、平台看不到內容、避開審查或帳號不受限制。通道及運算供應者仍位於資料路徑；不提供「防風控」功能。關閉後停止通道與本工具程序，清理工作暫存；刪除全部作品需另一個明確按鈕，不能關閉時靜默清空未匯出成果。

### 18. 上傳、下載與匯入防錯

產品初始限制：每張圖片最多 20 MiB／20 MP，接受 PNG、JPEG、WebP 靜態圖；先確認 magic bytes 再解碼，處理 EXIF 方向、轉 RGB／RGBA、移除 EXIF／GPS。動畫先拒絕並解釋。任何拒絕保留原有有效輸入；成功上傳一律預覽。不得以檔名作系統路徑。

來源 URL 必須 https、限制 provider allowlist；解析每次 redirect 的 hostname 與 IP，拒絕 loopback、私有、link-local、metadata IP 與不受允許目的地，限制 redirect 次數及下載大小。對 Hugging Face／Civitai 的 CDN 必須建立已審核的可更新 allowlist，不能任意追隨 redirect。token 不得跟隨跨站跳轉。

專案 ZIP 最多 1 GiB 壓縮、4 GiB 展開、5000 entries、單檔 256 MiB，壓縮比超過 100 倍拒絕；只允許 manifest 中的相對路徑，拒絕 `..`、絕對路徑、symlink、重名及非法 hash。匯入在私有 staging 驗證後提交；失敗清 staging。作品 ZIP 按固定排序，只有 PNG／JPEG 與選擇納入的 metadata；預設作品圖不嵌完整提示與來源，完整追溯內容只在明確勾選的專案包中保存。

### 19. 錯誤、回退、可觀測性與 UI 事件回報

| code／情境 | 顯示文字 | 回復策略 |
|---|---|---|
| E_GPU_PROFILE | 實際環境不符合已驗證設定 | 顯示偵測值與必要資源，不自動換付費機型 |
| E_CAPABILITY | 此功能尚缺已驗證的節點或權重 | 指向模型頁與缺項，保留草稿 |
| E_TRANSPORT | 目前通道無法完成介面通訊 | 顯示測試結果與可選路徑，不無限重啟 |
| E_OOM | 記憶體不足，本次未完成 | 清理本工作，有限同參數重試；仍失敗供降低負載選擇 |
| E_MASK_EMPTY | 請先塗抹要修改的區域 | 回畫布，不提交 |
| E_MODEL_INCOMPATIBLE | 此 LoRA 與目前模式未通過相容測試 | 顯示可選組合，不靜默忽略 LoRA |
| E_DOWNLOAD_AUTH／HASH | 下載需授權／檔案驗證失敗 | 不登錄 ready，移除壞片段或重取 |
| E_CONFLICT | 專案已在另一個頁面更新 | 重新載入或另存草稿，不覆蓋 |
| E_ENGINE／E_INTERRUPTED | 引擎中斷，正在核對工作紀錄 | 查 history，再提供重跑；不重複產生 |

結構化本機 JSONL logs 含 timestamp、event、job_id、stage、duration_ms、memory、version、error_code；不記 token、cookie、原圖 bytes 或完整提示詞。作品 provenance 是使用者可選保存資料，與診斷日誌分開。每工作 trace_id 串接下載／編譯／推論／保存；本機 metrics 包括失敗率、OOM、取消延遲、生成時間、記憶體峰值與下載重試數，不外送分析服務。

| UI event | 觸發／欄位 | 用途 |
|---|---|---|
| asset_uploaded／rejected | kind、bytes、dimensions、code | 上傳品質，無原始檔名 |
| layout_changed | project_id、revision、box_count | 對帳，無文字內容 |
| job_submitted／stage／terminal | job_id、task、profile、stage、elapsed | 進度、追錯 |
| model_switch_requested／done | artifact_id、generation、result | 驗證交易切換 |
| project_export_offered／imported | project_id、schema_version、size | 續編診斷，不聲稱下載已落地 |
| transport_probe | mode、check、result | 通道相容性 |

### 20. 非功能需求與驗收條件

可用性：一般創作無需接觸節點或命令；鍵盤可到達主要控制、欄位錯誤就地顯示。可靠性：重連依 ledger 對帳、原子保存、單 GPU 不競態。可維護性：UI、domain、adapter 分離；更新上游需重跑契約與 GPU 回歸，不追蹤浮動 latest。成本：畫面顯示 Colab 為持續消耗資源的執行環境，不估算未查證價格，不建立自動續費或 keepalive。

以下驗收 ID 是產品發布關卡。速度資料先建立 baseline，不以草稿秒數作門檻；畫質另用固定評測集，不能以「能輸出一張圖」代替功能成功。

| ID | 驗收情境與可測門檻 | 證據 |
|---|---|---|
| AC-01 | 乾淨 L4 Colab 安裝、啟動；重跑啟動不產生第二個引擎或重下載已校驗檔 | Notebook 記錄、PID、hash |
| AC-02 | 未登入的頁面、狀態、上傳、預覽、作品下載均被拒；ComfyUI 無公開入口 | 獨立瀏覽器與 HTTP 測試 |
| AC-03 | 選定通道完整完成上傳→生成→進度→取消→重連→ZIP 下載 | 傳輸契約測試；Quick 路徑確認無 SSE 依賴 |
| AC-04 | 1024² SFT bf16 基準 5 次成功；無 NaN／OOM／黑圖 | benchmark JSON與輸出 |
| AC-05 | 正方／橫／直三種畫布，邊界／反拖／縮放共 30 組座標測試，全數誤差≤1px | 自動單元測試 |
| AC-06 | 固定版本 8-step 工作流 5 次成功，確實使用對應 LoRA與設定；報與50步耗時／品質差異 | profile、workflow hash、benchmark |
| AC-07 | 50步、Euler、CFG／SLG 設定與實際 graph 一致；切回8步沒有殘留參數 | graph contract與輸出 |
| AC-08 | 1／2／4 圖各至少3案例；主圖比例、圖號與指令對應正確，四圖無OOM | 測試素材與人工量表 |
| AC-09 | 筆刷遮罩方向正確；黑／白筆均有效；柔邊外像素逐像素一致；空白及全白路徑正確 | 遮罩單測、差分圖 |
| AC-10 | 視覺參考確實走視覺塔，不退成文字；參考開／關及權重對照，5案例至少4例符合主要參考特徵 | workflow trace與量表 |
| AC-11 | 深度、silhouette／color 各有實際接入對照；5例至少4例保留主要幾何／區塊關係 | 控制圖、輸出與評分 |
| AC-12 | 2048² 在目標L4以宣告profile連續3次完成；記憶體峰值與用時公開 | GPU報告；替代放大不得算此項通過 |
| AC-13 | SFT↔Base各3次；忙碌時不切換；失敗回復；無持續增加的活躍模型引用 | 切換事件與資源趨勢 |
| AC-14 | 修圖／加速／風格LoRA不支援組合被攔截；刪除正在使用檔案被阻擋 | 相容矩陣測試 |
| AC-15 | 專案ZIP匯出後新執行階段匯入，輸入、遮罩、排版、設定及既有作品hash一致 | round-trip測試；跨GPU不要求生成bitwise一致 |
| AC-16 | 重複提交僅一工作；斷線不重跑；取消只影響自己的工作；故障後不誤報成功 | 故障注入 |
| AC-17 | 網址／ZIP／圖檔異常、防路徑穿越、大小限制、token遮罩均通過 | 邊界測試 |
| AC-18 | 固定10個繁中排版、5個局部修補、5個一般生成案例；各類至少80%案例達下述品質標準 | 原圖、輸出、完整失敗例與評分表 |

品質量表：每案例預先標 3 項必要特徵，滿足至少 2 項且無全黑／嚴重破圖才算成功。繁中案例另要求預定標題逐字正確及主要框區域位置合理（人工檢查區域，可輔以 OCR）；局部修補要求修改確實發生、主體身分未明顯漂移、柔邊無明顯接縫。評分案例與標準在跑模型前固定，不能跑完才挑圖或降低標準。未通過保留失敗證據並標 blocked。

#### 測試案例與 Gherkin／BDD

```gherkin
Scenario: 瀏覽器重新連線不重複生成
  Given 一個已入列的工作與固定 client_request_id
  When 使用者重新連線並查詢該工作
  Then 顯示原工作的階段或結果
  And ComfyUI 只收到一次相同工作提交

Scenario: 未塗抹遮罩不執行重繪
  Given 原圖存在且遮罩全黑
  When 使用者按開始重繪
  Then 顯示 E_MASK_EMPTY
  And 不建立 GPU 工作

Scenario: 不相容的加速設定
  Given 8-step profile 不支援手動 SLG
  When 請求包含未允許的 SLG 覆寫
  Then 拒絕提交並指出衝突欄位
  And 不偷偷移除該設定後繼續
```

### 21. Edge／Abuse cases、建議補充與發布風險

| 邊界 | 明確行為 |
|---|---|
| 上傳解碼／預覽失敗 | 不替換既有資產，提示格式或解碼原因 |
| 4096上下文／多圖超長 | 使用實際 tokenizer 與視覺位置預算驗證；不靜默截尾 |
| 超長檔名、Unicode、同名輸出 | 以UUID命名，顯示名稱獨立保存 |
| 多頁面同時編輯 | revision conflict，提供另存；不使用最後寫入勝出 |
| 下載HTML冒充權重 | 檔頭與hash失敗，不列ready |
| RAM不足但GPU有空間 | 阻擋RAM快取或逐出；不能繼續到系統OOM |
| UI關閉／VM回收 | 前者可找回本地專案；後者僅匯出或Drive副本可恢復 |
| JSON中嵌入指令／路徑 | 只解析允許欄位，不執行、載入插件或套用任意Comfy graph |
| 引擎成功但保存失敗 | 標 saving_failed，提供恢復保存；不能顯示已保存 |
| 部分下載後版本改變 | 不混合分段，重建對應revision下載 |

建議補充：P1 作品參數比較／固定種子重跑；P1 繁中拼字檢查與輸出文字人工覆核；P2 可選 Drive 專案同步；P2 參考素材授權備註。這些不應延後必要五分頁驗收。

未決事項均有 owner：開發者負責固定版本／精度／通道／工作流相容性；使用者只需在實際啟用需要帳號／網域的通道或選購資源時決定。研究不再重複詢問已確定的方案 A。若核心 2K、8-step、四圖、重繪、vision 或控制無法通過，需交付證據與最小修正提案，不能偷偷縮成文生圖 MVP 並稱全案完成。

### 22. 來源與文件驗證記錄

公開來源查閱日期均為 2026-11-07。分別將上游能力、社群實驗與本案設計區分，文件中的未測值不得在交付文案改成保證。

- [R1 OpenMOSS 使用指南](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md)：推論建議與排版格式。
- [R2 ComfyUI MOSS-Image 文件](https://github.com/Comfy-Org/docs/blob/main/tutorials/image/moss-image/moss-image.mdx)：原生範本、版本及模型檔案。
- [R3 lodestones 8-step 模型卡](https://huggingface.co/lodestones/MOSS-Image-SFT-8-steps-dmd)：版本敏感的加速設定，包含 deprecated 區段。
- [R4 視覺節點作者 repo](https://github.com/ThetaCursed/ComfyUI-MOSSImageTextEncoder)：視覺條件與參數。
- [R5 Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)：公開入口、認證選項與 SSE 限制。
- [R6 Colab FAQ](https://research.google.com/colaboratory/intl/en-GB/faq.html)：資源與網頁介面使用條件。
- [R7 OpenMOSS 官方 repo](https://github.com/OpenMOSS/MOSS-Image)：官方程式與示範入口；不作五分頁功能完整性證據。
- [R8 Gradio ImageEditor 文件入口](https://www.gradio.app/docs/gradio/imageeditor)：本次抓取失敗；列為開發需核對資料，不列已讀證據。

文件 QA 包含章節／驗收 ID／階段指令完整性、JSON／SVG 語法、白話用語檢查。這些僅驗證規格文件，不取代產品 GPU 或通道驗收。產品驗收目前全部尚未執行，發布狀態為 **待開發／未放行**。

## 非技術規格文件

### 這個工具是給誰用的

這個工具是給想在 Colab 製作圖片、海報或修圖的人使用。你只需在一個網頁選擇工作方式，不需要自己連接複雜的運算節點。

前提是取得足夠的 Colab 運算資源；預計以 L4 的環境測試。付費方案仍可能分配不同設備，工具會先檢查，符合條件後才開放已驗證的功能。

### 你能完成哪些工作

| 頁面 | 你能做的事 |
|---|---|
| 文生圖與排版 | 描述想要的圖片，拉框安排標題和角色，選擇較少或較多的繪製步驟 |
| 多圖修圖 | 放入一到四張圖片，說明每張用途，再描述要修改的內容 |
| 筆刷重繪 | 塗抹要改的區域，確認遮罩，再讓工具重新繪製選取位置 |
| 視覺與深度 | 參考圖片的大致構圖、色彩或立體關係，產生新的內容 |
| 模型與風格管理 | 選擇已驗證的創作引擎，加入相容的風格檔案，移除不再使用的檔案 |

### 你會怎麼使用它

先開啟提供的 Colab 筆記本，啟動工具並等待檢查、下載和載入完成。畫面會顯示實際設備與進度，不會要求你先把大型檔案存進 Google Drive。

接著開啟受登入保護的創作頁面，選擇工作方式。上傳後會先看到圖片預覽；放大或縮小時保持原本比例，不會把人物拉扁或拉長。多張圖各有清楚圖號，換圖時可以先確認指令是否仍指向正確圖片。

設定好後按「產生圖片」或「開始修圖」。過程會顯示目前階段、繪製步數和可提供的預覽；完成後再下載作品。你可以取消未完成的工作，原本輸入會保留。

### 畫面風格與主要配置

畫面以灰白底搭配深藍操作按鈕，完成提示用青綠色，需要注意的地方用琥珀色。左側準備創作內容，右側看畫布與結果；其他細部設定平常收起來，需要時再打開。

手機或較窄視窗會改為上下排列。一次只強調一個主要操作，避免同時看到所有頁面的設定。

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" role="img" aria-label="使用者看到的創作畫面">
 <rect width="900" height="420" fill="#f8fafc"/>
 <g font-family="sans-serif" font-size="18" fill="#0f172a">
 <text x="25" y="35">選擇工作：文生圖｜多圖修圖｜筆刷重繪｜視覺與深度｜模型管理</text>
 <rect x="25" y="65" width="315" height="280" rx="10" fill="white" stroke="#cbd5e1"/>
 <text x="45" y="105">寫下想法、放入圖片</text><text x="45" y="150">選擇尺寸與繪製方式</text><text x="45" y="200">需要時才打開細部設定</text>
 <rect x="45" y="260" width="275" height="55" rx="8" fill="#1d4ed8"/><text x="135" y="295" fill="white">產生圖片</text>
 <rect x="365" y="65" width="510" height="280" rx="10" fill="#e0f2fe"/>
 <text x="510" y="180">畫框、塗抹與作品預覽</text><text x="490" y="285">完成後可下載或繼續修改</text>
 <text x="25" y="390">目前進度與需要處理的問題，會在這裡清楚告訴你。</text>
 </g>
</svg>
```

### 保存、續編與重新開始

你可以把整個專案下載成一個檔案，裡面保留圖片、排版、筆刷範圍、創作設定及完成作品。下次重新啟動工具，再開啟這個專案，就能接著修改；也可只下載成品圖片。

工具會在目前 Colab 環境保留工作進度，但 Colab 結束或重建時，本地內容可能消失。想保留工作，請下載專案；如果選擇使用 Google Drive，才會另存到你的雲端空間。按「重新開始」只清空目前草稿，刪除整個專案會另外詢問。

### 提示語與常見問題

| 畫面提示 | 代表什麼／你可以怎麼做 |
|---|---|
| 正在準備創作環境 | 等待檢查、下載與載入；會顯示進度 |
| 正在繪製，第 3／8 步 | 圖片尚未完成，預覽可能與最後結果不同 |
| 請先塗抹要修改的區域 | 回到筆刷畫布選取範圍，再開始重繪 |
| 此功能尚缺必要檔案或測試 | 查看管理頁的缺項；工具不會假裝功能已啟用 |
| 記憶體不足，本次未完成 | 原本輸入保留，可依提示降低尺寸或減少參考圖 |
| 連線中斷，正在找回工作 | 重新連線後查找原工作，不必連按生成 |
| 圖片已完成，專案尚未匯出 | 可下載圖片；想下次接著改，請另下載專案 |

### 限制與注意事項

繪製較少步驟不一定在每台設備都一樣快；需要第一次測試後才會顯示實際速度。高解析度、多張參考圖及複雜排版可能需要更多記憶體。

中文字、手指、人物身分、接縫和指定姿勢仍可能畫錯，需要你檢查結果。參考深度圖只能協助跟隨大致幾何，不保證姿勢完全一致，也不是調整鏡頭景深的專用功能。

創作引擎與風格檔案有相容限制，無法任意混用。切換引擎可能需要等待，不保證立即完成；功能尚未通過測試時會清楚說明。

登入保護與加密連線可以降低未授權存取，但不代表運算或連線提供者看不到資料，也不保證內容無限制。公開網址必須有登入保護；工具不會用一個「無審查」按鈕保證帳號安全。

### 成功完成後會得到什麼

你會得到一張可下載的圖片，以及選擇保存的創作設定與專案檔。每個必要功能都必須通過測試，才能把這個工具稱為完整交付；只有幾個頁面能開啟，不能算完成。

## Codex / Claude Code 分階段開發計畫

### 執行總則

以下指令配合本規格使用，實作目錄稱 `moss-colab-studio/`。每階段先讀 `DEVNOTE.md`、規格與適用的 `AGENTS.md`／`CLAUDE.md`。完成後留下檔案變更、實際命令、測試結果、未決風險及回滾點；未通過該階段 DoD 先修復，遇到必要外部資源才明確標 blocked。任何階段不可把未跑的 GPU 測試寫成 PASS。

所有階段均保持單 GPU 排程、`share=False`、ComfyUI loopback、固定版本與已提交工作快照不可變。若加入 LLM 提示增強，Codex 與 Claude Code 版本都要求 Streaming；圖片本身用真實階段／步數／可用預覽，不虛構文字或影像增量。全功能發布前 AC-01～AC-18 必須全通過。

### Stage 0：建立專案骨架與可續編基礎

目標：建立可測的模組與資料契約。前置：取得本規格；不需先下載模型。

**Codex Instructions**

```text
直接貼給 Codex；把長期規則記入專案 AGENTS.md。
範圍：建立 MOSS-Image Colab Studio 的 Python 骨架與 project/job/asset 契約，不實作模型推論或對外發布。
檔案：pyproject.toml、README.md、.env.example、AGENTS.md、DEVNOTE.md、src/moss_studio/{domain,storage,services,adapters,ui}/、tests/unit/、configs/。
步驟：建立型別與驗證；實作原子專案JSON、revision CAS、SQLite工作紀錄、schema_version=1遷移入口與無敏感資料seed fixture；設定ruff、pytest及依賴鎖定策略。規劃可選LLM輸出必須Streaming。
測試：project新增/改名/刪除、revision衝突、狀態轉移與原子寫入中斷；不得用空殼測試宣稱推論可用。
DoD：CPU可跑領域/保存測試；目錄責任與技術規格一致；無secret或權重入版控。
輸出：變更清單、實際驗證、剩餘缺口與DEVNOTE更新。
```

**Claude Code Instructions**

```text
直接貼給 Claude Code；把長期規則寫入 CLAUDE.md。
建立 MOSS-Image Colab Studio 基礎，不接GPU、不啟動公開服務。
新增pyproject.toml、README.md、.env.example、CLAUDE.md、DEVNOTE.md、src/moss_studio/{domain,storage,services,adapters,ui}/、tests/unit/、configs/。
依本規格建立project/job/asset欄位與狀態規則、原子JSON、revision CAS、SQLite ledger、schema_version=1與seed fixture；設定ruff/pytest及版本鎖。可選LLM必須Streaming。
執行新增修改刪除、衝突與保存中斷測試；驗收為CPU測試通過且未假造推論能力。
回報檔案變更、實際命令、風險與回滾點，更新DEVNOTE。
```

風險／回滾：資料契約不穩先調整 fixture；只回滾本階段程式與測試資料，不刪使用者專案。

### Stage 1：驗證 Colab、模型與連線前置條件

目標：將重要假設轉為證據，建立可重跑啟動器。前置：Stage 0；實際 L4 Colab 與必要下載權限。

**Codex Instructions**

```text
直接貼給Codex並遵守AGENTS.md。實作環境與相容性驗證，不宣稱五分頁已完成。
檔案：notebooks/MOSS_Image_Colab.ipynb、configs/{runtime.lock.json,models.lock.json,capabilities.json}、src/moss_studio/adapters/{transport,comfy}.py、services/{downloads,resources}.py、tests/integration/test_bootstrap.py、docs/compatibility.md。
步驟：偵測GPU/RAM/disk；讀固定版ComfyUI與Gradio原始碼/文件，確認ImageEditor和事件傳輸；固定依賴、repo commit及模型revision/hash。實測bf16主幹+int8編碼器的text/edit/vision載入。建立idempotent啟停與健康檢查。
測Quick Tunnel完整操作，若SSE衝突則測同源polling adapter；若仍不通列blocked，不改share=True。Named tunnel需既有授權與憑證才啟用。LLM若加入必須Streaming，Quick路徑需相容傳遞。
測試：冷啟動、重跑、下載中斷/hash錯誤、認證覆蓋與傳輸AC-01～03；保留尚未通過項目。
DoD：至少一條符合要求的入口完成端到端測試，固定環境與來源可重現；不足時交付阻礙證據，不越過發布gate。
輸出：版本/資源/傳輸矩陣、命令與DEVNOTE。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，遵守CLAUDE.md；先驗證實際L4 Colab的環境與入口。
修改notebooks/MOSS_Image_Colab.ipynb、configs/runtime.lock.json、models.lock.json、capabilities.json、adapters/transport.py與comfy.py、services/downloads.py與resources.py、tests/integration/test_bootstrap.py、docs/compatibility.md。
讀固定ComfyUI/Gradio版本的原始碼與文件，填commit/revision/SHA256，確認ImageEditor及SSE依賴；跑bf16主幹+int8編碼器的text/edit/vision探測。建立可重跑且無重複程序的啟停器。
測試Quick Tunnel上傳、生成、進度、取消、重連、下載及認證；不支援時先驗證polling adapter，仍失敗標blocked，不偷偷share=True。需帳號/網域的入口只有取得必要設定才測。任何LLM文字輸出必須Streaming。
測冷/熱啟動、錯誤下載與AC-01～03；DoD為固定版本和至少一條符合要求的實際入口通過，未執行不算PASS。
輸出相容矩陣、驗證命令、阻礙與DEVNOTE。
```

風險／回滾：版本不相容回到最後通過的 lock；通道 blocked 可繼續離線單元工作，但不得公布可用入口。

### Stage 2：完成文生圖與視覺排版垂直切片

目標：第一條可由 UI 完整產圖保存的使用流程。前置：Stage 1 至少基本推論可用。

**Codex Instructions**

```text
直接貼給Codex；依AGENTS.md與規格完成T2I+Layout，不做其他分頁的假按鈕。
檔案：ui/app.py、ui/tabs.py、ui/layout_component/、domain/layout.py、adapters/workflow.py、workflows/{t2i,layout}.json、tests/unit/test_layout.py、tests/gpu/test_t2i.py。
步驟：建立五tab導航但未實作頁標示未驗證；完成提示/尺寸/種子、API graph編譯、單工作提交與結果保存。Canvas用contain座標變換、normalized儲存、中心yxyx編譯；支援框新增/改/刪、JSON同步及revision衝突。排版停用prompt enhancer；若加入LLM增強必須Streaming且保留最終文字。
測試：30組三種比例座標、非法JSON、邊界框、UI重連；跑AC-04/05並保存繁中案例。
DoD：能由真實Gradio生成保存1024圖；座標誤差≤1px；輸出含實際seed與workflow hash。
輸出：畫面、工作紀錄、測試結果及DEVNOTE；不得聲稱字形100%正確。
```

**Claude Code Instructions**

```text
直接貼給Claude Code並遵守CLAUDE.md。完成真實文生圖與拉框排版，不擴展到修圖。
新增/修改ui/app.py、ui/tabs.py、ui/layout_component/、domain/layout.py、adapters/workflow.py、workflows/t2i.json與layout.json、tests/unit/test_layout.py、tests/gpu/test_t2i.py。
實作提示、尺寸、seed、API graph提交、保存及預覽；Canvas等比contain、normalized框與中心yxyx，新增/移動/改文/刪除與JSON雙向同步，revision防覆寫。排版不改寫JSON；若啟用LLM提示生成必須Streaming。
執行30組正方/橫/直座標、非法JSON、空框、重連與AC-04/05；驗收為真實1024生成保存且≤1px座標誤差。
輸出變更、案例圖、已跑命令、未解風險與DEVNOTE。
```

風險／回滾：自訂元件相容失敗可暫以數值框編輯診斷，但拉框 AC 不通過；保留舊版專案欄位遷移。

### Stage 3：完成 8／50 步預設與 GPU 調度

目標：可重現切換採樣模式而不殘留設定。前置：Stage 2；固定 DMD artifact。

**Codex Instructions**

```text
直接貼給Codex；本階段僅做預設與記憶體，不新增未驗證LoRA疊加。
檔案：configs/profiles/{quality50,fast8}.json、services/resources.py、domain/profiles.py、workflows/fast8.json、tests/gpu/test_profiles.py、docs/benchmarks.md。
先讀當版DMD作者卡/實作，分清deprecated內容；固定精度、sampler、CFG、強度與相依檔。quality50初始Euler/CFG3/shift5/SLG22，再以工作流契約核對。建立編碼/採樣/解碼卸載、單GPU鎖、OOM同參數一次重試與RAM預算。LLM若有文字輸出必須Streaming。
跑AC-06/07及兩profile暖機1次+5次量測，記冷/熱與各階段耗時、RSS/VRAM峰值；不把3～4秒寫保證。
DoD：兩模式真實產圖、切換無殘留，記錄實際模型hash與可用設定；未通過的模式保持blocked。
輸出效能/品質差異、測試、DEVNOTE與回滾profile。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，依CLAUDE.md完成採樣預設與GPU調度。
修改configs/profiles/quality50.json與fast8.json、services/resources.py、domain/profiles.py、workflows/fast8.json、tests/gpu/test_profiles.py、docs/benchmarks.md。
依固定revision的DMD當版實作建立8步路徑，不混用deprecated fp32教學；50步路徑核對Euler/CFG/shift/SLG。實作分段卸載、單GPU鎖、RAM預算與一次同參數OOM重試。LLM文字若啟用必須Streaming。
測AC-06/07、參數殘留及暖機1次後各5次資源/耗時/品質量測。DoD為兩模式實際完成且設定可追溯，不能以假資料替代GPU報告。
輸出差異表、命令、失敗與DEVNOTE。
```

風險／回滾：候選 DMD 不相容則退回已驗證50步並標加速 blocked；不能當全功能完成。

### Stage 4：完成四張參考圖的指令修圖

目標：圖號與指令一致，四圖可在 L4 完成。前置：Stage 3、Edit LoRA 通過載入。

**Codex Instructions**

```text
直接貼給Codex；僅實作SFT+固定Edit LoRA，不假設Edit-HQ可互換。
檔案：ui/edit_tab.py、domain/references.py、workflows/edit.json、tests/gpu/test_edit.py、tests/fixtures/edit/。
建立四上傳格、預覽、替換/刪除、主圖與圖號確認；編碼正負路徑使用同一edit_format與有序資產陣列。等比預處理並記transform；編碼後卸載。LLM增強若存在必須Streaming。
以1/2/4圖各3案例測AC-08，含交換參考順序、留空槽位、token/視覺預算與OOM；保留失敗輸出。
DoD：四圖可完成且不靜默改圖號、指令確實生效、輸出比例跟主圖，記憶體報告齊全。
輸出案例表、實際設定、測試與DEVNOTE。
```

**Claude Code Instructions**

```text
直接貼給Claude Code；遵守CLAUDE.md實作有序1～4圖指令修圖。
新增ui/edit_tab.py、domain/references.py、workflows/edit.json、tests/gpu/test_edit.py、tests/fixtures/edit/。
採固定SFT與Edit LoRA，核對雙編碼節點edit_format；四格均可預覽、替換和移除，空槽重排須先確認新圖號。圖片等比預處理並保存transform，單GPU編碼後卸載。LLM輸出若有必須Streaming。
執行AC-08，1/2/4圖各3例、交換順序、空槽、超長輸入與四圖資源測試；DoD為圖號/主圖比例正確、修改有效且四圖無OOM。
回報圖例、設定、命令、未通過項目及DEVNOTE。
```

風險／回滾：四圖過載可降低參考前處理尺寸並標示，不能無聲丟圖；停用 Edit 不影響 T2I。

### Stage 5：完成筆刷重繪與原圖保護

目標：可檢查的遮罩、局部修改與柔邊外像素保留。前置：Stage 4；ImageEditor adapter 已驗證。

**Codex Instructions**

```text
直接貼給Codex；完成masked inpaint，不宣稱專用訓練模型或接縫保證。
檔案：ui/inpaint_tab.py、ui/editor_adapter.py、domain/masks.py、workflows/inpaint.json、tests/unit/test_masks.py、tests/gpu/test_inpaint.py。
從實際ImageEditor layers alpha建立白改黑留遮罩；EXIF校正與圖/遮罩共用等比變換。實作edge_softness0.15映射、有限距離柔邊、latent mask、denoise與最終原圖合成；空遮罩阻擋，全白確認。可選LLM文字輸出必須Streaming。
測AC-09及5個局部品質案例，含黑筆/白筆、極窄筆畫、非正方、透明圖、denoise1；柔邊支撐區外逐像素一致。
DoD：遮罩方向/對齊/合成全通過且修改生效，品質失敗不可只用像素測試掩蓋。
輸出差分圖、遮罩、案例評分、命令與DEVNOTE。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，依CLAUDE.md完成筆刷重繪垂直切片。
修改ui/inpaint_tab.py、ui/editor_adapter.py、domain/masks.py、workflows/inpaint.json、tests/unit/test_masks.py及tests/gpu/test_inpaint.py。
讀固定ImageEditor結構，僅由繪畫圖層alpha取mask；圖與mask共用等比座標。實作柔邊0.15產品映射、latent連接、denoise、遮罩預覽/反轉/清除及最終合成保護。若加入LLM文字功能必須Streaming。
跑AC-09和5個局部案例，覆蓋黑白筆、非正方、窄選區、全白/全黑與denoise1。DoD為柔邊外像素不變、選區確實修改且對齊，保留自然度失敗證據。
輸出差分、測試、限制與DEVNOTE。
```

風險／回滾：latent mask 不相容先阻擋重繪；合成不自然須修 workflow，不只擴大羽化掩蓋。

### Stage 6：完成視覺參考與色彩深度控制

目標：證明參考／控制訊號真的生效。前置：Stage 5、相容視覺編碼與控制權重。

**Codex Instructions**

```text
直接貼給Codex，遵守AGENTS.md；將vision與color_depth分成子模式，不加骨架姿勢或光學景深功能。
檔案：ui/control_tab.py、services/preprocessors.py、workflows/{vision,color_depth}.json、configs/capabilities.json、tests/gpu/test_controls.py。
優先原生路徑；需要外掛則固定ThetaCursed repo commit與license。測int8/fp8/bf16的視覺相容性，未測不開選項。提供參考圖、影響強度、深度/輪廓/色塊預覽與替換；MoGe前處理後卸載；只有接入的控制圖標已套用。LLM若輸出說明必須Streaming。
執行AC-10/11，含參考開關、控制adapter開關、強度對照各5例與資源量測。
DoD：每必要子模式至少4/5例通過固定特徵評分，無文字退化冒充vision，證據可追溯。
輸出圖組、矩陣、命令、風險與DEVNOTE。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，依CLAUDE.md完成視覺條件與色彩/深度控制。
新增ui/control_tab.py、services/preprocessors.py、workflows/vision.json與color_depth.json、tests/gpu/test_controls.py，更新configs/capabilities.json。
兩子模式分開；檢查精度相容性，必要外掛固定commit/授權。實作來源/處理圖等比預覽、參考強度、深度方向、控制結束比例與色塊圖替換；幾何估計先完成再卸載。任何LLM說明輸出必須Streaming。
以AC-10/11的開關對照各5例驗證，量資源，不能以能產圖就判定控制有效。DoD為各必要模式≥4/5例符合預定特徵，未支援FP8明確停用。
輸出對照圖、能力矩陣、測試與DEVNOTE。
```

風險／回滾：外掛破壞原生節點則移除該外掛並保留 blocked 原因；色塊自動提取未通過時需補測，不假裝已啟用。

### Stage 7：完成模型管理、熱切換與 2K 路徑

目標：安全管理模型並完成高負載驗收。前置：Stage 6；SFT、Base 與所選 LoRA。

**Codex Instructions**

```text
直接貼給Codex；依AGENTS.md完成模型頁，不建立任意腳本安裝器。
檔案：ui/models_tab.py、services/downloads.py、services/resources.py、domain/model_registry.py、configs/models.lock.json、tests/integration/test_downloads.py、tests/gpu/test_switch_2k.py。
實作HF/Civitai精確版本解析、Secrets、https/redirect/IP白名單、part下載/hash/atomic rename、大小與授權資訊；只接受safetensors。交易式切換、busy屏障、LoRA相容矩陣、使用中檔案不可刪、RAM LRU。LLM文字若有必須Streaming。
測AC-12/13/14/17：2048²三次、主幹雙向各三次、下載故障、惡意URL、token遮罩及不相容組合。
DoD：2K真實完成而非插值冒充，切換失敗可恢復，管理CRUD與下載校驗全通過。
輸出benchmark、切換紀錄、測試與DEVNOTE；不足明確blocked。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，遵守CLAUDE.md完成模型/LoRA管理及2048²生成。
修改ui/models_tab.py、services/downloads.py與resources.py、domain/model_registry.py、configs/models.lock.json、tests/integration/test_downloads.py、tests/gpu/test_switch_2k.py。
實作provider版本解析、Secret隱藏、下載白名單/重新導向檢查、part與hash、原子ready登錄、交易切換、LRU、相容矩陣及刪除保護。選用LLM若有輸出必須Streaming。
跑AC-12/13/14/17，真實2048²連續3次、SFT/Base雙向各3次，含忙碌、失敗恢復與惡意URL。DoD為資源報告與管理CRUD通過，不用分段放大替代原生2K驗收。
輸出測試、相容限制、回滾點與DEVNOTE。
```

風險／回滾：模型切換回最後 ready artifact；2K失敗保留原生項目 blocked，替代放大另提，不自動縮圖。

### Stage 8：完成專案續編、匯出與工作恢復

目標：成果與創作狀態能在新執行階段復原。前置：Stage 7。

**Codex Instructions**

```text
直接貼給Codex；依AGENTS.md完成project生命週期，不預設掛Drive。
檔案：storage/archive.py、storage/projects.py、storage/ledger.py、ui/project_menu.py、tests/integration/test_project_roundtrip.py、docs/project-format.md。
實作新建/改名/刪除/重置、500ms草稿保存、CAS、ZIP manifest/hash與大小/路徑/壓縮比驗證、匯入新id、輸入/框/mask/結果續編。工作依client_request_id去重，斷線查原job，重啟對帳history。匯出排除secret與權重；LLM輸出如有必須Streaming並可找回最終文字。
跑AC-15/16/17，含新VM匯入、兩視窗衝突、zip slip/bomb、保存失敗、取消及重連。
DoD：所有素材/設定hash roundtrip一致，無重複生成或虛假已保存狀態。
輸出格式文件、測試證據、限制與DEVNOTE。
```

**Claude Code Instructions**

```text
直接貼給Claude Code並遵守CLAUDE.md。完成可續編專案與工作恢復，Drive維持選用。
修改storage/archive.py、projects.py、ledger.py、ui/project_menu.py、tests/integration/test_project_roundtrip.py與docs/project-format.md。
實作CRUD/重置、debounce保存、revision CAS、ZIP驗證與新專案匯入、排除secret/權重；保存所有分頁輸入/框/遮罩/輸出。依request id去重，重連/重啟對帳，不重送；若有LLM文字必須Streaming且保留最終結果。
測AC-15/16/17，包含新環境roundtrip、衝突、惡意ZIP、保存失敗與取消。DoD為資產/設定hash一致且無重複工作，明確區分本地保存與外部匯出。
輸出測試、格式說明與DEVNOTE。
```

風險／回滾：遷移前保留原專案，匯入 staging 失敗全部清理；不改舊匯出包。

### Stage 9：補齊整合、回歸、邊界與品質測試

目標：作為倒數第二階段完成全案放行證據。前置：Stage 0～8 DoD 已通過或明確列阻礙；blocked 必要功能不得略過。

**Codex Instructions**

```text
直接貼給Codex，依AGENTS.md進行完整驗收；不新增產品功能或改低門檻。
檔案：tests/{integration,gpu}/、tests/fixtures/、docs/acceptance-report.md、docs/benchmarks.md、configs/capabilities.json。
固定品質評測集與三項特徵後再跑；執行AC-01～18、CPU/GPU、登入資產、通道、取消/重連/OOM、2K/四圖、ZIP與LoRA回歸；可選LLM必須Streaming並測中斷。清理測試暫存，保留必要證據。
DoD：所有必要AC有環境/版本/hash/命令/結果與完整失敗例；各類品質達80%；無阻擋才標產品可放行。任何未跑或失敗均不得以人工checklist覆蓋。
輸出PASS/FAIL/BLOCKED矩陣、風險、最小修正建議與DEVNOTE；不部署。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，遵守CLAUDE.md；本階段是整合與回歸gate，不擴充功能。
更新tests/integration、tests/gpu、tests/fixtures、docs/acceptance-report.md與benchmarks.md、configs/capabilities.json。
先固定評測素材/評分，再在乾淨L4完成AC-01～18，含五tab、認證/通道、取消/重連、故障注入、四圖、原生2K、模型切換與匯出入。任何LLM文字必須Streaming，測中途斷線；保留失敗例並清測試暫存。
DoD為必要AC全有實測證據、品質各類≥80%、無未跑gate；否則明確FAIL/BLOCKED，不以UI可開啟代替驗收。
回報矩陣、命令、資源、風險與DEVNOTE，不擅自部署。
```

風險／回滾：回到最後通過的 runtime／model／workflow lock；問題修復後僅重跑受影響案例及必要回歸，不能刪失敗證據。

### Stage 10：完成文件化與正式交付

目標：提供可自行啟動、操作與維護的交付包。前置：Stage 9 產品放行，否則只可交付明確標示未完成的開發包。

**Codex Instructions**

```text
直接貼給Codex並遵守AGENTS.md；只整理交付，不新增未測功能、不自行對外部署或付費。
檔案：README.md、docs/{setup,user-guide,troubleshooting,compatibility,privacy,acceptance-report}.md、notebooks/MOSS_Image_Colab.ipynb、DEVNOTE.md、交付manifest。
整理一鍵Colab啟動、選GPU、Secrets/通道設定、五分頁教學、專案保存與VM回收限制、取消/清理、版本升級/回滾與已知問題。明示8步/2K/vision實測範圍；若有LLM功能文件明寫Streaming。交付原始碼與鎖檔，不包權重或secret。
測試：依README在乾淨L4重演啟動與一條完整創作/匯出/恢復路徑，檢查Notebook無token或私有輸出；驗證來源/授權及檔案連結。
DoD：Stage9全通過、教學可重演、交付manifest完整；清本任務暫存但不刪使用者成果。
輸出交付清單、實測報告、使用限制及DEVNOTE最終快照。
```

**Claude Code Instructions**

```text
直接貼給Claude Code，遵守CLAUDE.md；完成交付文件，不擅自公開、部署或購買服務。
修改README.md、docs/setup.md、user-guide.md、troubleshooting.md、compatibility.md、privacy.md、acceptance-report.md、notebooks/MOSS_Image_Colab.ipynb、DEVNOTE.md及交付manifest。
涵蓋Colab啟動、設備/Secrets/入口設定、五tab教學、匯出續編、VM回收、關機清理、升級回滾與已測限制。若有LLM文字功能明寫Streaming。排除模型權重/secret，保留固定版本和授權。
按文件在乾淨L4重跑啟動、創作、匯出、恢復；檢查Notebook敏感輸出與連結。DoD為Stage9全通過、使用文件可重演及交付manifest齊全；阻礙存在則只交未完成開發包。
輸出清單、測試結果、限制、回滾點與DEVNOTE；移除本任務暫存且保留成果。
```

風險／回滾：文件與實際行為衝突須修程式或文件並重驗，不能美化能力；保存最後通過的完整 lock 及驗收報告作回復版本。


### 規格文件交付檢查

2026-11-07 實際完成：三份交付章節與順序檢查 PASS；11 個階段各含 Codex／Claude Code 指令及 Streaming 規則 PASS；18 個驗收 ID 覆蓋 PASS；2 個 JSON 範例解析 PASS；3 個 SVG 的 XML 與 viewBox 檢查 PASS；以 `spec-organizer/scripts/check_plain_language.py` 檢查白話版 PASS。檢查過程的暫存文字檔已移除。

上述為規格文件檢查。未執行 Colab、GPU、Gradio 瀏覽器、模型下載或 Cloudflare 端到端測試；沒有已部署的應用程式，也沒有產品 PASS 報告。產品放行仍須依 Stage 9 的 AC-01～AC-18 實測。
