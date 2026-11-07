"""Stage 1 diagnostic UI, not the five-tab product. Uses real ComfyUI jobs.

Start only on loopback. Password must be supplied in process memory/environment.
Never prints credentials, prompts, images, or Gradio share links.
"""

import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import gradio as gr
from PIL import Image

ROOT = Path(os.environ.get("MOSS_PROBE_ROOT", "/content/moss-stage1"))
COMFY = ROOT / "ComfyUI"
OUT = ROOT / "probe_outputs"
OUT.mkdir(exist_ok=True, mode=0o700)
PASSWORD = os.environ.pop("MOSS_PROBE_PASSWORD", "")
if len(PASSWORD) < 24:
    raise RuntimeError("Stage 1 probe requires a high-entropy password in memory")


def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        "http://127.0.0.1:8188" + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urlopen(request, timeout=10) as response:
        body = response.read()
        return json.loads(body) if body else {}


def generate(task, prompt, editor):
    graphs = json.loads((ROOT / "probe-graphs.json").read_text(encoding="utf-8"))
    graph = graphs[task]
    graph["4"]["inputs"]["text" if task == "text" else "prompt"] = prompt
    if task != "text":
        if not editor or editor.get("background") is None:
            raise gr.Error("請上傳探測來源圖")
        image = editor["background"]
        if image.width * image.height > 20_000_000:
            raise gr.Error("圖片超過 20MP")
        name = f"stage1_{uuid.uuid4()}.png"
        image.convert("RGB").save(COMFY / "input" / name)
        graph["11"]["inputs"]["image"] = name
    # One-step diagnostic only; never label this as the 8-step or 50-step production profile.
    graph["7"]["inputs"].update({"steps": 1, "seed": int.from_bytes(os.urandom(4), "big")})
    prompt_id = str(uuid.uuid4())
    api("/prompt", {"prompt": graph, "prompt_id": prompt_id, "client_id": str(uuid.uuid4())})
    yield None, f"已提交真實載入探測：{prompt_id}", None, prompt_id
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        history = api("/history/" + prompt_id).get(prompt_id)
        if history:
            if history["status"]["status_str"] != "success":
                raise gr.Error("引擎探測失敗，請查看本機診斷")
            images = [
                image
                for output in history["outputs"].values()
                for image in output.get("images", [])
            ]
            if not images:
                raise gr.Error("引擎沒有輸出圖片")
            query = urlencode({key: images[0][key] for key in ("filename", "subfolder", "type")})
            result = OUT / f"{prompt_id}.png"
            with urlopen("http://127.0.0.1:8188/view?" + query, timeout=30) as response:
                result.write_bytes(response.read(32 * 1024**2))
            with Image.open(result) as image:
                image.convert("RGB").save(result)  # Strip prompts/EXIF from offered image.
            archive = OUT / f"{prompt_id}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(result, "probe.png")
            yield str(result), "載入探測完成；不代表畫質驗收通過", str(archive), prompt_id
            return
        queue = api("/queue")
        running = any(item[1] == prompt_id for item in queue.get("queue_running", []))
        yield None, "引擎執行中" if running else "排隊或核對紀錄中", None, prompt_id
        time.sleep(1)
    raise gr.Error("探測逾時，保留引擎紀錄，請先核對後再提交")


def cancel(prompt_id):
    try:
        uuid.UUID(prompt_id)
    except (ValueError, TypeError):
        return "目前沒有可取消的工作"
    queue = api("/queue")
    if any(item[1] == prompt_id for item in queue.get("queue_pending", [])):
        api("/queue", {"delete": [prompt_id]})
    elif any(item[1] == prompt_id for item in queue.get("queue_running", [])):
        api("/interrupt", {"prompt_id": prompt_id})
    else:
        return "工作已離開引擎佇列，請核對結果"
    return "已要求取消，等待引擎確認；尚未宣告取消完成"


with gr.Blocks(title="MOSS Stage 1 診斷", analytics_enabled=False) as demo:
    gr.Markdown("# MOSS Stage 1 診斷\n這是單步載入與通訊探測，尚非完整創作工作台。")
    state = gr.State("")
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
            result = gr.Image(label="探測結果", type="filepath")
            status = gr.Textbox(label="狀態", interactive=False)
            archive = gr.File(label="下載測試 ZIP")
    start.click(
        generate,
        [task, prompt, editor],
        [result, status, archive, state],
        concurrency_limit=1,
        concurrency_id="gpu_probe",
        api_name="probe",
    )
    stop.click(cancel, [state], [status], queue=False, api_name="cancel_probe")

demo.queue(max_size=3).launch(
    server_name="127.0.0.1",
    server_port=7860,
    auth=("oberon", PASSWORD),
    share=False,
    prevent_thread_lock=False,
    inline=False,
    allowed_paths=[str(OUT)],
    max_file_size="20mb",
)
