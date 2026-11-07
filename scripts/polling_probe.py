"""Stage 1 real GPU/Gradio transport probe without SSE.

The Gradio controls invoke only client-side JS. Authenticated same-origin HTTP
handles submission, polling, cancellation and downloads. Not a product release.
"""

import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request as URLRequest
from urllib.request import urlopen

import gradio as gr
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from PIL import Image, ImageOps

ROOT = Path(os.environ.get("MOSS_PROBE_ROOT", "/content/moss-stage1"))
OUT = ROOT / "probe_outputs"
OUT.mkdir(exist_ok=True, mode=0o700)
CACHE = Path(os.environ["GRADIO_TEMP_DIR"]).resolve()
PASSWORD = os.environ.pop("MOSS_PROBE_PASSWORD", "")
if len(PASSWORD) < 24:
    raise RuntimeError("Set a high-entropy MOSS_PROBE_PASSWORD in process memory")
SESSION, CSRF = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1)
JOBS = {}
REQUESTS = {}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def authenticated(request):
    return hmac.compare_digest(request.cookies.get("moss_session", ""), SESSION)


@app.middleware("http")
async def auth_boundary(request, call_next):
    if request.url.path not in {"/login", "/favicon.ico"} and not authenticated(request):
        if request.url.path in {"/", "/studio", "/studio/"}:
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/login":
        origin = request.headers.get("origin")
        if origin and origin not in {
            f"https://{request.headers.get('host')}",
            f"http://{request.headers.get('host')}",
        }:
            return JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
        if request.url.path.startswith("/api/") and not hmac.compare_digest(
            request.headers.get("x-moss-csrf", ""), CSRF
        ):
            return JSONResponse({"detail": "csrf required"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


LOGIN = """<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>MOSS Stage 1 登入</title><style>body{font:17px system-ui;max-width:440px;
margin:15vh auto;background:#f8fafc;color:#0f172a}input,button{font:inherit;padding:12px;
box-sizing:border-box;width:100%;margin:10px 0}button{background:#1d4ed8;color:white;border:0}
</style><h1>MOSS Stage 1 診斷</h1><p>輸入本次執行階段的密碼。</p>
<form action="/login" method="post"><label for="password">執行階段密碼</label>
<input id="password" name="password" type="password" autocomplete="off" required>
<button type="submit">登入診斷工作台</button></form></html>"""


@app.get("/login")
def login_page():
    return HTMLResponse(LOGIN)


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if not isinstance(password, str) or not hmac.compare_digest(
        password.encode(), PASSWORD.encode()
    ):
        return HTMLResponse(LOGIN + "<p>密碼不符，請使用本次執行階段密碼。</p>", status_code=401)
    response = RedirectResponse("/studio/", status_code=303)
    response.set_cookie(
        "moss_session", SESSION, httponly=True, secure=True, samesite="lax", max_age=36000
    )
    return response


@app.get("/")
def index():
    return RedirectResponse("/studio/")


@app.get("/api/session")
def session():
    return {"csrf": CSRF}


def engine(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = URLRequest(
        "http://127.0.0.1:8188" + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urlopen(request, timeout=15) as response:
        body = response.read()
        return json.loads(body) if body else {}


def worker(job_id):
    job = JOBS[job_id]
    try:
        with LOCK:
            if job["cancel_requested"]:
                job["state"] = "cancelled"
                return
            engine(
                "/prompt",
                {"prompt": job["graph"], "prompt_id": job_id, "client_id": str(uuid.uuid4())},
            )
            job["submitted"] = True
            job["state"] = "running"
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            history = engine("/history/" + job_id).get(job_id)
            if history:
                if history["status"]["status_str"] != "success":
                    with LOCK:
                        job["state"] = "cancelled" if job["cancel_requested"] else "failed"
                    return
                images = [
                    image
                    for output in history["outputs"].values()
                    for image in output.get("images", [])
                ]
                if not images:
                    raise ValueError("missing output")
                query = urlencode(
                    {key: images[0][key] for key in ("filename", "subfolder", "type")}
                )
                with urlopen("http://127.0.0.1:8188/view?" + query, timeout=30) as response:
                    raw = response.read(32 * 1024**2 + 1)
                if len(raw) > 32 * 1024**2:
                    raise ValueError("output too large")
                result = OUT / f"{job_id}.png"
                with Image.open(io.BytesIO(raw)) as image:
                    image.convert("RGB").save(result)
                with zipfile.ZipFile(OUT / f"{job_id}.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
                    bundle.write(result, "probe.png")
                with LOCK:
                    job["state"] = "succeeded"
                return
            if job["cancel_requested"]:
                queue = engine("/queue")
                if not any(
                    item[1] == job_id
                    for item in queue.get("queue_running", []) + queue.get("queue_pending", [])
                ):
                    with LOCK:
                        job["state"] = "cancelled"
                    return
            time.sleep(0.5)
        raise TimeoutError
    except Exception:
        with LOCK:
            job["state"] = "failed"
            job["error"] = "探測失敗或逾時，請核對本機引擎紀錄"


@app.post("/api/probes")
async def submit(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(422, "請求必須是 JSON 物件")
    task, prompt = payload.get("task"), payload.get("prompt")
    if task not in {"text", "vision", "edit"} or not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(422, "模式或提示無效")
    if len(prompt) > 16000:
        raise HTTPException(422, "提示過長；尚未完成 tokenizer 預算驗證")
    try:
        request_id = str(uuid.UUID(payload["client_request_id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, "request id 無效") from exc
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with LOCK:
        if request_id in REQUESTS:
            job_id = REQUESTS[request_id]
            if JOBS[job_id]["fingerprint"] != fingerprint:
                raise HTTPException(409, "相同 request id 內容不同")
            return {"job_id": job_id}
        if sum(j["state"] in {"queued", "running", "cancelling"} for j in JOBS.values()) >= 3:
            raise HTTPException(409, "佇列已滿")
        graphs = json.loads((ROOT / "probe-graphs.json").read_text(encoding="utf-8"))
        graph = graphs[task]
        graph["4"]["inputs"]["text" if task == "text" else "prompt"] = prompt
        if task != "text":
            editor = payload.get("editor") or {}
            if not isinstance(editor, dict):
                raise HTTPException(422, "圖片資料格式無效")
            background = editor.get("background") or {}
            if not isinstance(background, dict) or not isinstance(background.get("path"), str):
                raise HTTPException(422, "請上傳有效來源圖")
            path = Path(background.get("path", ""))
            if path.is_symlink() or not path.resolve().is_relative_to(CACHE):
                raise HTTPException(422, "請上傳有效來源圖")
            if not path.is_file() or path.stat().st_size > 20 * 1024**2:
                raise HTTPException(422, "來源圖超過大小限制或不存在")
            with Image.open(path) as image:
                if getattr(image, "n_frames", 1) != 1 or image.width * image.height > 20_000_000:
                    raise HTTPException(422, "請使用 20MP 以內靜態圖片")
                image = ImageOps.exif_transpose(image).convert("RGB")
                name = f"stage1_{uuid.uuid4()}.png"
                image.save(ROOT / "ComfyUI/input" / name)
            graph["11"]["inputs"]["image"] = name
        job_id = str(uuid.uuid4())
        graph["7"]["inputs"].update({"seed": secrets.randbelow(2**32), "steps": 1})
        JOBS[job_id] = {
            "state": "queued",
            "graph": graph,
            "fingerprint": fingerprint,
            "submitted": False,
            "cancel_requested": False,
        }
        REQUESTS[request_id] = job_id
        POOL.submit(worker, job_id)
        return {"job_id": job_id}


@app.get("/api/probes/{job_id}")
def status(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "工作不存在；請勿自動重新提交")
        response = {"job_id": job_id, "state": job["state"], "error": job.get("error")}
        if job["state"] == "succeeded":
            response.update(
                {"image": f"/api/assets/{job_id}.png", "archive": f"/api/assets/{job_id}.zip"}
            )
        return response


@app.post("/api/probes/{job_id}/cancel")
def cancel(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "工作不存在")
        if job["state"] in {"succeeded", "failed", "cancelled"}:
            return status(job_id)
        job["cancel_requested"] = True
        if not job["submitted"]:
            job["state"] = "cancelled"
            return status(job_id)
        queue = engine("/queue")
        if any(item[1] == job_id for item in queue.get("queue_pending", [])):
            engine("/queue", {"delete": [job_id]})
        elif any(item[1] == job_id for item in queue.get("queue_running", [])):
            engine("/interrupt", {"prompt_id": job_id})
        job["state"] = "cancelling"
        return status(job_id)


@app.get("/api/assets/{filename}")
def asset(filename: str):
    path = Path(filename)
    try:
        if str(uuid.UUID(path.stem)) != path.stem or path.suffix not in {".png", ".zip"}:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(404) from exc
    if JOBS.get(path.stem, {}).get("state") != "succeeded" or not (OUT / filename).is_file():
        raise HTTPException(404)
    return FileResponse(OUT / filename)


JS = """async (task,prompt,editor) => {
 const csrf = (await (await fetch('/api/session')).json()).csrf;
 const r = await fetch('/api/probes',{method:'POST',headers:{'Content-Type':'application/json',
 'X-Moss-CSRF':csrf},body:JSON.stringify({task,prompt,editor,client_request_id:crypto.randomUUID()})});
 const j=await r.json(); if(!r.ok){document.getElementById('probe-status').textContent=
 JSON.stringify(j);return;} localStorage.setItem('moss_probe_job',j.job_id);
 await window.mossProbePoll(j.job_id);
}"""
INIT = """() => {
 window.mossProbePoll = async(id) => {
  while(true){ const r=await fetch('/api/probes/'+encodeURIComponent(id));
   const j=await r.json(); const s=document.getElementById('probe-status'); if(!s)return;
   s.textContent=j.error||j.state||'工作無法找回，請核對原紀錄';
   if(!r.ok)return;
   if(j.state==='succeeded'){document.getElementById('probe-image').src=j.image;
    const a=document.getElementById('probe-zip');a.href=j.archive;a.hidden=false;return;}
   if(['failed','cancelled'].includes(j.state))return;
   await new Promise(resolve=>setTimeout(resolve,1000));
  }
 };
 const id=localStorage.getItem('moss_probe_job');if(id)window.mossProbePoll(id);
}"""
CANCEL_JS = """async () => {
 const id=localStorage.getItem('moss_probe_job');if(!id)return;
 const csrf=(await(await fetch('/api/session')).json()).csrf;
 await fetch('/api/probes/'+encodeURIComponent(id)+'/cancel',{
 method:'POST',headers:{'X-Moss-CSRF':csrf}});
}"""
with gr.Blocks(title="MOSS Stage 1 輪詢診斷", analytics_enabled=False) as demo:
    gr.Markdown("# MOSS Stage 1 輪詢診斷\n真實單步載入與通訊測試；尚非完整五分頁工作台。")
    with gr.Row():
        with gr.Column():
            task = gr.Dropdown(["text", "vision", "edit"], value="text", label="載入路徑")
            prompt = gr.Textbox(label="測試描述", value="A red ceramic teapot on a wooden table.")
            editor = gr.ImageEditor(
                type="pil",
                image_mode="RGBA",
                sources=["upload"],
                format="png",
                label="來源圖與筆刷傳輸探測",
            )
            start = gr.Button("執行單步探測", variant="primary")
            stop = gr.Button("取消目前探測")
        with gr.Column():
            gr.HTML(
                '<p id="probe-status" role="status">尚未提交</p>'
                '<img id="probe-image" alt="探測結果" style="max-width:100%">'
                '<p><a id="probe-zip" hidden download>下載探測 ZIP</a></p>'
            )
    start.click(fn=None, inputs=[task, prompt, editor], js=JS)
    stop.click(fn=None, js=CANCEL_JS)
    demo.load(fn=None, js=INIT)

app = gr.mount_gradio_app(app, demo, path="/studio", max_file_size="20mb")
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="warning", access_log=False)
