// Shared same-origin HTTP helpers for the tabs added after Stage 2 (edit, inpaint, control,
// models). Gradio stays a shell: every call here is authenticated HTTP, never SSE.
const state={csrf:null,session:null};
export const STAGES={created:"正在準備",validating:"正在檢查",queued:"已排隊",encoding:"正在編碼",
  sampling:"正在繪製",decoding:"正在解碼",saving:"正在保存",succeeded:"已完成",
  cancelling:"正在等候引擎取消",cancelled:"已取消",failed:"本次未完成，輸入仍保留",
  interrupted:"工作曾中斷，請先核對原紀錄"};
export const TERMINAL=new Set(["succeeded","failed","cancelled","interrupted"]);

export async function request(url,options={}){
  const headers={...(options.headers||{})};let body=options.body;
  if(body!==undefined&&!(body instanceof Blob)&&!(body instanceof ArrayBuffer)){
    headers["Content-Type"]="application/json";body=JSON.stringify(body);}
  if(options.method&&options.method!=="GET")headers["X-Moss-CSRF"]=state.csrf;
  const response=await fetch(url,{...options,body,headers,credentials:"same-origin"});
  let result;try{result=await response.json();}catch{throw Error("連線回應不完整，請先找回原工作");}
  if(!response.ok){
    const error=Error(response.status===401?"登入已失效，請重新登入":result.message||result.detail||`請求失敗 (${response.status})`);
    error.status=response.status;throw error;}
  return result;
}

// The only source of "verified / not yet verified" wording: configs/capabilities.json.
export function capabilityLabel(session,id){const c=session?.capabilities?.[id];if(!c)return "驗收狀態未知";
  const prefix=c.class==="experimental"?"實驗功能，":"";
  if(c.state==="verified"||c.state==="released")return prefix+"已通過 GPU 驗收";
  if(c.state==="blocked")return prefix+"目前停用（未通過驗收）";
  if(c.state==="disabled")return prefix+"已停用";
  return prefix+"尚未通過 GPU 驗收";}

// Re-read on every call: the active backbone can change on the model page while tabs stay open.
export async function session(){
  state.session=await request("/api/session");state.csrf=state.session.csrf;
  return state.session;
}

// The t2i tab owns project creation; other tabs follow the project it stored.
export async function currentProject(){
  const id=localStorage.getItem("moss_studio_project");
  if(!id)throw Error("請先在「文生圖與排版」分頁建立或開啟專案");
  return request("/api/projects/"+encodeURIComponent(id));
}

export function progressText(job,lastSeq){
  let progress="",seq=lastSeq;
  for(const event of job.events){seq=Math.max(seq,event.seq);
    if(event.type==="progress"&&Number.isFinite(event.payload.value)&&Number.isFinite(event.payload.max))
      progress=`，第 ${event.payload.value}/${event.payload.max} 步`;}
  return {text:(STAGES[job.status]||job.status)+progress,seq};
}

// Polls one job until it is terminal or the caller's token changes. Never resubmits.
export async function pollJob(id,{onUpdate,isCurrent}){
  let seq=0;
  while(isCurrent()){
    try{const job=await request(`/api/jobs/${encodeURIComponent(id)}?after_seq=${seq}`);
      const view=progressText(job,seq);seq=view.seq;onUpdate(job,view.text);
      if(TERMINAL.has(job.status))return job;
      await new Promise(r=>setTimeout(r,document.hidden?5000:1000));
    }catch(error){onUpdate(null,"重新連線中："+error.message+"。不會自動重送工作。");
      await new Promise(r=>setTimeout(r,3000));}
  }
  return null;
}

// Draft saving with revision CAS. A 409 caused only by another tab (this tab's draft hash
// unchanged on the server) retries once on the new revision; anything else is a real conflict.
export function draftSaver(tab,{getProject,capture,onState}){
  let chain=Promise.resolve(),timer=null,savedHash=null;
  const saver={
    setSavedHash(hash){savedHash=hash;},
    schedule(){clearTimeout(timer);timer=setTimeout(()=>saver.save().catch(e=>onState("尚未保存："+e.message)),500);},
    async save(){clearTimeout(timer);const project=getProject();const draft=JSON.parse(JSON.stringify(capture()));
      // A failed save must not poison later ones; the caller still sees this rejection.
      chain=chain.catch(()=>{}).then(async()=>{let result;
        try{result=await request(`/api/projects/${project.id}/draft`,{method:"PUT",
          body:{tab,draft,expected_revision:project.revision}});}
        catch(error){if(error.status!==409)throw error;
          const current=await request(`/api/projects/${project.id}`);
          if(current.draft_hashes[tab]!==savedHash)throw Error("此分頁草稿已在其他頁面更新，請重新整理");
          project.revision=current.revision;
          result=await request(`/api/projects/${project.id}/draft`,{method:"PUT",
            body:{tab,draft,expected_revision:project.revision}});}
        project.revision=result.revision;savedHash=result.draft_hash;
        onState("草稿已保存在本次 Colab；VM 回收後需匯出副本續編。");});
      return chain;}
  };
  return saver;
}
