import {LayoutCanvas} from "/static/layout.js";
const $=(id)=>document.getElementById(id);
const stages={created:"正在準備",validating:"正在檢查",queued:"已排隊",encoding:"正在編碼",
  sampling:"正在繪製",decoding:"正在解碼",saving:"正在保存",succeeded:"已完成",
  cancelling:"正在等候引擎取消",cancelled:"已取消",failed:"本次未完成，輸入仍保留",
  interrupted:"工作曾中斷，請先核對原紀錄"};
const S={project:null,form:null,csrf:null,saving:Promise.resolve(),timer:null,active:null,
  conflict:false,submitting:false,pollToken:0,lastSeq:0,dirty:false,hasResult:false,view:"result",pending:null};
const active=()=>S.active&&!['succeeded','failed','cancelled','interrupted'].includes(S.active.status);
const message=(text)=>{$("moss-status").textContent=text;};
const defaults=["","",1024,1024,"",false];
async function request(url,options={}){
  const headers={...(options.headers||{})};
  if(options.body!==undefined){headers["Content-Type"]="application/json";options.body=JSON.stringify(options.body);}
  if(options.method&&options.method!=="GET")headers["X-Moss-CSRF"]=S.csrf;
  const response=await fetch(url,{...options,headers,credentials:"same-origin"});
  let result;try{result=await response.json();}catch{throw Error("連線回應不完整，請先找回原工作");}
  if(!response.ok){
    const error=Error(response.status===401?"登入已失效，請重新登入":result.message||result.detail||`請求失敗 (${response.status})`);
    error.status=response.status;throw error;}
  return result;
}
function capture(){const [prompt,negative,width,height,seed,layout]=S.form||defaults;
  return {prompt,negative,width:S.canvas.width,height:S.canvas.height,seed,layout_enabled:layout,layout_items:S.canvas.items,
    layout_caption:S.canvas.captionOverride||null};}
async function save(){if(S.conflict)throw Error("專案版本衝突，請重新載入或另存草稿");
  const draft=JSON.parse(JSON.stringify(capture()));
  const projectId=S.project.id;
  S.saving=S.saving.then(async()=>{let result;
    if(S.project.id!==projectId)throw Error("專案已切換，舊草稿未覆寫新專案");
    try{result=await request(`/api/projects/${S.project.id}/draft`,{
      method:"PUT",body:{draft,expected_revision:S.project.revision}});}
    catch(error){if(error.status!==409)throw error;
      const current=await request(`/api/projects/${S.project.id}`);
      if(current.draft_hash!==S.savedHash)throw error;
      S.project.revision=current.revision;
      result=await request(`/api/projects/${S.project.id}/draft`,{
        method:"PUT",body:{draft,expected_revision:S.project.revision}});
    }
    S.project.revision=result.revision;S.savedHash=result.draft_hash;
    S.dirty=JSON.stringify(capture())!==JSON.stringify(draft);
    $("moss-save-state").textContent=S.dirty?"仍有變更正在保存…":"草稿已保存在本次 Colab；VM 回收後需匯出副本續編。";
  });
  try{await S.saving;}catch(error){S.conflict=true;$("moss-save-state").textContent="尚未保存："+error.message;throw error;}
}
function scheduleSave(){S.dirty=true;clearTimeout(S.timer);if(S.project&&!S.submitting)
  S.timer=setTimeout(()=>save().catch(e=>message(e.message)),500);}
function setForm(values){const old=S.form;S.form=values;
  if(old&&old[0]!==values[0]){S.canvas.captionOverride=null;S.canvas.revision++;S.canvas.render();}
  if(!old)S.canvas.setSize(Number(values[2]),Number(values[3]));
  $("moss-confirm-size").hidden=S.canvas.width===Number(values[2])&&S.canvas.height===Number(values[3]);
  if(!old||old[5]!==values[5])S.view=values[5]?"layout":"result";
  showView(S.view);
}
function showView(view){S.view=view;const layout=!!S.form?.[5];
  $("layout-workbench").style.display=layout&&view==="layout"?"block":"none";
  $("moss-result-panel").style.display=layout&&view==="layout"?"none":"block";
  $("moss-view-controls").style.display=layout?"block":"none";
  $("moss-view-result").disabled=!S.hasResult;}
async function loadProject(project){S.project=project;S.savedHash=project.draft_hash;S.conflict=false;
  const d=project.drafts.t2i;const values=[d.prompt||"",d.negative||"",d.width||1024,d.height||1024,d.seed||"",!!d.layout_enabled];
  S.canvas.setItems(d.layout_items||[]);S.canvas.captionOverride=d.layout_caption||null;S.form=null;setForm(values);
  $("moss-project").textContent=project.name;return values;}
