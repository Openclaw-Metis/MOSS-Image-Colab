"""Markup and styles shared by every tab; behaviour is in static/widgets.js.

Palette follows spec §11: primary #1D4ED8, done #0F766E, pending #B45309, error #B91C1C on
#F8FAFC. A tone is always paired with text.
"""

IMAGE_TYPES = "image/png,image/jpeg,image/webp"

USAGE_NOTICE = (
    '<p role="note" class="moss-notice">'
    "使用限制：不得以真人照片製作換臉、私密或冒用他人身分的內容（Colab 對所有執行環境禁止"
    " deepfakes）。</p>"
)

WORKBENCH_CSS = """
.gradio-container{--body-background-fill:#f8fafc;--block-background-fill:#fff;
 --input-background-fill:#f1f5f9;--body-text-color:#0f172a;--input-text-color:#0f172a}
.moss-tab{display:flex;flex-direction:column;gap:12px;color:#0f172a}
.moss-split{display:grid;gap:20px;grid-template-columns:minmax(0,1fr)}
.moss-inputs,.moss-output{display:flex;flex-direction:column;gap:12px;min-width:0}
@media(min-width:1100px){.moss-split{grid-template-columns:minmax(0,5fr) minmax(0,6fr);
 align-items:start}.moss-split.moss-canvas-first{grid-template-columns:minmax(0,6fr) minmax(0,5fr)}
 .moss-output{position:sticky;top:12px}}
.moss-muted{color:#475569;margin:0}
.moss-notice{background:#fef3c7;color:#713f12;padding:8px 12px;border-radius:6px;margin:0}
.moss-row{display:flex;gap:8px 16px;flex-wrap:wrap;align-items:center}
.moss-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.moss-grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}
@media(min-width:640px){.moss-grid-4{grid-template-columns:repeat(4,minmax(0,1fr))}}
.moss-tab input:not([type]),.moss-tab input[type=number],.moss-tab select,.moss-tab textarea,
#layout-workbench input,#layout-workbench select,#layout-workbench textarea,#project-menu input,
#project-menu select{color:#0f172a;background:#fff;border:1px solid #94a3b8;border-radius:5px;
 padding:6px 8px;font:inherit}
.moss-tab textarea{width:100%;box-sizing:border-box}
.moss-tab input[type=range]{accent-color:#1d4ed8;vertical-align:middle}
.moss-button,.moss-tab button,#layout-workbench button,#project-menu button,
#moss-view-controls button,#moss-gallery button:not(.moss-thumb){display:inline-flex;
 align-items:center;justify-content:center;min-height:36px;padding:6px 12px;
 border:1px solid #94a3b8;
 border-radius:6px;background:#fff;color:#0f172a;font:inherit;font-weight:500;cursor:pointer;
 text-decoration:none}
.moss-button:hover,.moss-tab button:hover:not(:disabled),#layout-workbench button:hover,
#project-menu button:hover{background:#eff6ff;border-color:#1d4ed8}
.moss-tab button:disabled,#moss-view-controls button:disabled{opacity:.5;cursor:not-allowed}
.moss-tab button[aria-pressed=true]{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
.moss-tab button.moss-primary,a.moss-primary{background:#1d4ed8;border-color:#1d4ed8;color:#fff;
 min-height:42px;padding:8px 20px;font-weight:600}
.moss-tab button.moss-primary:hover:not(:disabled),a.moss-primary:hover{background:#1e40af}
.moss-tab button.moss-danger,#project-menu button.moss-danger{color:#b91c1c;border-color:#fca5a5}
.moss-tab :focus-visible,.moss-button:focus-visible,#layout-workbench :focus-visible,
.moss-thumb:focus-visible,.moss-drop:focus-visible{outline:3px solid #93c5fd;outline-offset:2px}
.moss-status{display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;align-items:center;
 padding:10px 12px;border-radius:6px;border-left:4px solid #64748b;background:#f1f5f9}
.moss-status::before{content:"";width:10px;height:10px;border-radius:50%;background:#64748b}
.moss-status-time{color:#475569;font-variant-numeric:tabular-nums;white-space:nowrap}
.moss-status progress{grid-column:1/-1;width:100%;height:6px;appearance:none;border:0;
 border-radius:3px;background:#dbeafe;overflow:hidden}
.moss-status progress::-webkit-progress-bar{background:#dbeafe}
.moss-status progress::-webkit-progress-value{background:#1d4ed8}
.moss-status progress::-moz-progress-bar{background:#1d4ed8}
a.moss-button{color:#0f172a!important;text-decoration:none!important}
a.moss-button.moss-primary{color:#fff!important}
.moss-status[data-tone=running]{background:#eff6ff;border-color:#1d4ed8}
.moss-status[data-tone=running]::before{background:#1d4ed8;animation:moss-pulse 1.2s infinite}
.moss-status[data-tone=success]{background:#f0fdfa;border-color:#0f766e;color:#134e4a}
.moss-status[data-tone=success]::before{background:#0f766e}
.moss-status[data-tone=warn]{background:#fffbeb;border-color:#b45309;color:#78350f}
.moss-status[data-tone=warn]::before{background:#b45309}
.moss-status[data-tone=error]{background:#fef2f2;border-color:#b91c1c;color:#7f1d1d}
.moss-status[data-tone=error]::before{background:#b91c1c}
@keyframes moss-pulse{50%{opacity:.3}}
@media(prefers-reduced-motion:reduce){.moss-status::before{animation:none!important}}
.moss-slot{border:1px solid #cbd5e1;border-radius:8px;padding:8px;display:flex;
 flex-direction:column;gap:6px;min-width:0;background:#fff}
.moss-drop{aspect-ratio:1/1;background:#f1f5f9;border:2px dashed #94a3b8;border-radius:6px;
 display:flex;align-items:center;justify-content:center;overflow:hidden;cursor:pointer;
 color:#475569;text-align:center;padding:4px}
.moss-drop:hover,.moss-drop[data-over]{border-color:#1d4ed8;background:#eff6ff}
.moss-drop img{max-width:100%;max-height:100%;object-fit:contain}
.moss-result{display:flex;flex-direction:column;gap:8px}
.moss-result>img{width:100%;max-height:70vh;object-fit:contain;background:#f1f5f9;border-radius:6px}
.moss-result-empty{min-height:280px;display:flex;align-items:center;justify-content:center;
 background:#f1f5f9;color:#475569;border-radius:6px;padding:16px;text-align:center}
.moss-actions,.moss-actions-next{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.moss-actions-next{color:#475569;flex-basis:100%}
.moss-shortcut{color:#64748b;font-size:13px;margin:0}
#moss-gallery{margin-top:16px;border:1px solid #cbd5e1;border-radius:8px;padding:10px 14px;
 background:#fff;color:#0f172a}
#moss-gallery>summary{cursor:pointer;font-weight:600}
#moss-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;
 margin:10px 0}
.moss-thumb{padding:0;border:2px solid transparent;border-radius:6px;background:#f1f5f9;
 aspect-ratio:1/1;overflow:hidden;cursor:pointer}
.moss-thumb:hover{border-color:#1d4ed8}
.moss-thumb img{width:100%;height:100%;object-fit:cover;display:block}
#moss-gallery-detail>img{max-width:100%;max-height:60vh;object-fit:contain;display:block;
 margin-bottom:8px}
#models-table{width:100%;border-collapse:collapse;font-size:14px}
#models-table th{text-align:left;padding:8px 6px;border-bottom:2px solid #cbd5e1;white-space:nowrap}
#models-table td{padding:8px 6px;border-bottom:1px solid #e2e8f0;vertical-align:middle}
#models-table td[data-state=ready]{color:#0f766e}
#models-table td[data-state=missing],#models-table td[data-state=downloading]{color:#b45309}
#models-table td[data-state=failed]{color:#b91c1c}
#models-table button{margin:2px 4px 2px 0}
#moss-runtime{color:#475569;margin:0}
#moss-cancel[hidden],.moss-tab [hidden],.moss-result [hidden],.moss-status [hidden],
#moss-gallery [hidden]{display:none!important}
"""


