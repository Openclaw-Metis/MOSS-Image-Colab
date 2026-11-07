"""Custom SVG layout canvas, serialized independently from ImageEditor."""

LAYOUT_HTML = """
<section id="layout-workbench" style="display:none">
 <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
  <button id="layout-add-text" type="button">新增文字框</button>
  <button id="layout-add-object" type="button">新增物件框</button>
  <button id="layout-add-character" type="button">新增人物框</button>
  <button id="layout-undo" type="button">復原框選</button>
  <button id="layout-delete" type="button">刪除選取框</button>
 </div>
 <svg id="layout-canvas" viewBox="0 0 1024 1024" role="img" tabindex="0"
  aria-label="可拖曳的排版畫布" preserveAspectRatio="xMidYMid meet"
  style="width:100%;height:450px;background:#e2e8f0;touch-action:none;border:1px solid #94a3b8">
 </svg>
 <p id="layout-hint" role="status">在畫布拖曳可新增框；選取後可移動，拖曳圓點調整大小。</p>
 <div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0">
  <label>選取框 <select id="layout-selection"><option value="">未選取</option></select></label>
  <label>種類 <select id="layout-kind"><option value="text">文字</option>
   <option value="object">物件</option><option value="character">人物</option></select></label>
  <label>框描述 <input id="layout-caption" aria-label="框描述"></label>
  <label>顯示文字 <input id="layout-text" aria-label="框顯示文字"></label>
  <label>配色（選填，逗號分隔）<input id="layout-palette" aria-label="框配色"
    placeholder="#1e3a8a, 米白"></label>
 </div>
 <div style="display:flex;gap:8px;flex-wrap:wrap">
  <label>x0 <input id="layout-x0" type="number" min="0" max="1" step="0.001"
    style="width:90px"></label>
  <label>y0 <input id="layout-y0" type="number" min="0" max="1" step="0.001"
    style="width:90px"></label>
  <label>x1 <input id="layout-x1" type="number" min="0" max="1" step="0.001"
    style="width:90px"></label>
  <label>y1 <input id="layout-y1" type="number" min="0" max="1" step="0.001"
    style="width:90px"></label>
 </div>
 <details style="margin-top:12px"><summary>排版 JSON</summary>
  <textarea id="layout-json" aria-label="排版 JSON"
    style="width:100%;height:220px;font:13px monospace"></textarea>
  <button id="layout-apply-json" type="button">套用 JSON</button>
 </details>
</section>
"""
