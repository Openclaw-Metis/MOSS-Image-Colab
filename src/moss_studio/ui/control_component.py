"""Vision/control tab markup; behaviour in static/control.js (client-only, HTTP)."""

from moss_studio.ui.edit_component import USAGE_NOTICE

_INPUT = "border:1px solid #94a3b8;padding:5px"
_IMAGE = "image/png,image/jpeg,image/webp"


def _preview(prefix: str, label: str) -> str:
    return f"""
 <div style="border:1px solid #cbd5e1;border-radius:8px;padding:8px;min-width:0">
  <strong>{label}</strong>
  <div style="aspect-ratio:1/1;background:#f1f5f9;display:flex;align-items:center;
    justify-content:center;overflow:hidden;margin:6px 0">
   <img id="{prefix}-preview" alt="{label} 預覽" hidden
     style="max-width:100%;max-height:100%;object-fit:contain">
   <span id="{prefix}-empty" style="color:#475569">未放入</span>
  </div>
  <input id="{prefix}-file" type="file" accept="{_IMAGE}" aria-label="{label} 上傳">
  <button id="{prefix}-remove" type="button" disabled>移除</button>
 </div>"""


CONTROL_HTML = f"""
<section id="control-root" style="display:flex;flex-direction:column;gap:12px">
 {USAGE_NOTICE}
 <fieldset style="border:0;padding:0;display:flex;gap:16px">
  <label><input type="radio" name="control-mode" value="color_depth" checked> 色彩／深度控制</label>
  <label><input type="radio" name="control-mode" value="vision"> 視覺參考（實驗）</label>
 </fieldset>
 <p id="control-status" role="status">放入來源圖，新圖會跟隨它的大致輪廓或深度。</p>
 <div id="control-cd">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px">
   {_preview("control-source", "來源圖（決定輸出比例）")}
   {_preview("control-depth", "自備深度圖（白近黑遠）")}
   {_preview("control-color", "色塊圖（每區一色，選填）")}
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px">
   <label>幾何來源 <select id="control-geometry" style="{_INPUT}">
    <option value="mask">自動估計：輪廓</option><option value="depth">自動估計：深度</option>
    <option value="upload">使用自備深度圖</option></select></label>
   <label>控制強度 <input id="control-strength" type="range" min="0" max="2" step="0.05" value="1">
    <output id="control-strength-value">1.00</output></label>
   <label>控制持續比例 <input id="control-end" type="range" min="0.05" max="1" step="0.05"
    value="0.6"> <output id="control-end-value">0.60</output></label>
  </div>
  <p style="color:#475569">只會跟隨大致構圖與幾何，不保證姿勢完全一致。
   估計的輪廓／深度圖目前不另外預覽。</p>
 </div>
 <div id="control-vision" hidden>
  <p style="background:#fef3c7;padding:8px 12px;border-radius:6px">
   實驗功能：MOSS-Image 沒有正式的圖片輸入，參考圖只經過文字編碼器的視覺塔，效果不保證。</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px">
   {"".join(_preview(f"vision-{i}", f"參考圖 {i}") for i in range(1, 5))}
  </div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px">
   <label>參考強度 <input id="vision-strength" type="range" min="0" max="4" step="0.1" value="1">
    <output id="vision-strength-value">1.0</output></label>
   <label>寬 <input id="vision-width" type="number" min="512" max="2048" step="16" value="1024"
    style="width:90px;{_INPUT}"></label>
   <label>高 <input id="vision-height" type="number" min="512" max="2048" step="16" value="1024"
    style="width:90px;{_INPUT}"></label>
  </div>
 </div>
 <label for="control-prompt"><strong>畫面描述</strong></label>
 <textarea id="control-prompt" rows="3" style="width:100%;{_INPUT}"
  placeholder="描述新圖的人物、服裝、場景與光線"></textarea>
 <details><summary>進階設定</summary>
  <label>負向提示詞 <textarea id="control-negative" rows="2" style="width:100%;{_INPUT}"></textarea>
  </label>
  <label>種子（留空自動產生）<input id="control-seed" style="{_INPUT}"></label>
 </details>
 <p id="control-summary"></p>
 <div style="display:flex;gap:8px;flex-wrap:wrap">
  <button id="control-submit" type="button" style="background:#1d4ed8;color:white;
    padding:10px 18px;border-radius:6px;border:0">產生圖片</button>
  <button id="control-cancel" type="button" style="padding:10px 18px">取消目前工作</button>
 </div>
 <p id="control-save-state"></p>
 <section>
  <img id="control-result" alt="生成結果" hidden
    style="width:100%;max-height:650px;object-fit:contain">
  <p id="control-result-summary"></p>
  <a id="control-download" hidden download>下載圖片</a>
 </section>
</section>
"""
