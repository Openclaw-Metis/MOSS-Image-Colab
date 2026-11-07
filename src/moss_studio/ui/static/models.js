import {request,session,currentProject,pollJob,TERMINAL} from "/static/api.js";
const $=(id)=>document.getElementById(id);
const ROLE={backbone:"主模型",text_vision_encoder:"文字／視覺編碼器",vae:"VAE",edit_lora:"修圖 LoRA",
  control_lora:"控制 LoRA",speed_lora:"8 步加速 LoRA",geometry_estimator:"幾何估計（MoGe 3）"};
const STATE={ready:"已下載並校驗",missing:"未下載",downloading:"下載中…",failed:"下載失敗"};
const M={bound:null,timer:null,project:null,outputs:[],active:null,pollToken:0,submitting:false,pending:null};
const SHARED=new Set(["text_vision_encoder","vae"]);
const gib=(b)=>(b/1024**3).toFixed(2)+" GiB";

async function refreshModels(){
  try{const {models,busy}=await request("/api/models");const body=$("models-table").querySelector("tbody");body.replaceChildren();
    for(const m of models){const row=document.createElement("tr");row.style.borderBottom="1px solid #e2e8f0";
      const cells=[`${m.id}${m.active?"（使用中）":""}`,ROLE[m.role]||m.role,gib(m.size_bytes),
        (STATE[m.state]||m.state)+(m.message?`：${m.message}`:"")];
      for(const text of cells){const td=document.createElement("td");td.textContent=text;td.style.padding="6px 4px";row.append(td);}
      const license=document.createElement("td");const link=document.createElement("a");link.href=m.license_url;
      link.textContent=m.provider_declared_license||"授權";link.target="_blank";link.rel="noopener noreferrer";license.append(link);row.append(license);
      const actions=document.createElement("td");
      if(m.state==="missing"||m.state==="failed"){const b=document.createElement("button");b.type="button";b.textContent="下載";
        b.onclick=()=>act(`/api/models/${m.id}/download`,{},`${m.id} 開始下載`);actions.append(b);}
      if(m.role==="backbone"&&m.state==="ready"&&!m.active){const b=document.createElement("button");b.type="button";
        b.textContent="設為使用中";b.disabled=busy;b.title=busy?"工作進行中不可切換":"";
        b.onclick=()=>act("/api/models/activate",{artifact_id:m.id},`已切換主模型為 ${m.id}；新工作會使用它`);actions.append(b);}
      if(m.state==="ready"&&!m.active&&!SHARED.has(m.role)){const b=document.createElement("button");b.type="button";
        b.textContent="刪除檔案";b.disabled=busy;b.title=busy?"工作進行中不可刪除":"釋放磁碟空間，之後可重新下載";
        b.onclick=()=>{if(confirm(`刪除 ${m.id}（${gib(m.size_bytes)}）？之後需要時可重新下載。`))
          act(`/api/models/${m.id}`,null,`已刪除 ${m.id}`,"DELETE");};actions.append(b);}
      row.append(actions);body.append(row);}
    $("models-status").textContent=busy?"有工作進行中：可下載，但不能切換主模型或刪除檔案。":"模型清單已更新。";
    clearTimeout(M.timer);if(models.some(m=>m.state==="downloading"))M.timer=setTimeout(refreshModels,3000);
  }catch(error){$("models-status").textContent=error.message;}}

async function act(url,body,done,method="POST"){try{await request(url,body?{method,body}:{method});$("models-status").textContent=done;}
  catch(error){$("models-status").textContent=error.message;}await refreshModels();}

function targetSize(){const option=$("hires-source").selectedOptions[0];if(!option)return null;
  const w=Number(option.dataset.width),h=Number(option.dataset.height),edge=Number($("hires-edge").value);
  const scale=edge/Math.max(w,h);let tw=Math.round(w*scale/16)*16,th=Math.round(h*scale/16)*16;
  while(tw*th>2048*2048){tw-=16;th=Math.round(tw*h/w/16)*16;}
  return {w,h,tw,th};}

