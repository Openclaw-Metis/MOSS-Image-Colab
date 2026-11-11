import {request,session,currentProject,pollJob,draftSaver,capabilityLabel} from "/static/api.js";
import {setStatus,setBusy,running,reveal,pictureDrop,onPastePicture,showResult,takeHandoff,handoffFile} from "/static/widgets.js";
const $=(id)=>document.getElementById(id);
// The mask canvas lives at the working size (≈1 MP) so undo snapshots stay bounded.
const P={project:null,source:null,mask:null,ctx:null,undo:[],mode:"brush",last:null,active:null,
  pollToken:0,submitting:false,pending:null,saver:null,bound:null,maskAssetId:null};
const message=(text,tone="info")=>setStatus("inpaint-status",text,{tone});
const busy=()=>running(P.active);
const syncButtons=()=>setBusy($("inpaint-submit"),$("inpaint-cancel"),busy());

function capture(){return {source:P.source,prompt:$("inpaint-prompt").value,negative:$("inpaint-negative").value,
  seed:$("inpaint-seed").value,denoise:Number($("inpaint-denoise").value),
  edge_softness:Number($("inpaint-softness").value),mask_asset_id:P.maskAssetId};}

function featherText(){const soft=Number($("inpaint-softness").value);
  const size=P.source?.inpaint_size;const px=size?Math.round(0.1*Math.min(...size)*soft):null;
  $("inpaint-softness-value").textContent=px===null?soft.toFixed(2):`${soft.toFixed(2)}（約 ${px} px）`;
  $("inpaint-denoise-value").textContent=Number($("inpaint-denoise").value).toFixed(2);}

function coverage(){if(!P.mask)return {any:false,all:false};
  const data=P.ctx.getImageData(0,0,P.mask.width,P.mask.height).data;let any=false,all=true;
  for(let i=3;i<data.length;i+=4){if(data[i]>127)any=true;else all=false;if(any&&!all)break;}
  return {any,all};}

function redraw(){const ov=$("inpaint-overlay");const c=ov.getContext("2d");c.clearRect(0,0,ov.width,ov.height);
  if(!P.mask)return;
  if($("inpaint-preview").checked){c.fillStyle="#000";c.fillRect(0,0,ov.width,ov.height);
    c.drawImage(P.mask,0,0,ov.width,ov.height);}
  else{c.drawImage(P.mask,0,0,ov.width,ov.height);c.globalCompositeOperation="source-in";
    c.fillStyle="rgba(29,78,216,0.5)";c.fillRect(0,0,ov.width,ov.height);c.globalCompositeOperation="source-over";}
  const {all}=coverage();$("inpaint-full-box").hidden=!all;}

function place(){const img=$("inpaint-source"),ov=$("inpaint-overlay");if(img.hidden)return;
  ov.width=img.clientWidth;ov.height=img.clientHeight;
  Object.assign(ov.style,{left:img.offsetLeft+"px",top:img.offsetTop+"px",width:img.clientWidth+"px",height:img.clientHeight+"px"});
  redraw();}

function newMask(){const [w,h]=P.source.inpaint_size;P.mask=document.createElement("canvas");
  P.mask.width=w;P.mask.height=h;P.ctx=P.mask.getContext("2d",{willReadFrequently:true});P.undo=[];}

async function showSource(){const img=$("inpaint-source");
  $("inpaint-pick").textContent=P.source?"更換來源圖":"選擇來源圖";
  if(!P.source){img.hidden=true;$("inpaint-overlay").hidden=true;$("inpaint-empty").hidden=false;P.mask=null;return;}
  await new Promise((resolve)=>{img.onload=resolve;img.onerror=resolve;
    img.src=`/api/assets/${P.project.id}/${P.source.asset_id}`;img.hidden=false;});
  $("inpaint-empty").hidden=true;$("inpaint-overlay").hidden=false;newMask();
  if(P.maskAssetId){const saved=new Image();
    await new Promise((resolve)=>{saved.onload=resolve;saved.onerror=resolve;
      saved.src=`/api/assets/${P.project.id}/${P.maskAssetId}`;});
    if(saved.naturalWidth)P.ctx.drawImage(saved,0,0,P.mask.width,P.mask.height);}
  place();featherText();}

