"""Brush inpaint tab markup. Behaviour lives in static/inpaint.js (client-only, HTTP).

A custom canvas replaces gr.ImageEditor: the editor's value travels through Gradio backend
callbacks, which need SSE that Quick Tunnel does not carry (spec v1.3 C7).
"""

from moss_studio.ui.workbench_parts import (
    IMAGE_TYPES,
    USAGE_NOTICE,
    result_panel,
    status_line,
    submit_row,
)

INPAINT_HTML = f"""
<section id="inpaint-root" class="moss-tab">
 {USAGE_NOTICE}
 <div class="moss-split moss-canvas-first">
  <div class="moss-inputs">
   <div class="moss-row">
    <button id="inpaint-pick" type="button">選擇來源圖</button>
    <input id="inpaint-file" type="file" accept="{IMAGE_TYPES}" aria-label="來源圖上傳" hidden>
    <button id="inpaint-brush" type="button" aria-pressed="true" title="快捷鍵 B">筆刷</button>
    <button id="inpaint-eraser" type="button" aria-pressed="false" title="快捷鍵 E">橡皮擦</button>
    <label>大小 <input id="inpaint-size" type="range" min="4" max="256" value="48"
      title="快捷鍵 [ 與 ]"></label>
    <button id="inpaint-undo" type="button" title="Ctrl+Z">復原</button>
    <button id="inpaint-clear" type="button">清除</button>
    <button id="inpaint-invert" type="button">反轉</button>
    <label><input id="inpaint-preview" type="checkbox"> 黑白遮罩預覽</label>
   </div>
   <div id="inpaint-stage" style="position:relative;max-width:100%;background:#f1f5f9;
     min-height:280px;display:flex;align-items:center;justify-content:center;border-radius:6px">
    <div id="inpaint-empty" class="moss-drop" aria-label="來源圖：選擇圖片"
      style="aspect-ratio:auto;align-self:stretch;flex:1;min-height:280px">
     點擊、拖放或貼上來源圖</div>
    <img id="inpaint-source" alt="來源圖" hidden style="max-width:100%;max-height:70vh">
    <canvas id="inpaint-overlay" hidden aria-label="遮罩畫布：塗抹的區域會重繪"
     style="position:absolute;touch-action:none;cursor:none"></canvas>
    <div id="inpaint-cursor" hidden aria-hidden="true" style="position:absolute;border-radius:50%;
     border:2px solid #fff;box-shadow:0 0 0 1px #0f172a;pointer-events:none"></div>
   </div>
   <p class="moss-muted">藍色＝要重繪的區域；未塗抹的地方會逐像素保留原圖。</p>
  </div>
  <div class="moss-output">
   <label for="inpaint-prompt"><strong>重繪內容描述</strong></label>
   <textarea id="inpaint-prompt" rows="3"
    placeholder="描述塗抹區域要畫成什麼，例如：一束紅色玫瑰"></textarea>
   <div class="moss-row">
    <label>重繪幅度 <input id="inpaint-denoise" type="range" min="0.05" max="1" step="0.05"
      value="1"> <output id="inpaint-denoise-value">1.00</output></label>
    <label>邊緣柔和度 <input id="inpaint-softness" type="range" min="0" max="1" step="0.05"
      value="0.15"> <output id="inpaint-softness-value">0.15</output></label>
   </div>
   <p class="moss-muted">要加入新東西請用重繪幅度 1.00；只想微調質感或顏色再調低。</p>
   <label id="inpaint-full-box" hidden><input id="inpaint-full" type="checkbox">
    確認整張重繪（遮罩已涵蓋整張圖）</label>
   <details><summary>進階設定</summary>
    <label>負向提示詞 <textarea id="inpaint-negative" rows="2"></textarea></label>
    <label>種子（留空自動產生）<input id="inpaint-seed" inputmode="numeric"></label>
   </details>
   <p id="inpaint-summary" class="moss-muted">30 步 · 遮罩 latent 重繪＋柔邊合成</p>
   {submit_row("inpaint", "開始重繪")}
   <p id="inpaint-save-state" class="moss-muted"></p>
   {status_line("inpaint-status", "先放入來源圖，再用筆刷塗抹要修改的區域。")}
   {result_panel("inpaint", "重繪結果", "重繪結果會顯示在這裡。")}
   <button id="inpaint-compare" type="button" hidden
    title="按住時顯示來源圖，放開回到結果">按住比較原圖</button>
  </div>
 </div>
</section>
"""
