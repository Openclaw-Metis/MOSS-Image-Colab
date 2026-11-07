import {request,session,currentProject,pollJob,draftSaver,TERMINAL,capabilityLabel} from "/static/api.js";
const $=(id)=>document.getElementById(id);
const SLOTS=[1,2,3,4];
const E={project:null,slots:[null,null,null,null],active:null,pollToken:0,submitting:false,
  pending:null,profile:null,saver:null,bound:null};
const message=(text)=>{$("edit-status").textContent=text;};
const busy=()=>E.active&&!TERMINAL.has(E.active.status);
const gaps=()=>{const last=E.slots.map(Boolean).lastIndexOf(true);return E.slots.slice(0,last).some(s=>!s);};

function capture(){return {slots:E.slots,prompt:$("edit-prompt").value,negative:$("edit-negative").value,
  seed:$("edit-seed").value,roles:SLOTS.map(i=>$(`edit-role-${i}`).value)};}

function render(){
  for(const i of SLOTS){const slot=E.slots[i-1];const img=$(`edit-preview-${i}`);
    img.hidden=!slot;$(`edit-empty-${i}`).hidden=!!slot;$(`edit-remove-${i}`).disabled=!slot;
    if(slot)img.src=`/api/assets/${E.project.id}/${slot.asset_id}`;else img.removeAttribute("src");}
  const main=E.slots[0];
  $("edit-size").textContent=main?`輸出尺寸：${main.edit_size[0]}×${main.edit_size[1]}（跟隨圖 1，約 1 MP）`
    :"輸出尺寸：放入圖 1 後顯示";
  $("edit-renumber-box").hidden=true;
}

async function loadProject(project){E.project=project;const d=project.drafts.edit||{};
  E.slots=SLOTS.map(i=>(d.slots||[])[i-1]||null);
  $("edit-prompt").value=d.prompt||"";$("edit-seed").value=d.seed||"";
  $("edit-negative").value=d.negative??(E.profile.default_negative_prompt||"");
  SLOTS.forEach(i=>{$(`edit-role-${i}`).value=(d.roles||[])[i-1]||"";});
  E.saver.setSavedHash(project.draft_hashes.edit);render();}

async function followProject(){
  // The t2i tab may have switched projects; never write this tab's draft into the old one.
  const id=localStorage.getItem("moss_studio_project");
  if(!E.project||E.project.id!==id){if(busy())throw Error("目前工作完成後再切換專案");
    await loadProject(await currentProject());}
}

async function upload(index,file){
  if(!file)return;
  if(file.size>20*1024**2){message("圖片需小於 20 MiB");return;}
  try{await followProject();message(`正在上傳圖 ${index}…`);
    const asset=await request(`/api/projects/${E.project.id}/assets?kind=input`,
      {method:"POST",body:file,headers:{"Content-Type":file.type||"application/octet-stream"}});
    E.project.revision=asset.project_revision;
    E.slots[index-1]={asset_id:asset.id,width:asset.width,height:asset.height,edit_size:asset.edit_size};
    render();E.saver.schedule();message(`圖 ${index} 已放入（${asset.width}×${asset.height}）`);
  }catch(error){message(error.message+"；保留原有圖片");}
  finally{$(`edit-file-${index}`).value="";}
}

function remove(index){E.slots[index-1]=null;render();E.saver.schedule();
  if(gaps())message(`圖 ${index} 已移除。提交前會請你確認新的圖號，不會自動改變指令中的圖號。`);}

function askRenumber(){
  const lines=[];let next=1;
  E.slots.forEach((slot,i)=>{if(slot){if(i+1!==next)lines.push(`圖 ${i+1} → 圖 ${next}`);next++;}});
  $("edit-renumber-hint").textContent=`中間有空格。重新編號後：${lines.join("、")}。請確認後再檢查指令中的圖號。`;
  $("edit-renumber-box").hidden=false;
}

function renumber(){E.slots=[...E.slots.filter(Boolean),null,null,null,null].slice(0,4);
  render();E.saver.schedule();message("已重新編號；請確認指令中的圖號仍正確，再按「開始修圖」。");}

