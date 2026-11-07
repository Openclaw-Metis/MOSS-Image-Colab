# MOSS-Image-Colab
目標是在 Google Colab 以 ComfyUI 無頭引擎與 Gradio 五分頁執行 MOSS-Image。

**開發中，尚非已驗收的完整生圖工具。** 依 [規格 v1.3.0](specs/requirements.md)：Stage 0、1 已 PASS；
Stage 2～8 程式完成，但 GPU 驗收批次尚未執行，未跑的項目不算通過。進度見 [todo.md](todo.md)。

五分頁：文生圖與排版（精細 50 步／加速 8 步、拉框含人物框）、多圖指令修圖（1～4 張）、筆刷局部重繪、
視覺與深度控制（色彩／深度；視覺參考為實驗）、模型與高解析（固定清單下載、主模型切換、分段放大）。
專案可匯出成 ZIP，在新的 Colab 匯入續編。

**已知限制（繁中字形）**：GPU 批次 A 實測 10 張繁中排版海報，7 張文字全對、3 張出錯
（「週」寫成「周」、「鬱金香」寫成「鬱花香」、框描述的「橘棕色」被寫進標題），未達規格 8/10 門檻。
請逐字檢查成品；框描述避免寫可能被畫成文字的詞，重要標題可改用後製加字。
詳見 [批次 A 證據](docs/evidence/stage2-batch-a/README.md)。

**使用限制**：不得以真人照片製作換臉、私密或冒用他人身分的內容（Colab 對所有執行環境禁止 deepfakes）。

怎麼用：見 [使用說明](docs/user-guide.md)（啟動、五個分頁、專案、結束、疑難排解、隱私）。

開發檢查（Linux／macOS）：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e ".[ui]"
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
```

Windows 用 `.venv\Scripts\python.exe` 執行相同指令；依賴 Linux `/proc` 或符號連結權限的測試會在 Windows 跳過。

不接 GPU 檢查介面（假引擎，產生標明「非模型輸出」的佔位圖，不能當成 GPU 或畫質證據）：

```bash
python scripts/dev_server.py --data-root .runtime/dev --port 7861
```

證據：[Stage 0](docs/stages/stage0.md)、[Stage 1](docs/stages/stage1.md)、[Stage 2](docs/stages/stage2.md)、
[Stage 3～8](docs/stages/stage3-8.md)、[相容性](docs/compatibility.md)。

模型權重、使用者素材與憑證不入版控。`docs/evidence/` 僅保留本專案測試生成的範例與驗證紀錄。
Colab VM 回收會失去本地資料；請下載作品，或用專案選單匯出專案 ZIP。