async function loadProject(project){P.project=project;const d=project.drafts.inpaint||{};
  P.source=d.source||null;P.maskAssetId=d.mask_asset_id||null;
  $("inpaint-prompt").value=d.prompt||"";$("inpaint-negative").value=d.negative||"";$("inpaint-seed").value=d.seed||"";
  $("inpaint-denoise").value=d.denoise??1;$("inpaint-softness").value=d.edge_softness??0.15;
  P.saver.setSavedHash(project.draft_hashes.inpaint);await showSource();featherText();}

async function followProject(){const id=localStorage.getItem("moss_studio_project");
  if(!P.project||P.project.id!==id){if(busy())throw Error("目前工作完成後再切換專案");
    await loadProject(await currentProject());}}

async function uploadSource(file){if(!file)return;
  if(file.size>20*1024**2){message("圖片需小於 20 MiB","warn");return;}
  try{await followProject();message("正在上傳來源圖…","running");
    const asset=await request(`/api/projects/${P.project.id}/assets?kind=input`,
      {method:"POST",body:file,headers:{"Content-Type":file.type||"application/octet-stream"}});
    P.project.revision=asset.project_revision;
    P.source={asset_id:asset.id,width:asset.width,height:asset.height,inpaint_size:asset.inpaint_size};
    P.maskAssetId=null;await showSource();P.saver.schedule();
    message(`來源圖已放入（${asset.width}×${asset.height}，重繪尺寸 ${asset.inpaint_size.join("×")}）。請塗抹要修改的區域。`);
  }catch(error){message(error.message+"；保留原有圖片","error");}}

function point(event){const r=$("inpaint-overlay").getBoundingClientRect();
  return [(event.clientX-r.left)*P.mask.width/r.width,(event.clientY-r.top)*P.mask.height/r.height,P.mask.width/r.width];}
function paint(from,to,scale){const c=P.ctx;c.globalCompositeOperation=P.mode==="eraser"?"destination-out":"source-over";
  c.strokeStyle="#fff";c.fillStyle="#fff";c.lineCap="round";c.lineJoin="round";
  c.lineWidth=Number($("inpaint-size").value)*scale;c.beginPath();c.moveTo(from[0],from[1]);c.lineTo(to[0],to[1]);c.stroke();
  c.globalCompositeOperation="source-over";}
function remember(){P.undo.push(P.ctx.getImageData(0,0,P.mask.width,P.mask.height));if(P.undo.length>15)P.undo.shift();}

function bindCanvas(){const ov=$("inpaint-overlay");
  ov.onpointerdown=(e)=>{if(!P.mask||e.button!==0)return;remember();ov.setPointerCapture(e.pointerId);
    const p=point(e);P.last=p;paint(p,p,p[2]);redraw();};
  ov.onpointermove=(e)=>{showCursor(e);if(!P.last)return;const p=point(e);paint(P.last,p,p[2]);P.last=p;redraw();};
  ov.onpointerup=ov.onpointercancel=()=>{if(!P.last)return;P.last=null;P.maskAssetId=null;P.saver.schedule();};
  ov.onpointerleave=()=>{$("inpaint-cursor").hidden=true;};
  window.addEventListener("resize",place);}

// The brush outline at its real on-screen size; the system cursor is hidden over the canvas.
function showCursor(event){const ring=$("inpaint-cursor"),stage=$("inpaint-stage").getBoundingClientRect();
  const size=Number($("inpaint-size").value);ring.hidden=false;
  Object.assign(ring.style,{width:size+"px",height:size+"px",left:event.clientX-stage.left-size/2+"px",top:event.clientY-stage.top-size/2+"px"});}