def status_line(element_id: str, text: str) -> str:
    return (
        f'<div id="{element_id}" class="moss-status" data-tone="info" role="status" '
        f'aria-live="polite"><span class="moss-status-text">{text}</span>'
        '<span class="moss-status-time"></span><progress hidden></progress></div>'
    )


def result_panel(prefix: str, alt: str, empty: str) -> str:
    return f"""
 <section id="{prefix}-result-panel" class="moss-result" aria-label="結果">
  <div id="{prefix}-result-empty" class="moss-result-empty">{empty}</div>
  <img id="{prefix}-result" alt="{alt}" hidden>
  <p id="{prefix}-result-summary" class="moss-muted"></p>
  <div id="{prefix}-result-actions" class="moss-actions" hidden></div>
 </section>"""


def picture_slot(
    prefix: str, label: str, empty: str = "點擊、拖放或貼上圖片", extra: str = ""
) -> str:
    """One picture input: drop zone with preview, hidden file input, remove button."""
    return f"""
 <div class="moss-slot" id="{prefix}-slot">
  <strong id="{prefix}-title">{label}</strong>
  <div class="moss-drop" id="{prefix}-drop" aria-label="{label}：選擇圖片">
   <img id="{prefix}-preview" alt="{label} 預覽" hidden>
   <span id="{prefix}-empty">{empty}</span>
  </div>
  <input id="{prefix}-file" type="file" accept="{IMAGE_TYPES}" aria-label="{label} 上傳" hidden>
  {extra}
  <button id="{prefix}-remove" type="button" disabled>移除</button>
 </div>"""


def submit_row(prefix: str, label: str) -> str:
    return f"""
 <div class="moss-row">
  <button id="{prefix}-submit" type="button" class="moss-primary moss-cta">{label}</button>
  <button id="{prefix}-cancel" type="button" hidden>取消目前工作</button>
  <span class="moss-shortcut">Ctrl+Enter 也可送出</span>
 </div>"""


GALLERY_HTML = """
<details id="moss-gallery">
 <summary>本專案作品</summary>
 <p id="moss-gallery-status" class="moss-muted" role="status">正在讀取作品…</p>
 <div id="moss-gallery-grid"></div>
 <div id="moss-gallery-detail" hidden>
  <img id="moss-gallery-image" alt="選取的作品">
  <p id="moss-gallery-size" class="moss-muted"></p>
  <div id="moss-gallery-actions" class="moss-actions"></div>
 </div>
 <p><a id="moss-works" class="moss-button" hidden download>打包全部作品 ZIP</a></p>
</details>
"""
