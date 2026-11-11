import {request,session,currentProject,pollJob,draftSaver,capabilityLabel} from "/static/api.js";
import {setStatus,setBusy,running,reveal,pictureDrop,onPastePicture,showResult,takeHandoff,handoffFile} from "/static/widgets.js";
const $=(id)=>document.getElementById(id);
const SLOTS=["control-source","control-depth","control-color","vision-1","vision-2","vision-3","vision-4"];
const KIND={"control-depth":"control","control-color":"control"};
const C={project:null,assets:{},active:null,pollToken:0,submitting:false,pending:null,saver:null,bound:null};
const message=(text,tone="info")=>setStatus("control-status",text,{tone});
const busy=()=>running(C.active);
const syncButtons=()=>setBusy($("control-submit"),$("control-cancel"),busy());
const mode=()=>document.querySelector('input[name="control-mode"]:checked').value;

function capture(){return {mode:mode(),assets:C.assets,geometry:$("control-geometry").value,
  strength:Number($("control-strength").value),end_percent:Number($("control-end").value),
  image_strength:Number($("vision-strength").value),width:Number($("vision-width").value),
  height:Number($("vision-height").value),prompt:$("control-prompt").value,
  negative:$("control-negative").value,seed:$("control-seed").value};}

function render(){
  for(const slot of SLOTS){const asset=C.assets[slot];const img=$(`${slot}-preview`);
    img.hidden=!asset;$(`${slot}-empty`).hidden=!!asset;$(`${slot}-remove`).disabled=!asset;
    if(asset)img.src=`/api/assets/${C.project.id}/${asset.asset_id}/thumbnail`;else img.removeAttribute("src");}
  const vision=mode()==="vision";$("control-cd").hidden=vision;$("control-vision").hidden=!vision;
  $("control-strength-value").textContent=Number($("control-strength").value).toFixed(2);
  $("control-end-value").textContent=Number($("control-end").value).toFixed(2);
  $("vision-strength-value").textContent=Number($("vision-strength").value).toFixed(1);
  const source=C.assets["control-source"];
  $("control-summary").textContent=vision
    ?`50 步 · 參考圖只進視覺塔 · ${capabilityLabel(C.session,"vision_reference")}`
    :`SFT bf16 · 控制 LoRA · 25 步 er_sde · ${source?`輸出 ${source.inpaint_size.join("×")}（跟隨來源圖）`:"放入來源圖後顯示輸出尺寸"} · ${capabilityLabel(C.session,"color_depth")}`;
}

async function loadProject(project){C.project=project;const d=project.drafts.control||{};
  C.assets=d.assets||{};
  if(d.mode)document.querySelector(`input[name="control-mode"][value="${d.mode}"]`).checked=true;
  $("control-geometry").value=d.geometry||"depth";$("control-strength").value=d.strength??1;
  $("control-end").value=d.end_percent??0.6;$("vision-strength").value=d.image_strength??1;
  $("vision-width").value=d.width||1024;$("vision-height").value=d.height||1024;
  $("control-prompt").value=d.prompt||"";$("control-negative").value=d.negative||"";$("control-seed").value=d.seed||"";
  C.saver.setSavedHash(project.draft_hashes.control);render();}

async function followProject(){const id=localStorage.getItem("moss_studio_project");
  if(!C.project||C.project.id!==id){if(busy())throw Error("目前工作完成後再切換專案");
    await loadProject(await currentProject());}}

async function upload(slot,file){if(!file)return;
  if(file.size>20*1024**2){message("圖片需小於 20 MiB","warn");return;}
  try{await followProject();message("正在上傳…","running");
    const asset=await request(`/api/projects/${C.project.id}/assets?kind=${KIND[slot]||"input"}`,
      {method:"POST",body:file,headers:{"Content-Type":file.type||"application/octet-stream"}});
    C.project.revision=asset.project_revision;
    C.assets[slot]={asset_id:asset.id,width:asset.width,height:asset.height,inpaint_size:asset.inpaint_size};
    if(slot==="control-depth")$("control-geometry").value="upload";
    render();C.saver.schedule();message(`已放入（${asset.width}×${asset.height}）`);
  }catch(error){message(error.message+"；保留原有圖片","error");}}
// Pasted or handed-over pictures: the source in colour/depth mode, the first free reference otherwise.
function uploadToDefault(file){if(mode()!=="vision")return upload("control-source",file);
  const free=["vision-1","vision-2","vision-3","vision-4"].find(slot=>!C.assets[slot]);
  if(!free){message("四張參考圖都已放入；請先移除一張","warn");return;}
  return upload(free,file);}

function remove(slot){delete C.assets[slot];
  if(slot==="control-depth"&&$("control-geometry").value==="upload")$("control-geometry").value="depth";
  render();C.saver.schedule();}