// B / E pick the tool, [ and ] resize the brush, Ctrl+Z undoes; never while typing in a field.
function shortcuts(event){if($("inpaint-root").offsetParent===null||!P.mask)return;
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)&&event.target.type!=="range"&&event.target.type!=="checkbox")return;
  const key=event.key.toLowerCase();
  if((event.ctrlKey||event.metaKey)&&key==="z"){event.preventDefault();undo();P.saver.schedule();}
  else if(event.ctrlKey||event.metaKey||event.altKey)return;
  else if(key==="b")setMode("brush");else if(key==="e")setMode("eraser");
  else if(key==="["||key==="]"){const size=$("inpaint-size");
    size.value=Math.min(256,Math.max(4,Number(size.value)+(key==="]"?8:-8)));}}

function setMode(mode){P.mode=mode;$("inpaint-brush").setAttribute("aria-pressed",mode==="brush");
  $("inpaint-eraser").setAttribute("aria-pressed",mode==="eraser");}
function undo(){if(!P.undo.length)return;P.ctx.putImageData(P.undo.pop(),0,0);P.maskAssetId=null;redraw();}
function clear(){if(!P.mask)return;remember();P.ctx.clearRect(0,0,P.mask.width,P.mask.height);P.maskAssetId=null;redraw();}
function invert(){if(!P.mask)return;remember();const image=P.ctx.getImageData(0,0,P.mask.width,P.mask.height);
  for(let i=0;i<image.data.length;i+=4){image.data[i]=image.data[i+1]=image.data[i+2]=255;image.data[i+3]=255-image.data[i+3];}
  P.ctx.putImageData(image,0,0);P.maskAssetId=null;redraw();}

async function watch(id){const token=++P.pollToken;localStorage.setItem("moss_inpaint_job",id);
  const job=await pollJob(id,{isCurrent:()=>token===P.pollToken,onUpdate:(job,text,view)=>{
    if(job)P.active=job;setStatus("inpaint-status",text,view);syncButtons();}});
  if(job?.status==="succeeded"){showResult("inpaint",job,
      `種子 ${job.seed} · ${job.record.seconds.toFixed(1)} 秒 · 柔邊 ${job.record.feather_px} px · 未塗抹區域保留原圖 · 尚未匯出專案`);
    bindCompare(job);}}

// Hold to flip the result back to the picture that job started from (same working size).
function bindCompare(job){const button=$("inpaint-compare"),image=$("inpaint-result");
  const result=`/api/assets/${job.project_id}/${job.record.output_assets[0]}`;
  const before=`/api/assets/${job.project_id}/${job.record.source_asset_id}`;
  button.hidden=!job.record.source_asset_id;
  const show=(source)=>()=>{if(image.src.endsWith(result)||image.src.endsWith(before))image.src=source;};
  button.onpointerdown=show(before);button.onpointerup=button.onpointerleave=button.onblur=show(result);
  button.onkeydown=(e)=>{if(e.key===" "||e.key==="Enter")show(before)();};button.onkeyup=show(result);}

