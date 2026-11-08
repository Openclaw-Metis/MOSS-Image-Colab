# GPU 批次 E（精簡版，2026-11-08，Colab L4）

使用者選擇精簡回歸：只補沒有證據的項目，其餘沿用批次 A～D（見 [Stage 9 總表](../../stages/stage9.md)）。
在一台**新配的** L4（主機 `26c1276b4bcc`）上執行，程式 `557abc7`。完整 ZIP（15,208,407 bytes）留在使用者電腦。

| 項目 | 結果 | 檔案 |
|---|---|---|
| AC-01 重跑安裝與啟動 | 通過：引擎（PID 5076）與工作台（PID 7875）都沿用，4 個已下載權重的修改時間不變 | `ac01.json` |
| 引擎 preflight | 11 種圖全部通過真引擎驗證 | `preflight.txt` |
| VM 上的契約測試 | 214 項，0 失敗、0 錯誤、0 略過（含 Windows 上略過的 `/proc` 與符號連結測試） | `cpu_tests.json` |
| AC-06 fast8 | 暖機 11.5 秒，正式 5 次皆 10.4～10.5 秒，1024²、非黑圖 | `ac06_benchmark.json` |
| AC-18 一般生成 | 5/5 符合事先凍結的 3 項特徵，耗時 110～179 秒 | `ac18_report.json`、`ac18_scoring.json`、`previews/ac18-general.jpg` |

第一次執行時 preflight 失敗：這台新 VM 只下載了文生圖需要的模型，修圖與控制的 LoRA、MoGe 要到後面的步驟才下載。
補下載後重跑全部通過；Notebook 第 10 格已改為先下載再檢查（`b1afbd1`）。

AC-04 未另外重跑：AC-18 在同一版程式上以 quality50 跑了 5 次（1～1.5 MP），全部成功；1024² 基準沿用批次 A。
