# MOSS-Image Colab Studio

先讀 DEVNOTE.md、todo.md、specs/requirements.md。以規格 Stage 0–10 與 AC-01–18 為準。
採方案 A：Python、Colab、ComfyUI loopback、Gradio 五分頁。一次一個 GPU 工作。
不可把 CPU/mock 測試當成 GPU、畫質或通道通過。未通過必要 gate 不進下一依賴階段。
不追蹤浮動 latest、不提交權重、token、私人圖片或 Notebook 輸出。
執行中的 JobSpec 是不可變快照；專案保存採 revision CAS、原子 JSON；ledger 用 SQLite。
UI 唯一主任務是把創作意圖與素材變成可保存圖片。task model：編輯→驗證→提交→結果。
state model 依規格 empty/editing/validating/submitted/running/resolved/blocked/reconnecting。
首屏最多三組：必要輸入/畫布、結果、窄狀態列，當前分頁一個主 CTA。
content audit：輸入為 must-see-now；下載為 next-step-only；錯誤為 error-only；
JSON/採樣進階為 on-demand-reference；歷史與診斷為 keep-off-first-viewport。
進階設定現在隱藏因一般流程不需、點展開才以 accordion 顯示；診斷僅出錯或點查詢才顯示。
模型管理低頻置獨立 tab，不在創作首屏堆疊卡片。空狀態須指引下一步。
各層責任：domain 驗證；storage 持久化；services 調度；adapters 外部協定；ui 呈現。
每階段完成跑 pytest/ruff、更新 evidence/DEVNOTE/todo；有實際阻礙保留證據。
若加入 LLM 文字輸出必須 Streaming。不要建立假內容篩選開關或規避平台限制。
完成後清除本次測試暫存，不刪使用者成果。使用者已授權推送至指定公開 GitHub 倉庫。
