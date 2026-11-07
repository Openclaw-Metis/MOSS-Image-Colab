const svgNS = "http://www.w3.org/2000/svg";
const clone = (x) => JSON.parse(JSON.stringify(x));
const clamp = (x, low=0, high=1) => Math.min(high, Math.max(low, x));

export class LayoutCanvas {
  constructor(request, onChange, getCaption) {
    this.svg=document.getElementById("layout-canvas"); this.request=request;
    this.onChange=onChange; this.getCaption=getCaption; this.items=[]; this.history=[];
    this.width=1024; this.height=1024; this.selected=null; this.revision=0;
    const byId=(id)=>document.getElementById(id);
    byId("layout-selection").onchange=(event)=>{this.selected=event.target.value;this.render();};
    byId("layout-add-text").onclick=()=>this.add("text");
    byId("layout-add-object").onclick=()=>this.add("object");
    byId("layout-delete").onclick=()=>this.remove();
    byId("layout-undo").onclick=()=>{if(this.history.length){this.items=this.history.pop();this.commit(false);}};
    byId("layout-apply-json").onclick=()=>this.applyJSON();
    for(const id of ["layout-kind","layout-caption","layout-text"]){
      const update=()=>{const item=this.current();if(!item)return;this.remember();
        item.label=byId("layout-kind").value;item.caption=byId("layout-caption").value;
        if(item.label==="text")item.text=byId("layout-text").value;else delete item.text;
        this.commit(false);};
      byId(id)[id==="layout-kind"?"onchange":"oninput"]=update;
    }
    for(const [index,id] of ["x0","y0","x1","y1"].entries()){
      byId("layout-"+id).oninput=(event)=>{const item=this.current();if(!item)return;
        const next=[...item.normalized_bbox];next[index]=Number(event.target.value);
        if(!this.valid(next)){this.hint("座標必須在 0～1 之間且框有面積");return;}
        this.remember();item.normalized_bbox=next;this.commit(false);};
    }
    this.svg.onpointerdown=(event)=>this.down(event);
    this.svg.onpointermove=(event)=>this.move(event);
    this.svg.onpointerup=()=>this.up(); this.svg.onpointercancel=()=>this.up();
    this.svg.onkeydown=(event)=>{if(["Delete","Backspace"].includes(event.key)){
      event.preventDefault();this.remove();}};
    this.render();
  }
  current(){return this.items.find(x=>x.id===this.selected);}
  hint(message){document.getElementById("layout-hint").textContent=message;}
  valid(b){return b.length===4&&b.every(Number.isFinite)&&b[0]>=0&&b[1]>=0&&b[2]<=1&&b[3]<=1&&b[0]<b[2]&&b[1]<b[3];}
  remember(){this.history.push(clone(this.items));if(this.history.length>50)this.history.shift();}
  point(event){const p=this.svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;
    const local=p.matrixTransform(this.svg.getScreenCTM().inverse());
    return [clamp(local.x/this.width),clamp(local.y/this.height)];}
  setSize(width,height){this.width=width;this.height=height;this.render();}
  setItems(items){this.items=clone(items||[]);this.selected=null;this.revision++;this.render();}
  add(label, bbox=[.12,.12,.88,.27]){if(this.items.length>=32){this.hint("最多 32 個框");return;}
    this.remember();const item={id:crypto.randomUUID(),label,caption:label==="text"?"標題":"主體",
      normalized_bbox:bbox,z_order:this.items.length};if(label==="text")item.text="山間慢旅";
    this.items.push(item);this.selected=item.id;this.commit(false);}
  remove(){if(!this.current())return;this.remember();
    this.items=this.items.filter(x=>x.id!==this.selected);this.selected=null;this.commit(false);}
  down(event){if(event.button!==0)return;const start=this.point(event);
    const id=event.target.dataset.id;const item=this.items.find(x=>x.id===id);
    if(!item&&this.items.length>=32){this.hint("最多 32 個框");return;}
    this.svg.focus({preventScroll:true});this.before=clone(this.items);this.drag={start,mode:event.target.dataset.handle||"move"};
    if(item){this.selected=id;this.drag.bbox=[...item.normalized_bbox];}
    else {if(this.items.length>=32)return;
      const label=document.getElementById("layout-kind").value;
      const added={id:crypto.randomUUID(),label,caption:label==="text"?"文字":"物件",
        normalized_bbox:[...start,...start],z_order:this.items.length};
      if(label==="text")added.text="新標題";this.items.push(added);this.selected=added.id;
      this.drag.mode="new";}
    this.svg.setPointerCapture(event.pointerId);this.render();}
  move(event){if(!this.drag)return;const end=this.point(event);const item=this.current();if(!item)return;
    const {start,mode,bbox}=this.drag;
    if(mode==="new")item.normalized_bbox=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];
    else if(mode==="start")item.normalized_bbox=[clamp(end[0],0,bbox[2]-.0001),clamp(end[1],0,bbox[3]-.0001),bbox[2],bbox[3]];
    else if(mode==="end")item.normalized_bbox=[bbox[0],bbox[1],clamp(end[0],bbox[0]+.0001,1),clamp(end[1],bbox[1]+.0001,1)];
    else {const dx=clamp(end[0]-start[0],-bbox[0],1-bbox[2]);const dy=clamp(end[1]-start[1],-bbox[1],1-bbox[3]);
      item.normalized_bbox=[bbox[0]+dx,bbox[1]+dy,bbox[2]+dx,bbox[3]+dy];}
    this.render(false);}
  up(){if(!this.drag)return;this.drag=null;const item=this.current();
    if(!item||!this.valid(item.normalized_bbox)){this.items=this.before;this.render();return;}
    this.history.push(this.before);if(this.history.length>50)this.history.shift();this.commit(false);}
  commit(){this.revision++;this.render();this.onChange();
    const overlap=this.items.some((a,i)=>this.items.slice(i+1).some(b=>{
      const x=a.normalized_bbox,y=b.normalized_bbox;
      return x[0]<y[2]&&y[0]<x[2]&&x[1]<y[3]&&y[1]<x[3];}));
    this.hint(overlap?"框有重疊，已保留；請留意文字可讀性。":"可拖曳移動框，拖圓點調整大小。");}
  json(){return {summary:{meta:["poster"],canvas:"single",caption:this.captionOverride||this.getCaption()||"創作畫面"},
    items:this.items.map(item=>{const [x0,y0,x1,y1]=item.normalized_bbox;
      const result={label:item.label,caption:item.caption,
        bbox:[Math.round(y0*this.height)-this.height/2,Math.round(x0*this.width)-this.width/2,
              Math.round(y1*this.height)-this.height/2,Math.round(x1*this.width)-this.width/2]};
      if(item.label==="text")result.text=item.text;return result;}),
    bbox_coord_space:"abs_centralized",bbox_format:"yxyx"};}
  async applyJSON(){const revision=this.revision;
    try{const parsed=await this.request("/api/layout/validate",{method:"POST",body:{
      layout:document.getElementById("layout-json").value,width:this.width,height:this.height,
      previous_items:this.items}});
      if(this.revision!==revision)throw Error("畫布已更新，請重新檢查 JSON");
      this.remember();this.items=parsed.items;this.captionOverride=parsed.layout.summary.caption;
      this.commit();this.hint("已套用有效 JSON");
    }catch(error){this.hint(error.message+"；保留上一次有效畫布");}}
  render(syncFields=true){this.svg.setAttribute("viewBox",`0 0 ${this.width} ${this.height}`);
    this.svg.replaceChildren();const bg=document.createElementNS(svgNS,"rect");
    bg.setAttribute("width",this.width);bg.setAttribute("height",this.height);
    bg.setAttribute("fill","#fff");bg.style.pointerEvents="none";this.svg.append(bg);
    for(const item of this.items){const [x0,y0,x1,y1]=item.normalized_bbox;
      const rect=document.createElementNS(svgNS,"rect");rect.dataset.id=item.id;
      for(const [k,v] of Object.entries({x:x0*this.width,y:y0*this.height,width:(x1-x0)*this.width,
        height:(y1-y0)*this.height,fill:item.label==="text"?"#dbeafe":"#ccfbf1",stroke:item.id===this.selected?"#1d4ed8":"#64748b","stroke-width":3}))rect.setAttribute(k,v);
      rect.style.cursor="move";this.svg.append(rect);const label=document.createElementNS(svgNS,"text");
      label.setAttribute("x",x0*this.width+10);label.setAttribute("y",y0*this.height+28);
      label.setAttribute("font-size",22);label.setAttribute("fill","#0f172a");label.style.pointerEvents="none";
      label.textContent=item.label==="text"?item.text:item.caption;this.svg.append(label);
      if(item.id===this.selected)for(const [handle,x,y] of [["start",x0,y0],["end",x1,y1]]){
        const c=document.createElementNS(svgNS,"circle");c.dataset.id=item.id;c.dataset.handle=handle;
        for(const [k,v] of Object.entries({cx:x*this.width,cy:y*this.height,r:10,fill:"#1d4ed8"}))c.setAttribute(k,v);
        c.style.cursor="nwse-resize";this.svg.append(c);}
    }
    if(syncFields){const selection=document.getElementById("layout-selection");selection.replaceChildren();
      const empty=document.createElement("option");empty.value="";empty.textContent="未選取";selection.append(empty);
      this.items.forEach((item,index)=>{const option=document.createElement("option");option.value=item.id;
        option.textContent=`${index+1}. ${item.label==="text"?item.text:item.caption}`;selection.append(option);});
      selection.value=this.selected||"";
      const item=this.current();if(item){document.getElementById("layout-kind").value=item.label;
      document.getElementById("layout-caption").value=item.caption;
      document.getElementById("layout-text").value=item.text||"";
      document.getElementById("layout-text").disabled=item.label!=="text";
      ["x0","y0","x1","y1"].forEach((id,i)=>document.getElementById("layout-"+id).value=item.normalized_bbox[i].toFixed(4));}
      document.getElementById("layout-json").value=JSON.stringify(this.json(),null,2);}
  }
}
