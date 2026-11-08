# Stage 3～8：開發與驗收紀錄（規格 v1.3.0）

狀態（2026-11-08 更新，GPU 批次 C、D 已在 Colab L4 執行）：

| 階段 | 狀態 | 依據 |
|---|---|---|
| 3 | **PASS** | 批次 B：AC-06、VRAM 改 auto（[stage3-batch-b](../evidence/stage3-batch-b/README.md)） |
| 4 | **有條件通過** | AC-08 1 張 3/3、2 張 3/3；3～4 張在 1／0.25／0.5 MP 都 0/3，使用者 2026-11-08 接受限制，介面標為實驗 |
| 5 | **PASS** | AC-09 柔邊外逐像素保留 5/5；重繪強度 1.0 時要求的物件出現 4/5 |
| 6 | **有條件通過** | AC-11 深度 5/5 保留幾何；輪廓（MoGe mask）在棚拍背景 0/5，介面預設改深度並說明；AC-10（實驗）已記錄 |
| 7 | **PASS** | AC-12、AC-13、AC-14 通過；AC-20 原生 2048²（實驗）3/3；自加 HF LoRA 未做 GPU 實測 |
| 8 | **PASS** | AC-15 在新 VM 匯入後 hash 與草稿一致、續編成功 |

證據：[批次 C](../evidence/stage4-6-batch-c/README.md)（含兩次重測）、[批次 D 與 AC-15](../evidence/stage7-8-batch-d/README.md)。
驗證環境：Windows 11、Python 3.13.15、Gradio 6.31.0；CPU 測試 212 passed、7 skipped；ruff 通過。
瀏覽器檢查一律使用 `scripts/dev_server.py` 假引擎，只證明 UI 與 API 串接。

| 階段 | 已實作 | CPU／假引擎證據 | 待 GPU 驗收 | 已知缺口 |
|---|---|---|---|---|
| 3 加速 8 步、VRAM 模式 | `fast8_v1`（DMD `lora_latest` 0.7、8 步、CFG 1、無 SLG、只限 SFT）；profile 登錄；負向詞與 fast8 衝突時拒絕而非忽略；`engine_vram_mode`（lowvram／auto／highvram） | graph 契約與切換無殘留（AC-07 CPU 部分）；瀏覽器：fast8 帶負向詞被擋、清空後 8/8 步 | 批次 B：auto 與 lowvram 對照、AC-06 | VRAM 預設仍是 lowvram，待實測再改 |
| 4 多圖修圖 | 上傳 API（串流、20 MiB 上限、不留檔名）；Edit graph 依官方範本（30 步、CFG 4、euler/normal、SLG 22 全程、圖 1 縮 1 MP／16 px 決定尺寸）；參考圖以 UUID 名稱送入引擎；分頁草稿分開保存 | 尺寸算式與 ComfyUI `ImageScaleToTotalPixels` 一致；正負編碼器同圖同序；跨專案素材被拒；上傳失敗不封鎖 GPU；瀏覽器：空格要求確認重新編號、30/30 步、輸出跟隨圖 1 | 批次 C：AC-08（見上表） | 3～4 張未通過（實驗）；圖 2～4 縮到 0.25 MP；Edit-HQ 對照未做（選用） |
| 5 筆刷重繪 | 自訂 Canvas（筆刷、橡皮擦、復原、清除、反轉、黑白預覽）；遮罩以工作尺寸上傳；`SetLatentNoiseMask`；有限寬度柔邊；後端合成 | 柔邊外逐像素等於原圖、遮罩方向、黑白筆、空／全白路徑；瀏覽器：空遮罩被擋、拖曳塗抹、未塗抹角落保留原色 | 批次 C：AC-09（見上表） | 預設強度改 1.0；窄框純色背景仍可能畫不出物件；Edit-HQ 對照未做 |
| 6 色彩／深度、視覺參考 | Control graph 依官方範本（MoGe 3 → MoGeRender → MOSSImageControl＋控制 LoRA、TSR、SLG 24、25 步 er_sde）；自備深度圖／色塊圖（色塊最近鄰縮放）；視覺參考（實驗）走無 VAE 的原生節點 | graph 契約、參數邊界、色塊縮放後只剩原色；瀏覽器：兩個子模式都能產生 | 批次 C：AC-11、AC-10（見上表） | 輪廓模式在棚拍背景無效；深度會帶入身形；取樣器用 KSampler `er_sde`，與範本 s_noise 1.05 有差 |
| 7 模型管理、高解析 | 固定清單狀態與背景下載（不佔 GPU 鎖）、SFT↔Base 切換（工作中與未下載時拒絕）；分段放大（每段 ≤1.5 倍、16 px、最大 2048²） | 切換屏障、非清單來源拒絕、段數與節點串接；瀏覽器：模型表、開發伺服器拒絕真實下載、1024×1536→1360×2048 | 批次 D：AC-12、AC-13、AC-14、AC-20（見上表） | 自加 HF LoRA 已實作但未做 GPU 實測 |
| 8 專案匯出入 | ZIP（manifest、project、assets）；匯入驗證檔名、符號連結、重名、壓縮比、單檔與總量、hash；一律新 id；專案選單切換／匯出／匯入 | round-trip hash 一致；7 種惡意或不一致檔案被拒且無殘留；瀏覽器：匯出→匯入→開啟新專案帶回草稿 | 批次 D：AC-15（見上表） | 工作歷史不隨專案匯入（設計如此） |

## 測試穩定性

全套測試在 Windows 上曾間歇失敗（`test_saved_result…`、`test_queue_bound…`）。實際原因：Windows 不允許
讀取正被另一執行緒 `os.replace` 的檔案（反之亦然），會丟 `PermissionError`；Linux 沒有此限制。
`storage/atomic.py` 的 Windows 分支改為對開檔與 replace 短暫重試後，連跑 6 次全部通過。先前推測的
`LK_LOCK` 1 秒重試只是次要因素（也已改為非阻塞輪詢）。POSIX 路徑不受影響。

## 回滾

各階段可單獨停用：移除對應分頁與 profile，不影響已通過的 T2I。資料格式仍為 schema v1；
匯出包加入 `format`／`schema_version`，舊版程式不會誤讀。