// Colour/depth control is trained on SFT; the experimental vision mode follows the active backbone.
function payloadFor(prompt,backbone){const base={project_id:C.project.id,client_request_id:crypto.randomUUID(),
  project_revision:C.project.revision,model_artifact_id:"sft_bf16",prompt,negative_prompt:$("control-negative").value,
  seed:$("control-seed").value.trim()||null,layout:null,mask_asset_id:null,lora_stack:[]};
  if(mode()==="vision"){
    const slots=["vision-1","vision-2","vision-3","vision-4"].map(s=>C.assets[s]);
    const refs=slots.filter(Boolean);if(!refs.length)throw Error("請至少放入一張參考圖");
    const firstEmpty=slots.findIndex(s=>!s);
    if(firstEmpty!==-1&&firstEmpty<slots.findLastIndex(Boolean))
      throw Error("參考圖請從參考圖 1 開始依序放入，不要中間留空（圖號會寫入提示詞）");
    return {...base,task:"vision",profile_id:"vision_v1",model_artifact_id:backbone,width:Number($("vision-width").value),
      height:Number($("vision-height").value),references:refs.map((r,i)=>({asset_id:r.asset_id,slot:i+1})),
      control:{image_strength:Number($("vision-strength").value)}};}
  const source=C.assets["control-source"];if(!source)throw Error("請先放入來源圖");
  const geometry=$("control-geometry").value;const depth=C.assets["control-depth"];
  if(geometry==="upload"&&!depth)throw Error("選擇自備深度圖時，請先放入深度圖");
  return {...base,task:"color_depth",profile_id:"control_v1",width:source.inpaint_size[0],height:source.inpaint_size[1],
    references:[{asset_id:source.asset_id,slot:1}],
    control:{geometry,strength:Number($("control-strength").value),end_percent:Number($("control-end").value),
      depth_asset_id:geometry==="upload"?depth.asset_id:null,color_asset_id:C.assets["control-color"]?.asset_id||null}};}

async function watch(id){const token=++C.pollToken;localStorage.setItem("moss_control_job",id);
  const job=await pollJob(id,{isCurrent:()=>token===C.pollToken,onUpdate:(job,text,view)=>{
    if(job)C.active=job;setStatus("control-status",text,view);syncButtons();}});
  if(job?.status==="succeeded"){
    showResult("control",job,`種子 ${job.seed} · ${job.record.seconds.toFixed(1)} 秒${job.record.experimental?" · 實驗功能":""} · 尚未匯出專案`);
    const map=(job.record.auxiliary_assets||[])[0];const preview=$("control-map");
    if(map){preview.src=`/api/assets/${job.project_id}/${map}`;preview.hidden=false;$("control-map-label").hidden=false;}
    else{preview.hidden=true;$("control-map-label").hidden=true;}}}

async function submit(){if(C.submitting)return;
  if(busy()){message("已有工作進行中；可先準備下一份，或取消目前工作。","warn");return;}
  C.submitting=true;reveal("control-status");
  try{let payload=C.pending;
    if(!payload){await followProject();const prompt=$("control-prompt").value.trim();
      if(!prompt)throw Error("請描述要產生的畫面");await C.saver.save();payload=payloadFor(prompt,(await session()).model_artifact_id);
      C.pending=payload;localStorage.setItem("moss_control_pending",JSON.stringify(payload));}
    message("正在驗證工作…","running");const job=await request("/api/jobs",{method:"POST",body:payload});
    C.pending=null;localStorage.removeItem("moss_control_pending");C.active=job;C.project.revision=job.project_revision;watch(job.id);
  }catch(error){if(error.status===422){C.pending=null;localStorage.removeItem("moss_control_pending");}
    message(error.message+(C.pending?"；提交狀態未確認，再按產生圖片會核對同一工作。":""),error.status?"error":"warn");}
  finally{C.submitting=false;syncButtons();}}

async function cancel(){if(!C.active)return;
  try{await request(`/api/jobs/${C.active.id}/cancel`,{method:"POST"});message("已要求取消，等候引擎確認","warn");}
  catch(error){message(error.message,"error");}}

async function receive(){const picture=takeHandoff("control");if(!picture)return;
  try{await uploadToDefault(await handoffFile(picture));}catch(error){message(error.message,"error");}}

window.mossControl={
  async init(){const root=$("control-root");if(!root)return;
    if(C.bound===root){await followProject().catch(e=>message(e.message,"error"));await receive();return;}
    C.bound=root;C.session=await session();
    C.saver=draftSaver("control",{getProject:()=>C.project,capture,onState:(t)=>{$("control-save-state").textContent=t;}});
    for(const slot of SLOTS){pictureDrop($(`${slot}-drop`),$(`${slot}-file`),(file)=>upload(slot,file));$(`${slot}-remove`).onclick=()=>remove(slot);}
    onPastePicture(root,uploadToDefault);
    for(const radio of document.querySelectorAll('input[name="control-mode"]'))radio.onchange=()=>{render();C.saver.schedule();};
    for(const id of ["control-geometry","control-strength","control-end","vision-strength","vision-width","vision-height",
      "control-prompt","control-negative","control-seed"])$(id).oninput=$(id).onchange=()=>{render();C.saver.schedule();};
    $("control-submit").onclick=submit;$("control-cancel").onclick=cancel;
    try{await loadProject(await currentProject());}catch(error){message(error.message,"error");return;}
    await receive();
    const pending=localStorage.getItem("moss_control_pending");
    if(pending){C.pending=JSON.parse(pending);
      try{const found=await request(`/api/jobs/request/${C.pending.project_id}/${C.pending.client_request_id}`);
        localStorage.removeItem("moss_control_pending");C.pending=null;watch(found.id);return;}
      catch(error){message("前次提交尚未確認；按產生圖片以相同內容核對。"+error.message,"warn");return;}}
    const job=localStorage.getItem("moss_control_job");if(job)watch(job);}
};