async function poll(id){const token=++S.pollToken;S.lastSeq=0;
  while(token===S.pollToken){
    try{const job=await request(`/api/jobs/${encodeURIComponent(id)}?after_seq=${S.lastSeq}`);
      S.active=job;if(S.project.id!==job.project_id)return;
      if(job.draft_hash===S.savedHash)S.project.revision=job.project_revision;
      let progress="";for(const event of job.events){S.lastSeq=Math.max(S.lastSeq,event.seq);
        if(event.type==="progress"&&Number.isFinite(event.payload.value)&&Number.isFinite(event.payload.max))
          progress=`，第 ${event.payload.value}/${event.payload.max} 步`;}
      message((stages[job.status]||job.status)+progress);
      if(job.status==="succeeded"){
        const asset=job.record.output_assets[0];const path=`/api/assets/${job.project_id}/${asset}`;
        $("moss-result").src=path;$("moss-result").hidden=false;
        S.hasResult=true;$("moss-empty").style.display="none";showView("result");
        $("moss-download").href=path;$("moss-download").hidden=false;
        $("moss-works").href=`/api/works/${job.project_id}.zip`;$("moss-works").hidden=false;
        $("moss-result-summary").textContent=`種子 ${job.seed} · ${job.record.seconds.toFixed(1)} 秒 · 工作流 ${job.record.workflow_hash.slice(0,12)} · 本地已保存，尚未匯出專案`;
        return;
      }
      if(["failed","cancelled","interrupted"].includes(job.status))return;
      await new Promise(resolve=>setTimeout(resolve,document.hidden?5000:1000));
    }catch(error){message("重新連線中："+error.message+"。不會自動重送工作。");
      await new Promise(resolve=>setTimeout(resolve,3000));}
  }
}
window.mossStudio={
  async init(){const session=await request("/api/session");S.csrf=session.csrf;S.session=session;
    $("moss-edit-layout").onclick=()=>showView("layout");
    $("moss-view-result").onclick=()=>showView("result");
    $("moss-confirm-size").onclick=()=>{S.canvas.setSize(Number(S.form[2]),Number(S.form[3]));
      $("moss-confirm-size").hidden=true;scheduleSave();};
    S.canvas=new LayoutCanvas(request,scheduleSave,()=>S.form?.[0]||"");
    const runtime=await request("/api/runtime");const gpu=runtime.gpus[0];
    $("moss-runtime").textContent=`${gpu?gpu.name:"未偵測到 GPU"} · 系統 RAM ${(runtime.ram_total_bytes/1024**3).toFixed(1)} GiB · 開發驗證中`;
    let project;const id=localStorage.getItem("moss_studio_project");
    if(id)project=await request("/api/projects/"+encodeURIComponent(id));
    else{project=await request("/api/projects",{method:"POST",body:{name:"未命名創作"}});localStorage.setItem("moss_studio_project",project.id);}
    const values=await loadProject(project);
    const pending=localStorage.getItem("moss_studio_pending");
    if(pending){S.pending=JSON.parse(pending);
      try{const found=await request(`/api/jobs/request/${S.pending.project_id}/${S.pending.client_request_id}`);
        localStorage.setItem("moss_studio_job",found.id);localStorage.removeItem("moss_studio_pending");S.pending=null;}
      catch(error){message("前次提交尚未確認；按產生圖片以相同內容核對。"+error.message);return values;}}
    const job=localStorage.getItem("moss_studio_job");if(job)poll(job);return values;
  },
  touch(values){if(!S.canvas||!S.project)return;setForm(values);if(values[5])showView("layout");scheduleSave();},
  async submit(values){if(S.submitting)return;
    if(active()){message("已有工作進行中；可編輯下一份草稿，或取消目前工作。");return;}
    S.submitting=true;
    try{let payload=S.pending;
      if(!payload){setForm(values);
      if(!$("moss-confirm-size").hidden)throw Error("請先確認尺寸變更，再產生圖片");
      clearTimeout(S.timer);await save();
      const [prompt,negative,width,height,seed,layout]=values;
      payload={project_id:S.project.id,client_request_id:crypto.randomUUID(),project_revision:S.project.revision,
        task:layout?"layout":"t2i",profile_id:S.session.profile_id,model_artifact_id:S.session.model_artifact_id,
        prompt,negative_prompt:negative,width:Number(width),height:Number(height),seed:seed.trim()||null,
        references:[],layout:layout?S.canvas.json():null,mask_asset_id:null,control:null,lora_stack:[]};
      S.pending=payload;localStorage.setItem("moss_studio_pending",JSON.stringify(payload));}
      message("正在驗證工作…");const job=await request("/api/jobs",{method:"POST",body:payload});
      S.pending=null;localStorage.removeItem("moss_studio_pending");S.active=job;
      S.project.revision=job.project_revision;localStorage.setItem("moss_studio_job",job.id);poll(job.id);
    }catch(error){if(error.status===422){S.pending=null;localStorage.removeItem("moss_studio_pending");}
      message(error.message+(S.pending?"；提交狀態未確認，再按產生圖片會核對相同工作，不會建立新識別碼。":""));
    }finally{S.submitting=false;if(S.dirty)scheduleSave();}
  },
  async cancel(){if(!S.active)return;try{await request(`/api/jobs/${S.active.id}/cancel`,{method:"POST"});
    message("已要求取消，等候引擎確認");}catch(error){message(error.message);}},
  async newProject(){if(active()||S.pending){
      message("請先等目前工作完成或取消，再切換專案");return S.form;}
    clearTimeout(S.timer);await save();const project=await request("/api/projects",{method:"POST",body:{name:"新創作"}});
    localStorage.setItem("moss_studio_project",project.id);localStorage.removeItem("moss_studio_job");
    S.active=null;S.pollToken++;S.hasResult=false;$("moss-empty").style.display="flex";
    $("moss-result").hidden=true;$("moss-download").hidden=true;$("moss-works").hidden=true;
    message("新專案已建立，請輸入創作內容");return loadProject(project);
  }
};
