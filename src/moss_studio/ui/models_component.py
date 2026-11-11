"""Models tab markup; behaviour in static/models.js (client-only, HTTP)."""

from moss_studio.ui.workbench_parts import first_steps, result_panel, status_line, submit_row

_STEPS = first_steps(
    "選一張這個專案的作品或上傳圖（也可從結果下方的「接著做 → 放大」帶過來）。",
    "選目標長邊；畫面描述沿用原作品的描述效果最好。",
    "按「開始放大」，放大到 2048×2048 在 L4 上約 520 秒。",
)

MODELS_HTML = f"""
<section id="models-root" class="moss-tab">
 {status_line("models-status", "正在讀取模型清單…")}
 <p id="models-done" class="moss-muted" role="status"></p>
 <div style="overflow-x:auto">
  <table id="models-table">
   <thead><tr><th>模型</th><th>用途</th><th>大小</th><th>狀態</th><th>授權</th><th>操作</th></tr>
   </thead>
   <tbody></tbody>
  </table>
 </div>
 <p class="moss-muted">只能下載固定版本清單中的模型與你加入的 LoRA；
  檔案會在下載完成前驗證 SHA256。工作進行中不能切換主模型或刪除檔案。</p>
 <details><summary>加入 Hugging Face LoRA（只用於精細 50 步）</summary>
  <p class="moss-muted">填模型庫、完整 40 碼 commit 與檔案路徑。
   工具會向 Hugging Face 查詢並鎖定該檔的 SHA256 與大小，之後只會下載完全相同的檔案。
   是否適用 MOSS-Image 與授權條件請自行確認。</p>
  <div class="moss-row">
   <label>模型庫 <input id="lora-repo" placeholder="擁有者/名稱"></label>
   <label>Commit <input id="lora-revision" placeholder="40 碼 commit" size="42"></label>
   <label>檔案路徑 <input id="lora-path" placeholder="例如 lora.safetensors"></label>
   <button id="lora-add" type="button">查詢並加入</button>
  </div>
  <p id="lora-status" role="status"></p>
 </details>
 <h3 id="hires-title" style="margin:8px 0 0">高解析分段放大</h3>
 <p class="moss-muted">每段最多放大 1.5 倍並重新繪製細節，最大 2048×2048。
  結果會標示為「分段放大」，不是原生 2K 生成。</p>
 <div class="moss-split">
  <div class="moss-inputs">
   <div class="moss-row">
    <img id="hires-preview" alt="來源作品預覽" hidden
     style="width:96px;height:96px;object-fit:contain;background:#f1f5f9;border-radius:6px">
    <label>來源作品 <select id="hires-source"></select></label>
    <button id="hires-refresh" type="button">重新整理作品清單</button>
   </div>
   <div class="moss-row">
    <label>目標長邊 <select id="hires-edge">
     <option value="1536">1536</option><option value="2048" selected>2048</option></select></label>
    <label>重繪幅度 <input id="hires-denoise" type="range" min="0.2" max="0.8" step="0.05"
     value="0.6"> <output id="hires-denoise-value">0.60</output></label>
   </div>
   <p id="hires-plan" class="moss-muted"></p>
   <label for="hires-prompt"><strong>畫面描述（沿用原作品的描述效果最好）</strong></label>
   <textarea id="hires-prompt" rows="3"></textarea>
   {submit_row("hires", "開始放大")}
  </div>
  <div class="moss-output">
   {status_line("hires-status", "選一張作品與目標長邊，再按「開始放大」。")}
   {result_panel("hires", "放大結果", _STEPS)}
  </div>
 </div>
</section>
"""
