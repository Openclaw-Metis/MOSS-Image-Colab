"""Models tab markup; behaviour in static/models.js (client-only, HTTP)."""

_INPUT = "border:1px solid #94a3b8;padding:5px"

MODELS_HTML = f"""
<section id="models-root" style="display:flex;flex-direction:column;gap:12px">
 <p id="models-status" role="status">正在讀取模型清單…</p>
 <div style="overflow-x:auto">
  <table id="models-table" style="width:100%;border-collapse:collapse;font-size:14px">
   <thead><tr style="text-align:left;border-bottom:1px solid #cbd5e1">
    <th>模型</th><th>用途</th><th>大小</th><th>狀態</th><th>授權</th><th>操作</th></tr></thead>
   <tbody></tbody>
  </table>
 </div>
 <p style="color:#475569;margin:0">只能下載固定版本清單中的模型與你加入的 LoRA；
  檔案會在下載完成前驗證 SHA256。工作進行中不能切換主模型或刪除檔案。</p>
 <details><summary>加入 Hugging Face LoRA（只用於精細 50 步）</summary>
  <p style="color:#475569">填模型庫、完整 40 碼 commit 與檔案路徑。
   工具會向 Hugging Face 查詢並鎖定該檔的 SHA256 與大小，之後只會下載完全相同的檔案。
   是否適用 MOSS-Image 與授權條件請自行確認。</p>
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
   <label>模型庫 <input id="lora-repo" placeholder="擁有者/名稱" style="{_INPUT}"></label>
   <label>Commit <input id="lora-revision" placeholder="40 碼 commit" size="42"
    style="{_INPUT}"></label>
   <label>檔案路徑 <input id="lora-path" placeholder="例如 lora.safetensors"
    style="{_INPUT}"></label>
   <button id="lora-add" type="button">查詢並加入</button>
  </div>
  <p id="lora-status" role="status"></p>
 </details>
 <h3 style="margin:8px 0 0">高解析分段放大</h3>
 <p style="color:#475569;margin:0">每段最多放大 1.5 倍並重新繪製細節，最大 2048×2048。
  結果會標示為「分段放大」，不是原生 2K 生成。</p>
 <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
  <label>來源作品 <select id="hires-source" style="{_INPUT}"></select></label>
  <button id="hires-refresh" type="button">重新整理作品清單</button>
  <label>目標長邊 <select id="hires-edge" style="{_INPUT}">
   <option value="1536">1536</option><option value="2048" selected>2048</option></select></label>
  <label>重繪幅度 <input id="hires-denoise" type="range" min="0.2" max="0.8" step="0.05"
   value="0.6"> <output id="hires-denoise-value">0.60</output></label>
 </div>
 <p id="hires-plan"></p>
 <label for="hires-prompt"><strong>畫面描述（沿用原作品的描述效果最好）</strong></label>
 <textarea id="hires-prompt" rows="3" style="width:100%;{_INPUT}"></textarea>
 <div style="display:flex;gap:8px;flex-wrap:wrap">
  <button id="hires-submit" type="button" style="background:#1d4ed8;color:white;
    padding:10px 18px;border-radius:6px;border:0">開始放大</button>
  <button id="hires-cancel" type="button" style="padding:10px 18px">取消目前工作</button>
 </div>
 <p id="hires-status" role="status"></p>
 <img id="hires-result" alt="放大結果" hidden
  style="width:100%;max-height:650px;object-fit:contain">
 <p id="hires-result-summary"></p>
 <a id="hires-download" hidden download>下載圖片</a>
</section>
"""
