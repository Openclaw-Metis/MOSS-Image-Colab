# 開發清單（規格 v1.3.0）

「程式完成」＝CPU 測試、lint、假引擎 UI 檢查通過；「PASS」＝對應 GPU 批次在 L4 實跑通過並取回證據。

- [x] Stage 0：領域契約、原子 JSON、CAS、SQLite ledger。PASS；v1.3 加 Windows CPU 測試路徑。
- [x] Stage 1：固定環境、權重校驗、text/edit/vision 載入、認證通道端到端。PASS。
- [x] Stage 2：文生圖與排版。PASS（2026-11-07 批次 A：AC-04 通過；AC-19 7/10 未達門檻，使用者接受限制，介面已提醒）。
- [x] Stage 3：fast8 與 VRAM 模式。PASS（2026-11-07 批次 B：AC-06 通過，8 步約 10.5 秒；VRAM 改為 auto）。
- [x] Stage 4：指令修圖。有條件通過（2026-11-08 批次 C：1～2 張 6/6；3～4 張 0/3，使用者接受限制，介面標為實驗）。
- [x] Stage 5：筆刷重繪。PASS（批次 C：柔邊外逐像素保留 5/5；強度 1.0 時要求的物件出現 4/5）。
- [x] Stage 6：色彩／深度＋視覺參考（實驗）。有條件通過（深度 5/5；輪廓在棚拍背景無效，預設改深度）。
- [x] Stage 7：模型管理與分段放大。PASS（批次 D：AC-12、13、14；AC-20 實驗 3/3）；自加 HF LoRA 未做 GPU 實測。
- [x] Stage 8：專案 ZIP 匯出入。PASS（AC-15 新 VM 匯入 hash 與草稿一致、續編成功）。
- [x] Stage 9：精簡批次 E（使用者 2026-11-08 選擇）：AC-01、preflight、VM 上契約測試、AC-06、AC-18 一般生成；其餘沿用批次 A～D。
  AC-03 通道實測通過。總表見 docs/stages/stage9.md。
- [x] Stage 10：交付文件完成；使用者 2026-11-08 依 README 在乾淨 L4 重演，回報正常（docs/stages/stage10.md）。
  仍是開發版（AC-08、AC-11 有條件通過）；自加 HF LoRA 沒有 GPU 實測。

- [ ] UI／UX 優化與範例（2026-11-11）：程式完成（CPU 測試、lint、假引擎瀏覽器流程）。尚未在 L4 經通道實際操作；
  下次開 Colab 時順手走一遍五分頁與「接著做」。

GPU 批次腳本：`scripts/batch_c_eval.py`、`batch_d_eval.py`、`batch_e_eval.py`（共用 `batch_runner.py`，每例檢查點、重跑不重送），
開跑前先在 VM 跑 `scripts/engine_preflight.py`。Notebook 第 7～10 格；AC-15 第二段需在新的 Colab 工作階段上傳匯出檔（第 9 格）。

Notebook 從 GitHub `main` 取程式；本機修改需推送後，Colab 才會用到（第 1 格可填分支名稱）。
