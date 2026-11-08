# Stage 9：整合與回歸（2026-11-08）

所有 GPU 驗收都在 Colab L4（NVIDIA L4、driver 580.82.07、Python 3.13.16、ComfyUI 0.44.0 `1332fab`）執行。
使用者選擇精簡批次 E：補齊缺的項目，其餘沿用今天在同一分支上跑的批次 A～D。

| AC | 狀態 | 依據 |
|---|---|---|
| AC-01 安裝、重跑不重複 | **PASS** | [批次 E](../evidence/stage9-batch-e/README.md)：引擎與工作台沿用、權重未重下載 |
| AC-02 未登入一律拒絕 | **PASS** | 批次 E 在 L4 上跑契約測試：未登入時 API、素材、靜態檔、Gradio 設定與上傳端點皆 401，另驗 CSRF 與 Origin；Stage 1 通道實測 |
| AC-03 通道完整流程 | **PASS** | [通道實測](../evidence/stage9-ac03/README.md)：一次性連結登入、上傳、生成與進度、取消、重新整理後接回、下載都經 Cloudflare 通道完成；只用 HTTP 輪詢，無 SSE |
| AC-04 quality50 基準 | **PASS** | [批次 A](../evidence/stage2-batch-a/README.md) p50 111.5 秒；批次 E 的 AC-18 以同設定 5 次成功 |
| AC-05 排版座標 | **PASS** | 契約測試（L4 上 214 項全過） |
| AC-06 fast8 | **PASS** | [批次 B](../evidence/stage3-batch-b/README.md)；批次 E 重測 10.4～10.5 秒 |
| AC-07 profile 與 graph 一致 | **PASS** | 契約測試 |
| AC-08 多圖修圖 | **有條件通過** | [批次 C](../evidence/stage4-6-batch-c/README.md)：1～2 張 6/6；3～4 張 0/3，使用者接受限制，介面標為實驗 |
| AC-09 筆刷重繪 | **PASS** | 批次 C：柔邊外逐像素保留 5/5；強度 1.0 時要求的物件出現 4/5 |
| AC-10 視覺參考（實驗） | **已記錄** | 批次 C：開／關 5 例都明顯不同；傾向照抄參考圖 |
| AC-11 色彩／深度控制 | **有條件通過** | 批次 C：深度 5/5；輪廓（MoGe mask）在棚拍背景 0/5，介面預設改深度 |
| AC-12 高解析 | **PASS** | [批次 D](../evidence/stage7-8-batch-d/README.md)：原生 1456² 3/3、分段放大 2048² 3/3 |
| AC-13 主模型切換 | **PASS** | 批次 D：3 輪切換、忙碌阻擋、失敗回復 |
| AC-14 相容性攔截 | **PASS** | 批次 D：10 種組合全數攔截；忙碌時刪除使用中檔案被擋 |
| AC-15 專案匯出入 | **PASS** | 批次 D：新 VM 匯入後 hash 與草稿一致、續編成功 |
| AC-16 重複提交與故障 | **PASS** | 契約測試：並行重複提交只建一個工作、取消不會回報成功、只取消指定工作、引擎狀態不明時封鎖後續工作；批次腳本重跑時以相同 request id 取回原工作 |
| AC-17 邊界 | **PASS** | 契約測試：惡意或不一致的專案 ZIP、zip bomb、符號連結、超大或動態圖檔、上傳大小上限、未鎖定的下載來源 |
| AC-18 品質 | **PASS** | 一般生成 5/5（批次 E）、重繪 4/5（批次 C 重測） |
| AC-19 繁中排版（決策關卡） | **結案** | 批次 A 7/10，使用者接受限制，介面與 README 已提醒 |
| AC-20 原生 2048²（實驗） | **3/3 成功** | 批次 D：約 608 秒、峰值 20.4 GB |

規格要求「所有必要 AC 為 PASS」才算發布。目前必要 AC 中只有 AC-08 與 AC-11 為有條件通過（使用者已接受限制），
所以仍是開發版，不是正式發布。

## 本階段找到並修正的問題

- 真引擎的 `object_info` 驗證：`LoadImage` 列舉只含既有輸入檔、`TextEncodeMOSSImageEdit.images` 為 autogrow；
  新增 `scripts/engine_preflight.py` 在開跑前檢查 11 種圖。
- 多圖修圖參考圖改為圖 1 1 MP、其餘 0.25 MP；重繪預設強度 1.0；控制預設深度。
- 批次 E 的 preflight 需要先下載所有模型。
