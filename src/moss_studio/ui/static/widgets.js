// Presentation pieces shared by every tab: the status line, picture drop zones, the result
// panel with its hand-off to other tabs, and the project's saved-work gallery.
import {request,TERMINAL} from "/static/api.js";
const $=(id)=>document.getElementById(id);
const TITLE=document.title;
const element=(tag,props={},...children)=>{const node=Object.assign(document.createElement(tag),props);
  node.append(...children);return node;};

// ---- status line -------------------------------------------------------------------------
// view: {tone: info|running|success|warn|error, value, max, elapsed}. The tone always comes
// with text, never colour alone.
export function setStatus(id,text,view={}){const box=$(id);if(!box)return;
  box.dataset.tone=view.tone||"info";box.querySelector(".moss-status-text").textContent=text;
  box.querySelector(".moss-status-time").textContent=view.elapsed?`已 ${view.elapsed}`:"";
  const bar=box.querySelector("progress");const stepped=Number.isFinite(view.value)&&view.max>0;
  bar.hidden=view.tone!=="running";
  if(stepped){bar.max=view.max;bar.value=view.value;}else bar.removeAttribute("value");
  // Long jobs are usually watched from another browser tab: mirror progress in the title.
  if(view.tone==="running")document.title=(stepped?`(${view.value}/${view.max}) `:"… ")+TITLE;
  else if(view.tone==="success"&&document.hidden)document.title="已完成 · "+TITLE;
  else document.title=TITLE;}
document.addEventListener("visibilitychange",()=>{
  if(!document.hidden&&document.title.startsWith("已完成"))document.title=TITLE;});

// On a phone the status sits below the form; bring it into view when the user acts.
export function reveal(id){const box=$(id);if(!box)return;const r=box.getBoundingClientRect();
  if(r.top<0||r.bottom>innerHeight)box.scrollIntoView({behavior:"smooth",block:"center"});}

export const running=(job)=>!!job&&!TERMINAL.has(job.status);
// One job per tab at a time: the CTA waits, and cancel exists only while there is work to cancel.
export function setBusy(submit,cancel,busy){if(submit)submit.disabled=busy;if(cancel)cancel.hidden=!busy;}

// ---- picture input -----------------------------------------------------------------------
const picture=(files)=>[...(files||[])].find(f=>f.type.startsWith("image/"));
// `zone` becomes a click / keyboard / drag-and-drop target for the hidden file input.
export function pictureDrop(zone,input,onFile,{click=true}={}){
  if(click){zone.tabIndex=0;zone.setAttribute("role","button");zone.onclick=()=>input.click();
    zone.onkeydown=(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();input.click();}};}
  zone.ondragover=(e)=>{e.preventDefault();zone.dataset.over="1";};
  zone.ondragleave=()=>{delete zone.dataset.over;};
  zone.ondrop=(e)=>{e.preventDefault();delete zone.dataset.over;const file=picture(e.dataTransfer.files);if(file)onFile(file);};
  input.onchange=(e)=>{const file=e.target.files[0];e.target.value="";if(file)onFile(file);};}
// Ctrl+V with a picture on the clipboard, only while this tab is the visible one.
export function onPastePicture(root,onFile){document.addEventListener("paste",(e)=>{
  if(root.offsetParent===null)return;const file=picture(e.clipboardData?.files);
  if(file){e.preventDefault();onFile(file);}});}

// ---- hand-off between tabs ---------------------------------------------------------------
const TARGETS={edit:{tab:"多圖指令修圖",handle:"mossEdit",root:"edit-root",label:"修圖"},
  inpaint:{tab:"筆刷局部重繪",handle:"mossInpaint",root:"inpaint-root",label:"局部重繪"},
  control:{tab:"視覺與深度控制",handle:"mossControl",root:"control-root",label:"當控制來源"},
  hires:{tab:"模型與高解析",handle:"mossModels",root:"models-root",label:"放大"}};
let handoff=null;
// The receiving tab calls this from init(); it gets the picture at most once.
export function takeHandoff(target){if(handoff?.target!==target)return null;const taken=handoff;handoff=null;return taken;}
// Edit, inpaint and control only accept uploaded pictures (kind=input), so a result is passed
// as a file and goes through the same upload path as a picture from disk.
export async function handoffFile({projectId,assetId}){
  const response=await fetch(`/api/assets/${projectId}/${assetId}`,{credentials:"same-origin"});
  if(!response.ok)throw Error("無法讀取這張作品");return response.blob();}
