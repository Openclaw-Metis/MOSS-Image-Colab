"""Vision/control tab markup; behaviour in static/control.js (client-only, HTTP)."""

from moss_studio.ui.workbench_parts import (
    USAGE_NOTICE,
    examples_row,
    first_steps,
    picture_slot,
    result_panel,
    status_line,
    submit_row,
)

_STEPS = first_steps(
    "放入來源圖：新圖會沿用它的大致構圖、姿勢與遠近，不會沿用它的外觀。",
    "描述新圖要畫什麼，或點一個範例；想離來源圖遠一點就調低控制強度。",
    "按「產生圖片」，L4 上約 60 秒；結果下方會附上這次實際套用的深度圖。",
)

CONTROL_HTML = f"""
<section id="control-root" class="moss-tab">
 {USAGE_NOTICE}
 <fieldset class="moss-row" style="border:0;padding:0;margin:0">
  <label><input type="radio" name="control-mode" value="color_depth" checked> 色彩／深度控制</label>
  <label><input type="radio" name="control-mode" value="vision"> 視覺參考（實驗）</label>
 </fieldset>
 <div class="moss-split">
  <div class="moss-inputs">
   <div id="control-cd">
    <div class="moss-grid">
     {picture_slot("control-source", "來源圖（決定輸出比例）")}
     {picture_slot("control-depth", "自備深度圖（白近黑遠，選填）")}
     {picture_slot("control-color", "色塊圖（每區一色，選填）")}
    </div>
    <div class="moss-row" style="margin-top:8px">
     <label>幾何來源 <select id="control-geometry">
      <option value="depth">自動估計：深度（建議）</option>
      <option value="mask">自動估計：輪廓（背景需是天空或遠景）</option>
      <option value="upload">使用自備深度圖</option></select></label>
     <label>控制強度 <input id="control-strength" type="range" min="0" max="2" step="0.05"
      value="1"> <output id="control-strength-value">1.00</output></label>
     <label>控制持續比例 <input id="control-end" type="range" min="0.05" max="1" step="0.05"
      value="0.6"> <output id="control-end-value">0.60</output></label>
    </div>
    <details><summary>怎麼選幾何來源與強度</summary>
     <p class="moss-muted">只會跟隨大致構圖與幾何，不保證姿勢完全一致。
      自動估計時，結果下方會顯示這次實際套用的輪廓／深度圖。
      輪廓模式在棚拍或室內背景下常整片變白，等於沒有控制；深度模式連身形也會帶過來，
      若要把人物換成別的角色（例如機器人），可調低控制強度或持續比例。</p>
    </details>
   </div>
   <div id="control-vision" hidden>
    <p class="moss-notice">
     實驗功能：MOSS-Image 沒有正式的圖片輸入，參考圖只經過文字編碼器的視覺塔，效果不保證。</p>
    <div class="moss-grid moss-grid-4" style="margin-top:8px">
     {"".join(picture_slot(f"vision-{i}", f"參考圖 {i}") for i in range(1, 5))}
    </div>
    <div class="moss-row" style="margin-top:8px">
     <label>參考強度 <input id="vision-strength" type="range" min="0" max="4" step="0.1"
      value="1"> <output id="vision-strength-value">1.0</output></label>
     <label>寬 <input id="vision-width" type="number" min="512" max="2048" step="16" value="1024"
      style="width:90px"></label>
     <label>高 <input id="vision-height" type="number" min="512" max="2048" step="16" value="1024"
      style="width:90px"></label>
    </div>
   </div>
   <label for="control-prompt"><strong>畫面描述</strong></label>
   {examples_row("control")}
   <textarea id="control-prompt" rows="3"
    placeholder="描述新圖的人物、服裝、場景與光線"></textarea>
   <details><summary>進階設定</summary>
    <label>負向提示詞 <textarea id="control-negative" rows="2"></textarea></label>
    <label>種子（留空自動產生）<input id="control-seed" inputmode="numeric"></label>
   </details>
   <p id="control-summary" class="moss-muted"></p>
   {submit_row("control", "產生圖片")}
   <p id="control-save-state" class="moss-muted"></p>
  </div>
  <div class="moss-output">
   {status_line("control-status", "放入來源圖，新圖會跟隨它的大致輪廓或深度。")}
   {result_panel("control", "生成結果", _STEPS)}
   <p id="control-map-label" class="moss-muted" hidden>這次實際套用的估計輪廓／深度圖：</p>
   <img id="control-map" alt="估計的控制圖" hidden
     style="max-width:360px;max-height:360px;object-fit:contain;border:1px solid #cbd5e1">
  </div>
 </div>
</section>
"""