async function submit(){if(P.submitting)return;
  if(busy()){message("已有重繪工作進行中；可先準備下一份，或取消目前工作。","warn");return;}
  P.submitting=true;reveal("inpaint-status");
  try{let payload=P.pending;
    if(!payload){await followProject();
      if(!P.source)throw Error("請先放入來源圖");
      const {any,all}=coverage();if(!any)throw Error("請先塗抹要修改的區域");
      if(all&&!$("inpaint-full").checked)throw Error("遮罩涵蓋整張圖；請勾選「確認整張重繪」");
      const prompt=$("inpaint-prompt").value.trim();if(!prompt)throw Error("請描述塗抹區域要畫成什麼");
      if(!P.maskAssetId){message("正在上傳遮罩…","running");
        const blob=await new Promise(resolve=>P.mask.toBlob(resolve,"image/png"));
        const mask=await request(`/api/projects/${P.project.id}/assets?kind=mask`,
          {method:"POST",body:blob,headers:{"Content-Type":"image/png"}});
        P.project.revision=mask.project_revision;P.maskAssetId=mask.id;}
      await P.saver.save();const backbone=(await session()).model_artifact_id;
      payload={project_id:P.project.id,client_request_id:crypto.randomUUID(),project_revision:P.project.revision,
        task:"inpaint",profile_id:"inpaint_v1",model_artifact_id:backbone,prompt,negative_prompt:$("inpaint-negative").value,
        width:P.source.inpaint_size[0],height:P.source.inpaint_size[1],seed:$("inpaint-seed").value.trim()||null,
        references:[{asset_id:P.source.asset_id,slot:1}],layout:null,mask_asset_id:P.maskAssetId,
        control:{denoise:Number($("inpaint-denoise").value),edge_softness:Number($("inpaint-softness").value),
          confirm_full:$("inpaint-full").checked&&all},lora_stack:[]};
      P.pending=payload;localStorage.setItem("moss_inpaint_pending",JSON.stringify(payload));}
    message("正在驗證工作…","running");const job=await request("/api/jobs",{method:"POST",body:payload});
    P.pending=null;localStorage.removeItem("moss_inpaint_pending");P.active=job;P.project.revision=job.project_revision;watch(job.id);
  }catch(error){if(error.status===422){P.pending=null;localStorage.removeItem("moss_inpaint_pending");}
    message(error.message+(P.pending?"；提交狀態未確認，再按開始重繪會核對同一工作。":""),error.status?"error":"warn");}
  finally{P.submitting=false;syncButtons();}}

async function cancel(){if(!P.active)return;
  try{await request(`/api/jobs/${P.active.id}/cancel`,{method:"POST"});message("已要求取消，等候引擎確認","warn");}
  catch(error){message(error.message,"error");}}

async function receive(){const picture=takeHandoff("inpaint");if(!picture)return;
  try{await uploadSource(await handoffFile(picture));}catch(error){message(error.message,"error");}}

window.mossInpaint={
  async init(){const root=$("inpaint-root");if(!root)return;
    if(P.bound===root){await followProject().catch(e=>message(e.message,"error"));await receive();place();return;}
    P.bound=root;const s=await session();
    $("inpaint-summary").textContent=`${s.model_artifact_id==="base_bf16"?"Base":"SFT"} bf16 · 30 步 · 遮罩 latent 重繪＋柔邊合成 · ${capabilityLabel(s,"masked_inpaint")}`;
    P.saver=draftSaver("inpaint",{getProject:()=>P.project,capture,onState:(t)=>{$("inpaint-save-state").textContent=t;}});
    pictureDrop($("inpaint-empty"),$("inpaint-file"),uploadSource);
    pictureDrop($("inpaint-stage"),$("inpaint-file"),uploadSource,{click:false});
    $("inpaint-pick").onclick=()=>$("inpaint-file").click();onPastePicture(root,uploadSource);
    document.addEventListener("keydown",shortcuts);
    $("inpaint-brush").onclick=()=>setMode("brush");$("inpaint-eraser").onclick=()=>setMode("eraser");
    $("inpaint-undo").onclick=undo;$("inpaint-clear").onclick=clear;$("inpaint-invert").onclick=invert;
    $("inpaint-preview").onchange=redraw;$("inpaint-submit").onclick=submit;$("inpaint-cancel").onclick=cancel;
    for(const id of ["inpaint-denoise","inpaint-softness"])$(id).oninput=()=>{featherText();P.saver.schedule();};
    for(const id of ["inpaint-prompt","inpaint-negative","inpaint-seed"])$(id).oninput=()=>P.saver.schedule();
    bindCanvas();
    try{await loadProject(await currentProject());}catch(error){message(error.message,"error");return;}
    await receive();
    const pending=localStorage.getItem("moss_inpaint_pending");
    if(pending){P.pending=JSON.parse(pending);
      try{const found=await request(`/api/jobs/request/${P.pending.project_id}/${P.pending.client_request_id}`);
        localStorage.removeItem("moss_inpaint_pending");P.pending=null;watch(found.id);return;}
      catch(error){message("前次提交尚未確認；按開始重繪以相同內容核對。"+error.message,"warn");return;}}
    const job=localStorage.getItem("moss_inpaint_job");if(job)watch(job);}
};