function sendTo(target,projectId,assetId){const {tab,handle,root}=TARGETS[target];handoff={target,projectId,assetId};
  // Selecting a tab runs its init(); a tab that is already showing has to be told directly.
  if($(root)?.offsetParent&&window[handle]){window[handle].init();return;}
  // On narrow screens Gradio moves the tabs that do not fit into its overflow dropdown.
  const button=[...document.querySelectorAll('[role="tab"],.overflow-dropdown button')].find(b=>b.textContent.trim()===tab);
  if(button)button.click();else handoff=null;}

function actions(box,job,{seed=true}={}){const asset=job.asset_id,path=`/api/assets/${job.project_id}/${asset}`;
  const download=element("a",{className:"moss-button moss-primary",href:path,download:"",textContent:"下載圖片"});
  const full=element("a",{className:"moss-button",href:path,target:"_blank",rel:"noopener",textContent:"看原尺寸"});
  const next=element("span",{className:"moss-actions-next"},"接著做：");
  for(const [target,{label}] of Object.entries(TARGETS))next.append(element("button",{type:"button",className:"moss-button",
    textContent:label,onclick:()=>sendTo(target,job.project_id,asset)}));
  box.replaceChildren(download,full);
  if(seed&&job.seed)box.append(element("button",{type:"button",className:"moss-button",textContent:"複製種子",
    title:"貼到進階設定的種子欄，可用同一個種子重現或微調",
    onclick:async(e)=>{try{await navigator.clipboard.writeText(job.seed);e.target.textContent="已複製種子";}
      catch{e.target.textContent=`種子 ${job.seed}`;}}}));
  box.append(next);box.hidden=false;}

// Fills the markup from workbench_parts.result_panel(prefix).
export function showResult(prefix,job,summary){const asset=job.record.output_assets[0];
  const image=$(`${prefix}-result`);image.src=`/api/assets/${job.project_id}/${asset}`;image.hidden=false;
  $(`${prefix}-result-empty`).hidden=true;$(`${prefix}-result-summary`).textContent=summary;
  actions($(`${prefix}-result-actions`),{project_id:job.project_id,asset_id:asset,seed:job.seed});
  const r=image.getBoundingClientRect();if(r.top>innerHeight)image.scrollIntoView({behavior:"smooth",block:"nearest"});
  refreshGallery();}
export function clearResult(prefix){$(`${prefix}-result`).hidden=true;$(`${prefix}-result`).removeAttribute("src");
  $(`${prefix}-result-empty`).hidden=false;$(`${prefix}-result-summary`).textContent="";$(`${prefix}-result-actions`).hidden=true;}

// ---- gallery of saved work ---------------------------------------------------------------
// Loaded only when opened (history stays off the first viewport); thumbnails keep the tunnel light.
export async function refreshGallery(){const box=$("moss-gallery");if(!box||!box.open)return;
  const projectId=localStorage.getItem("moss_studio_project");if(!projectId)return;
  const grid=$("moss-gallery-grid"),status=$("moss-gallery-status"),detail=$("moss-gallery-detail");
  try{const assets=(await request(`/api/projects/${projectId}/assets`)).filter(a=>a.kind==="output").reverse();
    status.textContent=assets.length?`共 ${assets.length} 張，新的在前。這些只存在本次 Colab；要保留請下載或匯出專案。`
      :"這個專案還沒有作品。";
    $("moss-works").href=`/api/works/${projectId}.zip`;$("moss-works").hidden=!assets.length;
    if(detail.dataset.project!==projectId)detail.hidden=true;
    grid.replaceChildren(...assets.map(a=>{
      const thumb=element("img",{src:`/api/assets/${projectId}/${a.id}/thumbnail`,alt:`作品 ${a.width}×${a.height}`,loading:"lazy"});
      return element("button",{type:"button",className:"moss-thumb",title:`${a.width}×${a.height}`,onclick:()=>{
        detail.dataset.project=projectId;$("moss-gallery-image").src=`/api/assets/${projectId}/${a.id}`;
        $("moss-gallery-size").textContent=`${a.width}×${a.height}`;
        actions($("moss-gallery-actions"),{project_id:projectId,asset_id:a.id},{seed:false});detail.hidden=false;
        detail.scrollIntoView({behavior:"smooth",block:"nearest"});}},thumb);}));
  }catch(error){status.textContent=error.message;}}

let bound=false;
export function bindWorkbench(){if(bound)return;bound=true;
  $("moss-gallery")?.addEventListener("toggle",refreshGallery);
  // Ctrl/Cmd+Enter presses the visible tab's main button.
  document.addEventListener("keydown",(e)=>{if(e.key!=="Enter"||!(e.ctrlKey||e.metaKey))return;
    const cta=[...document.querySelectorAll(".moss-cta")].find(b=>b.offsetParent!==null);
    if(cta&&!cta.disabled){e.preventDefault();cta.click();}});}
