# 開發清單（規格 v1.3.0）

「程式完成」＝CPU 測試、lint、假引擎 UI 檢查通過；「PASS」＝對應 GPU 批次在 L4 實跑通過並取回證據。

- [x] Stage 0：領域契約、原子 JSON、CAS、SQLite ledger。PASS；v1.3 加 Windows CPU 測試路徑。
- [x] Stage 1：固定環境、權重校驗、text/edit/vision 載入、認證通道端到端。PASS。
- [ ] Stage 2：文生圖與排版。程式完成；**GPU 批次 A** 待跑（AC-04 五筆、排版下載、AC-19 繁中 10 例）。
- [ ] Stage 3：fast8 與 VRAM 模式。程式完成；**GPU 批次 B** 待跑（VRAM 對照、AC-06）。
- [ ] Stage 4：1～4 圖指令修圖。程式完成；**GPU 批次 B** 待跑（AC-08）。
- [ ] Stage 5：筆刷重繪。程式完成；**GPU 批次 C** 待跑（AC-09 品質）。
- [ ] Stage 6：色彩／深度＋視覺參考（實驗）。程式完成；**GPU 批次 C** 待跑（AC-11、AC-10）。缺 MoGe 估計圖預覽。
- [ ] Stage 7：模型管理與分段放大。程式完成（缺使用者自加 HF LoRA）；**GPU 批次 D** 待跑（AC-12～14、AC-20）。
- [ ] Stage 8：專案 ZIP 匯出入。程式完成；**GPU 批次 D** 待跑（AC-15 新 VM 續編）。
- [ ] Stage 9：GPU 批次 E，AC-01～19 全面回歸與 AC-18 品質評分。
- [ ] Stage 10：乾淨 L4 重演、正式交付文件。

Notebook 從 GitHub `main` 取程式；本機修改需推送後，Colab 才會用到。
