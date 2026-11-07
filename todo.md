# 開發清單（規格 v1.3.0）

「程式完成」＝CPU 測試、lint、假引擎 UI 檢查通過；「PASS」＝對應 GPU 批次在 L4 實跑通過並取回證據。

- [x] Stage 0：領域契約、原子 JSON、CAS、SQLite ledger。PASS；v1.3 加 Windows CPU 測試路徑。
- [x] Stage 1：固定環境、權重校驗、text/edit/vision 載入、認證通道端到端。PASS。
- [x] Stage 2：文生圖與排版。PASS（2026-11-07 批次 A：AC-04 通過；AC-19 7/10 未達門檻，使用者接受限制，介面已提醒）。
- [x] Stage 3：fast8 與 VRAM 模式。PASS（2026-11-07 批次 B：AC-06 通過，8 步約 10.5 秒；VRAM 改為 auto）。
- [ ] Stage 4：1～4 圖指令修圖。程式完成；**AC-08** 已寫入批次 C 腳本（1／2／4 圖各 3 例，素材由 fast8 現場生成），待 GPU 實跑。
- [ ] Stage 5：筆刷重繪。程式完成；**GPU 批次 C** 待跑（AC-09 品質）。
- [ ] Stage 6：色彩／深度＋視覺參考（實驗）。程式完成；**GPU 批次 C** 待跑（AC-11、AC-10）。MoGe 估計圖預覽已完成。
- [ ] Stage 7：模型管理與分段放大。程式完成（含刪除檔案與使用中阻擋、自加 HF LoRA）；**GPU 批次 D** 待跑（AC-12～14、AC-20）。
- [ ] Stage 8：專案 ZIP 匯出入。程式完成；**GPU 批次 D** 待跑（AC-15 新 VM 續編）。
- [ ] Stage 9：GPU 批次 E，AC-01～19 全面回歸與 AC-18 品質評分。
- [ ] Stage 10：乾淨 L4 重演、正式交付文件。

批次 C／D 腳本：`scripts/batch_c_eval.py`、`scripts/batch_d_eval.py`（共用 `batch_runner.py`，每例檢查點、重跑不重送）；
Notebook 第 7～9 格執行，皆已用假引擎試跑。AC-15 第二段需在新的 Colab 工作階段上傳匯出檔。

Notebook 從 GitHub `main` 取程式；本機修改需推送後，Colab 才會用到（第 1 格可填分支名稱）。