async function watch(id){const token=++E.pollToken;localStorage.setItem("moss_edit_job",id);
  const job=await pollJob(id,{isCurrent:()=>token===E.pollToken,onUpdate:(job,text)=>{
    if(job)E.active=job;message(text);}});
  if(job?.status==="succeeded"){const asset=job.record.output_assets[0];
    const path=`/api/assets/${job.project_id}/${asset}`;
    $("edit-result").src=path;$("edit-result").hidden=false;
    $("edit-download").href=path;$("edit-download").hidden=false;
    $("edit-result-summary").textContent=`種子 ${job.seed} · ${job.record.seconds.toFixed(1)} 秒 · 工作流 ${job.record.workflow_hash.slice(0,12)} · 本地已保存，尚未匯出專案`;}
}

async function submit(){
  if(E.submitting)return;
  if(busy()){message("已有修圖工作進行中；可先編輯下一份，或取消目前工作。");return;}
  E.submitting=true;
  try{let payload=E.pending;
    if(!payload){await followProject();
      if(!E.slots.some(Boolean))throw Error("請至少放入圖 1");
      if(gaps()){askRenumber();throw Error("請先確認重新編號");}
      const prompt=$("edit-prompt").value.trim();if(!prompt)throw Error("請輸入修改指令");
      await E.saver.save();const refs=E.slots.filter(Boolean);
      payload={project_id:E.project.id,client_request_id:crypto.randomUUID(),project_revision:E.project.revision,
        task:"instruction_edit",profile_id:"edit_v1",model_artifact_id:"sft_bf16",prompt,
        negative_prompt:$("edit-negative").value,width:refs[0].edit_size[0],height:refs[0].edit_size[1],
        seed:$("edit-seed").value.trim()||null,references:refs.map((r,i)=>({asset_id:r.asset_id,slot:i+1})),
        layout:null,mask_asset_id:null,control:null,lora_stack:[]};
      E.pending=payload;localStorage.setItem("moss_edit_pending",JSON.stringify(payload));}
    message("正在驗證工作…");const job=await request("/api/jobs",{method:"POST",body:payload});
    E.pending=null;localStorage.removeItem("moss_edit_pending");E.active=job;
    E.project.revision=job.project_revision;watch(job.id);
  }catch(error){if(error.status===422){E.pending=null;localStorage.removeItem("moss_edit_pending");}
    message(error.message+(E.pending?"；提交狀態未確認，再按開始修圖會核對同一工作，不會重複建立。":""));}
  finally{E.submitting=false;}
}

async function cancel(){if(!E.active)return;
  try{await request(`/api/jobs/${E.active.id}/cancel`,{method:"POST"});message("已要求取消，等候引擎確認");}
  catch(error){message(error.message);}}

window.mossEdit={
  async init(){
    const root=$("edit-root");if(!root)return;
    if(E.bound===root){await followProject().catch(e=>message(e.message));return;}
    E.bound=root;const s=await session();E.profile=s.profiles.find(p=>p.id==="edit_v1")||{};
    $("edit-summary").textContent=`SFT bf16 · Edit LoRA · ${E.profile.steps} 步 · CFG ${E.profile.cfg} · ${capabilityLabel(s,"instruction_edit_4")}`;
    E.saver=draftSaver("edit",{getProject:()=>E.project,capture,onState:(t)=>{$("edit-save-state").textContent=t;}});
    for(const i of SLOTS){$(`edit-file-${i}`).onchange=(e)=>upload(i,e.target.files[0]);
      $(`edit-remove-${i}`).onclick=()=>remove(i);$(`edit-role-${i}`).oninput=()=>E.saver.schedule();}
    for(const id of ["edit-prompt","edit-negative","edit-seed"])$(id).oninput=()=>E.saver.schedule();
    $("edit-renumber").onclick=renumber;$("edit-submit").onclick=submit;$("edit-cancel").onclick=cancel;
    try{await loadProject(await currentProject());}catch(error){message(error.message);return;}
    const pending=localStorage.getItem("moss_edit_pending");
    if(pending){E.pending=JSON.parse(pending);
      try{const found=await request(`/api/jobs/request/${E.pending.project_id}/${E.pending.client_request_id}`);
        localStorage.removeItem("moss_edit_pending");E.pending=null;watch(found.id);return;}
      catch(error){message("前次提交尚未確認；按開始修圖以相同內容核對。"+error.message);return;}}
    const job=localStorage.getItem("moss_edit_job");if(job)watch(job);
  }
};
