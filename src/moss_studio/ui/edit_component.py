"""Instruction-edit tab markup. Behaviour lives in static/edit.js (client-only, HTTP)."""

from moss_studio.ui.workbench_parts import (
    USAGE_NOTICE,
    picture_slot,
    result_panel,
    status_line,
    submit_row,
)


def _slot(index: int) -> str:
    # GPU batch C: with 3-4 pictures the model dropped the extra pictures' content (AC-08 FAIL).
    title = {1: "圖 1（主圖）", 3: "圖 3（實驗）", 4: "圖 4（實驗）"}.get(index, f"圖 {index}")
    note = (
        f'<input id="edit-{index}-role" placeholder="用途備註（只給你看，不送入模型）"'
        f' aria-label="{title} 用途備註">'
    )
    return picture_slot(f"edit-{index}", title, extra=note)


_START = "放入 1～2 張圖片（3～4 張為實驗），描述要修改的內容，再按「開始修圖」。"

EDIT_HTML = f"""
<section id="edit-root" class="moss-tab">
 {USAGE_NOTICE}
 <div class="moss-split">
  <div class="moss-inputs">
   <div class="moss-grid moss-grid-4">{"".join(_slot(i) for i in range(1, 5))}</div>
   <div id="edit-renumber-box" class="moss-notice" hidden>
    <p id="edit-renumber-hint"></p>
    <button id="edit-renumber" type="button">確認重新編號</button>
   </div>
   <label for="edit-prompt"><strong>修改指令</strong></label>
   <textarea id="edit-prompt" rows="4"
    placeholder="Change only the X to Y. Keep the character, face, hair, pose,
 background and composition unchanged."></textarea>
   <p class="moss-muted">多張圖時，在指令中說明每張圖的用途（例如「圖 2 的外套」）。</p>
   <p id="edit-experimental" class="moss-notice" hidden>
    實驗：放入 3～4 張時，模型常沒有把圖 3、圖 4 的內容（顏色、款式、場景）帶進成品。
    建議一次最多 2 張，分幾次修改。</p>
   <details><summary>進階設定</summary>
    <label>負向提示詞 <textarea id="edit-negative" rows="2"></textarea></label>
    <label>種子（留空自動產生）<input id="edit-seed" inputmode="numeric"></label>
   </details>
   <p id="edit-summary" class="moss-muted">SFT bf16 · Edit LoRA · 30 步 · CFG 4</p>
   <p id="edit-size" class="moss-muted">輸出尺寸：放入圖 1 後顯示</p>
   {submit_row("edit", "開始修圖")}
   <p id="edit-save-state" class="moss-muted"></p>
  </div>
  <div class="moss-output">
   {status_line("edit-status", _START)}
   {result_panel("edit", "修圖結果", "修圖結果會顯示在這裡。")}
  </div>
 </div>
</section>
"""
