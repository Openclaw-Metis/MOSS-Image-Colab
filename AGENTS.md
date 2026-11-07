# MOSS-Image Colab Studio

先讀 DEVNOTE.md、todo.md、specs/requirements.md（v1.3.0）。以規格 Stage 0–10 與 AC-01–20 為準。
採方案 A：Python、Colab、ComfyUI loopback、Gradio 五分頁。一次一個 GPU 工作。
不可把 CPU/mock/假引擎測試當成 GPU、畫質或通道通過。
階段推進：前一階段「程式完成」（CPU DoD 通過）即可開發下一階段；標 PASS 須其 GPU 批次在 L4 實跑通過並取回證據。
GPU 批次集中在同一 Colab 工作階段執行，每項完成就把報告與圖檔拉回 docs/evidence/。
不追蹤浮動 latest、不提交權重、token、私人圖片或 Notebook 輸出。
執行中的 JobSpec 是不可變快照；專案保存採 revision CAS、原子 JSON；ledger 用 SQLite。
Gradio 只做外殼：所有 callback 為 client-only（fn=None），生成、上傳、查詢走需登入的同源 HTTP，不依賴 SSE。
UI 唯一主任務是把創作意圖與素材變成可保存圖片。task model：編輯→驗證→提交→結果。
state model 依規格 empty/editing/validating/submitted/running/resolved/blocked/reconnecting。
首屏最多三組：必要輸入/畫布、結果、窄狀態列，當前分頁一個主 CTA。
content audit：輸入為 must-see-now；下載為 next-step-only；錯誤為 error-only；
JSON/採樣進階為 on-demand-reference；歷史與診斷為 keep-off-first-viewport。
實驗能力（視覺參考、原生 2048²）須在介面標示「實驗」，不阻擋發布。
修圖與控制分頁顯示使用限制：不得以真人照片做換臉、私密或冒名內容。
各層責任：domain 驗證；storage 持久化；services 調度；adapters 外部協定；ui 呈現。
CPU 測試須能在 Linux 與 Windows 執行；Windows 分支不得改變 POSIX 行為。
每階段完成跑 pytest/ruff、更新 evidence/DEVNOTE/todo；有實際阻礙保留證據。
若加入 LLM 文字輸出必須 Streaming。不要建立假內容篩選開關或規避平台限制。
完成後清除本次測試暫存，不刪使用者成果。使用者已授權推送至指定公開 GitHub 倉庫。
