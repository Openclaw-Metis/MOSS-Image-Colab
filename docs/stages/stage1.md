# Stage 1 — PASS（2026-11-07）

## 實際環境與版本

Colab 分配到 NVIDIA L4：23,659,151,360 bytes VRAM、56,863,301,632 bytes RAM。
Python 3.13.16、torch 2.14.1+cu130、CUDA 13.0、driver 580.82.07。
固定 ComfyUI 0.44.0 commit `1332fabfcc507aa7c548cd5152071ed494c207e8`，Gradio 6.31.0。
122 個實際相依版本寫入 `configs/requirements-colab-py313.lock`；此鎖依賴 Colab 的
指定基底與 system site-packages，不宣稱適用任意乾淨 Python/PyPI 環境。

## 已完成的必要探測

| 探測 | 結果／證據 |
|---|---|
| SFT bf16 + Qwen int8_convrot + VAE，1024² 單步 | 實際成功，冷載入約 16.28 秒 |
| 原生視覺塔，不接 VAE、不掛 Edit LoRA | 實際成功，約 5.33 秒；沒有文字增強器 |
| 原生 Edit + VAE 參考 latent + Edit LoRA | 實際成功，約 5.52 秒 |
| 模型來源 | 固定 HF revision；SFT/encoder/VAE/Edit 四個檔案 bytes、SHA256 全數校驗 |
| 認證 | 頁面登入；未登入 session/config/submission/upload/image 均被擋，圖片已登入 200、未登入 401 |
| CSRF／去重 | 無 CSRF 提交 403；相同 request id + payload 返回相同 job id |
| Quick Tunnel | 真實瀏覽器登入、上傳來源圖、vision 生成、PNG/ZIP 下載皆完成 |
| 取消 | 真實工作 cancelling → cancelled；使用 prompt_id 定向 interrupt，沒有全域清空 |
| 重連 | 瀏覽器 reload 後找回相同 job id 與結果，沒有重新提交 |
| 無 SSE 依賴 | 三個 Gradio callback 的 backend_fn 全為 false；connect_heartbeat=false；生成/查詢為同源 HTTP |
| 重跑 | 真實 managed engine 重跑沿用相同 PID；已校驗權重再次驗證，不重新下載 |
| 冷安裝重演 | 新 ComfyUI checkout + 新 venv，依 122 個鎖定版本重演成功；同一已宣告 Colab 基底 |

瀏覽器擴充功能的自動檔案上傳因 file URL 權限不足而受阻，已如實回報；使用者透過
正常上傳介面提供測試圖，完成真實 UI 上傳驗證。該圖片不納入公開倉庫。
Colab 原生受保護預覽在此瀏覽器出現輸出 JS/第三方 Cookie 錯誤，因此採規格內的
Quick Tunnel + polling 路徑；沒有修改瀏覽器安全設定，也沒有啟用 Gradio share。

## 原始碼測試與修正

本地原始碼以 SHA256 `92ab69bdf6583f0ffe28f8863e4198aeee3ed57f364fb84f5a23ba75fdc35860`
的初始來源包傳到 Colab，執行 51 項 CPU/真實 GPU 測試成功。後續冷安裝發現
`git clone --no-checkout` 被 dirty check 誤判；改為正常 clone 後 checkout 固定 commit，
加入真實本地 git 的冷 clone/重跑/保護本地修改回歸測試。

修正後，在新引擎目錄與隔離 venv 重演：**52 passed in 33.19s**（49 CPU + 3 真實 L4
載入探測）。原引擎停止後才啟動重演引擎；完成後停止重演引擎並恢復原引擎。
另修正 Linux `/proc/cmdline` 在 exec 交接短暫為空時的程序所有權判定。

原始碼中 `tests/gpu/test_load_paths.py` 必須由 `MOSS_RUN_GPU=1` 明確啟用；一般 CPU
環境會 skip，不把 skip 當成 GPU PASS。

## 完成邊界與下一階段

Stage 1 的環境、載入與至少一條合規入口已完成。這些為單步載入/通訊探測，不是畫質、
50/8 步效能、四圖、2K、完整五分頁或最終 AC-01～18 放行。Stage 2 起逐項完成正式功能。
Stage 10 仍需按最終 Notebook/README 在乾淨 Colab VM 重演整套正式產品。

回滾：固定的 ComfyUI/HF/cloudflared 與套件鎖；只停止本工具記錄且驗證所有權的程序。
不清除作品或使用者專案。單次入口密碼、公開臨時網址與私有 Notebook URL 不入版控。
