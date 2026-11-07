"""Brush inpaint tab markup. Behaviour lives in static/inpaint.js (client-only, HTTP).

A custom canvas replaces gr.ImageEditor: the editor's value travels through Gradio backend
callbacks, which need SSE that Quick Tunnel does not carry (spec v1.3 C7).
"""

from moss_studio.ui.edit_component import USAGE_NOTICE

_BUTTON = "padding:7px 10px;border:1px solid #94a3b8;border-radius:5px;background:white"

INPAINT_HTML = f"""
<section id="inpaint-root" style="display:flex;flex-direction:column;gap:12px">
 {USAGE_NOTICE}
 <p id="inpaint-status" role="status">先放入來源圖，再用筆刷塗抹要修改的區域。</p>
 <label>來源圖 <input id="inpaint-file" type="file"
   accept="image/png,image/jpeg,image/webp"></label>
 <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
  <button id="inpaint-brush" type="button" style="{_BUTTON}" aria-pressed="true">筆刷</button>
  <button id="inpaint-eraser" type="button" style="{_BUTTON}" aria-pressed="false">橡皮擦</button>
  <label>筆刷大小 <input id="inpaint-size" type="range" min="4" max="256" value="48"></label>
  <button id="inpaint-undo" type="button" style="{_BUTTON}">復原</button>
  <button id="inpaint-clear" type="button" style="{_BUTTON}">清除</button>
  <button id="inpaint-invert" type="button" style="{_BUTTON}">反轉</button>
  <label><input id="inpaint-preview" type="checkbox"> 黑白遮罩預覽</label>
 </div>
 <div id="inpaint-stage" style="position:relative;max-width:100%;background:#f1f5f9;
   min-height:240px;display:flex;align-items:center;justify-content:center">
  <span id="inpaint-empty" style="color:#475569">尚未放入來源圖</span>
  <img id="inpaint-source" alt="來源圖" hidden
   style="max-width:100%;max-height:640px;display:block">
  <canvas id="inpaint-overlay" hidden aria-label="遮罩畫布：白色區域會重繪"
   style="position:absolute;touch-action:none;cursor:crosshair"></canvas>
 </div>
 <p style="color:#475569;margin:0">藍色＝要重繪的區域；未塗抹的地方會逐像素保留原圖。</p>
 <label for="inpaint-prompt"><strong>重繪內容描述</strong></label>
 <textarea id="inpaint-prompt" rows="3" style="width:100%;border:1px solid #94a3b8;padding:8px"
  placeholder="描述塗抹區域要畫成什麼，例如：一束紅色玫瑰"></textarea>
 <div style="display:flex;gap:16px;flex-wrap:wrap">
  <label>重繪幅度 <input id="inpaint-denoise" type="range" min="0.05" max="1" step="0.05"
    value="0.65"> <output id="inpaint-denoise-value">0.65</output></label>
  <label>邊緣柔和度 <input id="inpaint-softness" type="range" min="0" max="1" step="0.05"
    value="0.15"> <output id="inpaint-softness-value">0.15</output></label>
 </div>
 <label id="inpaint-full-box" hidden><input id="inpaint-full" type="checkbox">
  確認整張重繪（遮罩已涵蓋整張圖）</label>
 <details><summary>進階設定</summary>
  <label>負向提示詞 <textarea id="inpaint-negative" rows="2"
    style="width:100%;border:1px solid #94a3b8"></textarea></label>
  <label>種子（留空自動產生）<input id="inpaint-seed"
    style="border:1px solid #94a3b8;padding:5px"></label>
 </details>
 <p id="inpaint-summary">SFT bf16 · 30 步 · 遮罩 latent 重繪＋柔邊合成 · 尚未通過 GPU 驗收</p>
 <div style="display:flex;gap:8px;flex-wrap:wrap">
  <button id="inpaint-submit" type="button" style="background:#1d4ed8;color:white;
    padding:10px 18px;border-radius:6px;border:0">開始重繪</button>
  <button id="inpaint-cancel" type="button" style="padding:10px 18px">取消目前工作</button>
 </div>
 <p id="inpaint-save-state"></p>
 <section id="inpaint-result-panel">
  <img id="inpaint-result" alt="重繪結果" hidden
    style="width:100%;max-height:650px;object-fit:contain">
  <p id="inpaint-result-summary"></p>
  <a id="inpaint-download" hidden download>下載圖片</a>
 </section>
</section>
"""
