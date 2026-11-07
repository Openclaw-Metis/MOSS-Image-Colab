"""Instruction-edit tab markup. Behaviour lives in static/edit.js (client-only, HTTP)."""

USAGE_NOTICE = (
    '<p role="note" style="background:#fef3c7;color:#713f12;padding:8px 12px;border-radius:6px">'
    "使用限制：不得以真人照片製作換臉、私密或冒用他人身分的內容（Colab 對所有執行環境禁止"
    " deepfakes）。</p>"
)


def _slot(index: int) -> str:
    title = "圖 1（主圖，決定輸出比例）" if index == 1 else f"圖 {index}"
    return f"""
 <div class="edit-slot" id="edit-slot-{index}" style="border:1px solid #cbd5e1;border-radius:8px;
   padding:8px;display:flex;flex-direction:column;gap:6px;min-width:0">
  <strong id="edit-title-{index}">{title}</strong>
  <div style="aspect-ratio:1/1;background:#f1f5f9;display:flex;align-items:center;
    justify-content:center;overflow:hidden">
   <img id="edit-preview-{index}" alt="{title} 預覽" hidden
     style="max-width:100%;max-height:100%;object-fit:contain">
   <span id="edit-empty-{index}" style="color:#475569">尚未放入圖片</span>
  </div>
  <input id="edit-file-{index}" type="file" accept="image/png,image/jpeg,image/webp"
    aria-label="{title} 上傳">
  <input id="edit-role-{index}" placeholder="用途備註（只給你看，不送入模型）"
    aria-label="{title} 用途備註" style="border:1px solid #94a3b8;padding:5px">
  <button id="edit-remove-{index}" type="button" disabled>移除</button>
 </div>"""


EDIT_HTML = f"""
<section id="edit-root" style="display:flex;flex-direction:column;gap:12px">
 {USAGE_NOTICE}
 <p id="edit-status" role="status">放入 1～4 張圖片，描述要修改的內容，再按「開始修圖」。</p>
 <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px">
  {"".join(_slot(i) for i in range(1, 5))}
 </div>
 <div id="edit-renumber-box" hidden style="background:#fef3c7;padding:8px 12px;border-radius:6px">
  <p id="edit-renumber-hint"></p>
  <button id="edit-renumber" type="button">確認重新編號</button>
 </div>
 <label for="edit-prompt"><strong>修改指令</strong></label>
 <textarea id="edit-prompt" rows="4" style="width:100%;border:1px solid #94a3b8;padding:8px"
  placeholder="Change only the X to Y. Keep the character, face, hair, pose,
 background and composition unchanged."></textarea>
 <p style="color:#475569;margin:0">多張圖時，在指令中說明每張圖的用途（例如「圖 2 的外套」）。</p>
 <details><summary>進階設定</summary>
  <label>負向提示詞 <textarea id="edit-negative" rows="2"
    style="width:100%;border:1px solid #94a3b8"></textarea></label>
  <label>種子（留空自動產生）<input id="edit-seed"
    style="border:1px solid #94a3b8;padding:5px"></label>
 </details>
 <p id="edit-summary">SFT bf16 · Edit LoRA · 30 步 · CFG 4 · 尚未通過 GPU 驗收</p>
 <p id="edit-size">輸出尺寸：放入圖 1 後顯示</p>
 <div style="display:flex;gap:8px;flex-wrap:wrap">
  <button id="edit-submit" type="button" style="background:#1d4ed8;color:white;padding:10px 18px;
    border-radius:6px;border:0">開始修圖</button>
  <button id="edit-cancel" type="button" style="padding:10px 18px">取消目前工作</button>
 </div>
 <p id="edit-save-state"></p>
 <section id="edit-result-panel">
  <img id="edit-result" alt="修圖結果" hidden
    style="width:100%;max-height:650px;object-fit:contain">
  <p id="edit-result-summary"></p>
  <a id="edit-download" hidden download>下載圖片</a>
 </section>
</section>
"""
