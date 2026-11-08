# Stage 10：文件與交付（2026-11-08）

規格要求 README、操作說明、疑難排解、相容性、隱私與使用限制，並依 README 在乾淨 L4 重演一次完整流程。
Stage 9 沒有全部 PASS（AC-08、AC-11 有條件通過），所以只交付標明為開發版的版本。

| 交付物 | 位置 | 狀態 |
|---|---|---|
| README（開啟方式、狀態、已知限制、開發檢查） | `README.md` | 完成，標明開發中 |
| 操作說明（啟動、五分頁、耗時、專案、結束） | `docs/user-guide.md` | 完成，已依 GPU 實測更新修圖、重繪、控制的建議用法 |
| 疑難排解 | `docs/user-guide.md`「疑難排解」 | 完成 |
| 隱私與使用限制 | `docs/user-guide.md`「隱私與使用限制」、README | 完成 |
| 相容性 | `docs/compatibility.md` | 完成，含 GPU 驗收後的參數調整 |
| 驗收證據 | `docs/stages/stage9.md` 與 `docs/evidence/` | 完成 |
| 依 README 在乾淨 L4 重演 | 本頁「乾淨 L4 重演」 | 完成（使用者自行操作並回報正常） |

## 乾淨 L4 重演

2026-11-08，[PR #2](https://github.com/Openclaw-Metis/MOSS-Image-Colab/pull/2) 與
[PR #3](https://github.com/Openclaw-Metis/MOSS-Image-Colab/pull/3) 合併進 `main`（`b00af07`）後，
使用者在新配的 L4 上自行照 README 操作，回報各項正常。檢查清單：

1. 點 README 的按鈕開 Notebook，執行第 1～4 格（不改任何參數；第 2 格預設下載 Base 以外的全部模型）。
2. 點登入連結，在五個分頁各跑一個最簡單的工作，下載一張作品。
3. 匯出專案 ZIP，執行最後一格停止工具，刪除執行階段。

這次由使用者操作，沒有把截圖或報告取回 `docs/evidence/`；紀錄依據是使用者的回報。
第 2 格新增的 `DOWNLOAD_FEATURE_MODELS` 也是在這次重演第一次於 Colab 執行。

Stage 10 完成。因為 AC-08、AC-11 是有條件通過，交付的仍是標明為開發版的版本。
