# 相容性與 Stage 1 探測

2026-11-07 實際 Colab：NVIDIA L4，23,659,151,360 bytes VRAM、56,863,301,632 bytes RAM。
Python 3.13.16、PyTorch 2.14.1+cu130、CUDA 13.0、driver 580.82.07。
ComfyUI 0.44.0 commit `1332fabfcc507aa7c548cd5152071ed494c207e8`；Gradio 6.31.0。

| 路徑 | 實際結果 | 不能據此推論 |
|---|---|---|
| bf16 SFT + int8_convrot 編碼器 + VAE，1024²，單步 | 成功，16.28 秒冷載入 | 50 步畫質或穩定速度 |
| 原生 TextEncodeMOSSImageEdit，無 VAE、無 Edit LoRA，圖片進視覺塔 | 成功，約 5.33 秒 | 參考品質 ≥80% |
| 原生 Edit + VAE 參考 latent + Edit LoRA | 成功，約 5.52 秒 | 四圖、2K 或局部修補品質 |
| Gradio 原生認證 | 未登入 config/info/file/upload 均 401 | 最終整合版已完成全部安全驗收 |
| Colab 保護預覽 | 空白；Colab 回報輸出 JS/登入/第三方 Cookie 限制 | 不能保證所有瀏覽器皆失敗 |
| Quick Tunnel + 同源 HTTP polling | Stage 1：登入、一次真實 GPU 出圖、下載 PNG/ZIP。2026-11-08 補齊上傳、取消、重新整理後接回（[AC-03](evidence/stage9-ac03/README.md)） | Cloudflare Quick Tunnel 的可用性（無 SLA） |

原生 `TextEncodeMOSSImageEdit` 在未連 VAE 時，會把圖片送入 Qwen 視覺塔，
直接回傳 conditioning；本固定版本可先驗證原生路徑，不必先裝社群外掛。
這條路徑沒有 TextGenerate/提示詞增強器，不能把文字描述當成視覺輸入。

Colab 部分映像無法使用 venv 的 ensurepip；bootstrap 用 `with_pip=False` 與
`system_site_packages=True`，沿用 Colab 的 pip/PyTorch，但其他安裝仍落在工具 venv。
這是有明確基底映像條件的候選設定，完整 transitive lock 尚未放行；
2026-11-08 使用者依 README 在乾淨 L4 重演，回報安裝與五分頁都正常（[Stage 10](stages/stage10.md)）。

## 固定來源

- [ComfyUI server contract](https://github.com/Comfy-Org/ComfyUI/blob/1332fabfcc507aa7c548cd5152071ed494c207e8/server.py)
- [原生 MOSS 節點](https://github.com/Comfy-Org/ComfyUI/blob/1332fabfcc507aa7c548cd5152071ed494c207e8/comfy_extras/nodes_moss_image.py)
- [Gradio ImageEditor 6.31.0](https://github.com/gradio-app/gradio/blob/gradio%406.31.0/gradio/components/image_editor.py)
- [Gradio queue 6.31.0](https://github.com/gradio-app/gradio/blob/gradio%406.31.0/gradio/queueing.py)
- [固定模型來源](https://huggingface.co/Comfy-Org/MOSS-Image/tree/2929efe3cdd506c0a430bcfca70a9a8d805cc095)

版本與模型 bytes/hash 見 configs。各功能的驗收狀態以 `configs/capabilities.json` 為準；
整體仍是開發版（AC-08、AC-11 有條件通過，見 [Stage 9](stages/stage9.md)）。

## v1.3 參數來源

下表是開發時採用的來源設定；GPU 批次 C 之後的調整列在下一節。

| 功能 | 設定 | 來源 |
|---|---|---|
| fast8 | `lora_latest.safetensors`（lodestones/MOSS-Image-SFT-8-steps-dmd @f95df83）強度 0.7、8 步 Euler、shift 5、CFG 1 | 作者示範 Space `app.py` |
| 指令修圖 | Edit LoRA 1.0、30 步、CFG 4、euler／normal、SLG 單層 22（0→1）、`Moss-Image-Edit`、圖 1 經 `ImageScaleToTotalPixels`（1 MP、16 px）決定輸出 | Comfy-Org `image_moss_image_edit` 範本 |
| 色彩／深度 | 控制 LoRA 1.0、TSR 0.95／1、shift 5、SLG 單層 24（0→1）、25 步 `er_sde`／simple、CFG 3、`MOSSImageControl` 強度 1 結束 0.6、MoGe 3（resolution 9、refine 3） | Comfy-Org `image_moss_image_color_depth_control` 範本；差異：用 KSampler `er_sde`，範本為 SamplerCustom s_noise 1.05 |
| 視覺參考（實驗） | 無 VAE 的 `TextEncodeMOSSImageEdit`，每張參考縮到 ≤384²，`image_strength` 可調 | ComfyUI `nodes_moss_image.py` @1332fab |
| 分段放大 | 每段 ≤1.5 倍、16 px 對齊、像素空間 `ImageScale` lanczos → VAEEncode → 重新採樣（denoise 0.6） | ComfyUI MOSS-Image 文件「Going above 2 MP」 |
| 筆刷重繪 | `VAEEncode` → `SetLatentNoiseMask`（`LoadImageMask` red）→ 30 步；柔邊映射與合成為本案設計 | 本案產品決策，需 AC-09 驗收 |

新增固定權重：`dmd8_lora`（1,189,176,800 bytes）、`moge3_vitg`（Comfy-Org/MoGe @1484985，2,501,605,198 bytes，宣告授權 MIT）。
SHA256 取自 Hugging Face LFS 資訊，下載時仍會實際校驗。

## GPU 驗收後的調整（2026-11-08）

| 功能 | 調整 | 依據 |
|---|---|---|
| 指令修圖 | 圖 1 維持 1 MP；圖 2～4 改縮到 0.25 MP（`secondary_reference_megapixels`）。0.5 MP 也試過，沒有改善 | [批次 C](evidence/stage4-6-batch-c/README.md)：每張 1 MP 時參考圖被貼成半透明圖層 |
| 筆刷重繪 | 預設強度 1.0（原 0.75～0.85） | 批次 C：部分雜訊時模型把背景補回去，不畫出要求的物件 |
| 色彩／深度 | 介面預設幾何來源改為深度 | 批次 C：MoGe 的 mask 標的是有效幾何範圍，棚拍背景整片有效而全白 |
| 真引擎驗證 | `LoadImage` 豁免本工作待上傳的檔名；`TextEncodeMOSSImageEdit.images` 依 autogrow 攤平的 `images.image_N` 驗證 | 批次 C 首次送出全數 422；`scripts/engine_preflight.py` 開跑前檢查 11 種圖 |
