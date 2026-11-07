# MOSS-Image-Colab
目標是在 Google Colab 以 ComfyUI 無頭引擎與 Gradio 五分頁執行 MOSS-Image。

**開發中，尚非可用的完整生圖工具。** Stage 0、Stage 1 已完成；Stage 2 實作中。
五分頁、模型與通道必須依 [原始規格](specs/requirements.md) 驗收，未跑項目不算通過。

開發檢查：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e .
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

進度見 [todo.md](todo.md)、[DEVNOTE.md](DEVNOTE.md) 與 [Stage 0 證據](docs/stages/stage0.md)。
[Stage 1 證據](docs/stages/stage1.md) 包含真實 L4、登入、上傳、取消、重連與下載結果。
[Stage 2 進度與限制](docs/stages/stage2.md) 記錄正式工作台實測及尚未完成的 GPU 驗收。
目前本地驗證為 110 項通過、4 項 GPU 測試跳過；不代表全功能已驗收。

模型權重、使用者素材與憑證不入版控。`docs/evidence/` 僅保留本專案測試生成的範例與驗證紀錄。
Colab VM 回收會失去本地資料；專案 ZIP 續編仍待後續階段完成。