function showPlan(){const t=targetSize();$("hires-denoise-value").textContent=Number($("hires-denoise").value).toFixed(2);
  if(!t){$("hires-plan").textContent="先在其他分頁產生作品，或按「重新整理作品清單」。";return;}
  const passes=Math.ceil(Math.log(t.tw/t.w)/Math.log(1.5)-1e-9);
  $("hires-plan").textContent=t.tw<=t.w?"此作品已達目標尺寸，請選較大的長邊。"
    :`${t.w}×${t.h} → ${t.tw}×${t.th}，約 ${passes} 段（每段 ≤1.5 倍）`;}

async function refreshOutputs(){try{M.project=await currentProject();
  const assets=await request(`/api/projects/${M.project.id}/assets`);
  M.outputs=assets.filter(a=>a.kind==="output"||a.kind==="input").reverse();const select=$("hires-source");select.replaceChildren();
  for(const a of M.outputs){const o=document.createElement("option");o.value=a.id;o.dataset.width=a.width;o.dataset.height=a.height;
    o.textContent=`${a.kind==="output"?"作品":"上傳圖"} ${a.width}×${a.height} · ${a.id.slice(0,8)}`;select.append(o);}
  if(!$("hires-prompt").value)$("hires-prompt").value=M.project.drafts.t2i.prompt||"";showPlan();
}catch(error){$("hires-status").textContent=error.message;}}

async function watch(id){const token=++M.pollToken;
  const job=await pollJob(id,{isCurrent:()=>token===M.pollToken,onUpdate:(job,text)=>{if(job)M.active=job;$("hires-status").textContent=text;}});
  if(job?.status==="succeeded"){const asset=job.record.output_assets[0];const path=`/api/assets/${job.project_id}/${asset}`;
    $("hires-result").src=path;$("hires-result").hidden=false;$("hires-download").href=path;$("hires-download").hidden=false;
    $("hires-result-summary").textContent=`分段放大 ${job.record.passes.map(p=>p.join("×")).join(" → ")} · ${job.record.seconds.toFixed(1)} 秒 · 尚未匯出專案`;
    refreshOutputs();}}

async function submit(){if(M.submitting)return;
  if(M.active&&!TERMINAL.has(M.active.status)){$("hires-status").textContent="已有放大工作進行中";return;}
  M.submitting=true;
  try{let payload=M.pending;
    if(!payload){const t=targetSize();if(!t||t.tw<=t.w)throw Error("請選擇來源作品與較大的目標長邊");
      const prompt=$("hires-prompt").value.trim();if(!prompt)throw Error("請輸入畫面描述");
      const s=await session();M.project=await currentProject();
      payload={project_id:M.project.id,client_request_id:crypto.randomUUID(),project_revision:M.project.revision,
        task:"upscale",profile_id:"upscale_v1",model_artifact_id:s.model_artifact_id,prompt,negative_prompt:"",
        width:t.tw,height:t.th,seed:null,references:[{asset_id:$("hires-source").value,slot:1}],layout:null,
        mask_asset_id:null,control:{denoise:Number($("hires-denoise").value)},lora_stack:[]};M.pending=payload;}
    $("hires-status").textContent="正在驗證工作…";const job=await request("/api/jobs",{method:"POST",body:payload});
    M.pending=null;M.active=job;watch(job.id);
  }catch(error){if(error.status===422)M.pending=null;$("hires-status").textContent=error.message;}
  finally{M.submitting=false;}}

window.mossModels={
  async init(){const root=$("models-root");if(!root)return;
    if(M.bound!==root){M.bound=root;await session();
      $("hires-refresh").onclick=refreshOutputs;$("hires-source").onchange=showPlan;$("hires-edge").onchange=showPlan;
      $("hires-denoise").oninput=showPlan;$("hires-submit").onclick=submit;
      $("hires-cancel").onclick=async()=>{if(!M.active)return;
        try{await request(`/api/jobs/${M.active.id}/cancel`,{method:"POST"});}catch(error){$("hires-status").textContent=error.message;}};}
    await refreshModels();await refreshOutputs();}
};
