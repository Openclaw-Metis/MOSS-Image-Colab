# Stage 0 — PASS（2026-11-07）

已建立 Python 五層骨架、Project/Asset/JobSpec v1 驗證、原子 JSON（temp/fsync/rename）、
跨程序 flock、revision CAS、可恢復刪除、SQLite WAL ledger、不可變快照與事件序號。
schema v1 無損讀取，未知版本/未知根欄位拒絕，extensions 保留。

實際驗證（Python 3.12.14、Linux）：

```bash
.venv/bin/pytest -q
# 28 passed
.venv/bin/ruff check src tests
# All checks passed
.venv/bin/ruff format --check src tests
# 16 files already formatted
```

測試涵蓋 CRUD、兩個寫入者衝突、replace/fsync 失敗保留舊稿、路徑與 symlink、
NaN、未知 schema、十二個並行重複提交去重、SQL 層不可變快照、取消、重啟中斷狀態。
首輪發現 SQL placeholder 數目及一項錯誤邊界期望，修正後全數通過。
這些是資料/領域測試，未宣稱推論可用；素材解碼與專案/工作關聯刪除屏障屬後續應用層。

回滾：回到本階段前的 Initial commit。不得刪除使用者資料。
