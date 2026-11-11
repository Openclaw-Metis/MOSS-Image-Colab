"""Authenticated same-origin polling adapter for the Gradio workbench."""

import hmac
import io
import json
import secrets
import threading
import time
import zipfile
from functools import lru_cache

import gradio as gr
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from PIL import Image
from starlette.concurrency import run_in_threadpool

from moss_studio.adapters.comfy import EngineError
from moss_studio.domain.contracts import ConflictError, ValidationError, digest, new_id
from moss_studio.domain.layout import compile_layout, parse_layout
from moss_studio.services.resources import inspect_runtime
from moss_studio.storage.archive import export_project, import_project
from moss_studio.storage.atomic import private_dir

LOGIN = """<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>MOSS-Image 登入</title><style>body{font:17px system-ui;max-width:420px;
margin:15vh auto;background:#f8fafc;color:#0f172a}input,button{font:inherit;padding:12px;
box-sizing:border-box;width:100%;margin:12px 0}button{background:#1d4ed8;color:white;border:0}
</style><h1>MOSS-Image 創作工作台</h1><p>使用本次執行階段的密碼登入。</p>
<form method="post" action="/login"><label for="password">執行階段密碼</label>
<input id="password" name="password" type="password" autocomplete="off" required>
<button type="submit">開啟創作工作台</button></form></html>"""


async def object_body(request: Request) -> dict:
    data = await request.body()
    if len(data) > 2 * 1024**2:
        raise HTTPException(413, "請求超過限制")
    try:
        value = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise ValidationError("請求不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("請求必須是 JSON 物件")
    return value


def wire_job(job: dict) -> dict:
    # Seeds up to 2^63-1 must not be rounded by JavaScript's 53-bit Number.
    result = {**job, "seed": str(job["seed"])}
    if "record" in result:
        result["record"] = {**result["record"], "seed": str(result["record"]["seed"])}
    return result


LINK_TTL_SECONDS = 1800
THUMBNAIL_EDGE = 384
MAX_LIVE_LINKS = 5


def create_http_app(service, password: str, ui_factory) -> FastAPI:
    if not isinstance(password, str) or len(password) < 24:
        raise ValidationError("入口需要高熵的單次密碼")
    session_token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # One-time login links: token → monotonic expiry. In memory only, so an app restart
    # invalidates every link; each token is removed the moment it is redeemed.
    login_links: dict[str, float] = {}
    links_lock = threading.Lock()

    def authenticated(request):
        return hmac.compare_digest(request.cookies.get("moss_session", ""), session_token)

    def password_matches(candidate) -> bool:
        return isinstance(candidate, str) and hmac.compare_digest(
            candidate.encode(), password.encode()
        )

    def signed_in() -> RedirectResponse:
        response = RedirectResponse("/studio/", status_code=303)
        response.set_cookie(
            "moss_session", session_token, httponly=True, secure=True, samesite="lax", max_age=36000
        )
        return response

    @app.middleware("http")
    async def boundary(request, call_next):
        public = {"/login", "/login-link", "/favicon.ico"}
        if request.url.path not in public and not authenticated(request):
            if request.url.path in {"/", "/studio", "/studio/"}:
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"code": "E_AUTH", "message": "請先登入"}, status_code=401)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/login":
            origin = request.headers.get("origin")
            if origin and origin not in {
                f"https://{request.headers.get('host')}",
                f"http://{request.headers.get('host')}",
            }:
                return JSONResponse({"code": "E_ORIGIN"}, status_code=403)
            if request.url.path.startswith("/api/") and not hmac.compare_digest(
                request.headers.get("x-moss-csrf", ""), csrf
            ):
                return JSONResponse({"code": "E_CSRF"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "code": "E_CONFLICT" if isinstance(exc, ConflictError) else "E_INPUT",
                "message": str(exc),
            },
            status_code=409 if isinstance(exc, ConflictError) else 422,
        )

    @app.exception_handler(EngineError)
    async def engine_error(request, exc):
        return JSONResponse({"code": "E_ENGINE", "message": str(exc)}, status_code=503)

    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(
            {"code": "E_NOT_FOUND", "message": "找不到此專案、工作或素材"}, status_code=404
        )

    @app.get("/login")
    def login_page(token: str | None = None):
        if token is None:
            return HTMLResponse(LOGIN)
        now, expiry = time.monotonic(), None
        with links_lock:
            for known in list(login_links):
                if login_links[known] < now:
                    del login_links[known]
                elif hmac.compare_digest(known.encode(), token.encode()):
                    expiry = login_links.pop(known)  # single use: gone before the cookie is set
        if expiry is None:
            notice = "<p>登入連結已用過或過期。請貼上密碼，或在 Notebook 重新執行第 4 格。</p>"
            return HTMLResponse(LOGIN + notice, status_code=401)
        return signed_in()

    @app.post("/login-link")
    async def login_link(request: Request):
        """Mints a one-time link for whoever already holds the password (the notebook)."""
        if len(await request.body()) > 4096:
            raise HTTPException(413)
        form = await request.form()
        if not password_matches(form.get("password", "")):
            return JSONResponse({"code": "E_AUTH", "message": "密碼不符"}, status_code=401)
        token, now = secrets.token_urlsafe(32), time.monotonic()
        with links_lock:
            for known in [k for k, expiry in login_links.items() if expiry < now]:
                del login_links[known]
            while len(login_links) >= MAX_LIVE_LINKS:  # oldest unredeemed link goes first
                del login_links[min(login_links, key=login_links.get)]
            login_links[token] = now + LINK_TTL_SECONDS
        return {"path": f"/login?token={token}", "expires_in": LINK_TTL_SECONDS}

    @app.post("/login")
    async def login(request: Request):
        if len(await request.body()) > 4096:
            raise HTTPException(413)
        form = await request.form()
        if not password_matches(form.get("password", "")):
            return HTMLResponse(LOGIN + "<p>密碼不符。</p>", status_code=401)
        return signed_in()

    @app.get("/")
    def index():
        return RedirectResponse("/studio/")

    @app.get("/api/session")
    def session():
        return {
            "csrf": csrf,
            "tasks": sorted(service.tasks),
            "profile_id": service.default_profile_id,
            "profiles": [
                {
                    key: profile[key]
                    for key in ("id", "label", "task_family", "steps", "cfg", "allowed_models")
                }
                | {
                    "negative_prompt": profile.get("negative_prompt", True),
                    "default_negative_prompt": profile.get("default_negative_prompt", ""),
                }
                for profile in service.profiles.values()
            ],
            "model_artifact_id": service.models.active_backbone(),
            "capabilities": service.capabilities,
            "release_status": "development",
        }

    @app.get("/api/runtime")
    def runtime():
        return inspect_runtime(service.root)

    @app.get("/api/projects")
    def projects():
        return [
            {k: project[k] for k in ("id", "name", "revision", "updated_at")}
            for project in service.projects.list()
        ]

    def with_hashes(project: dict) -> dict:
        hashes = {tab: digest(draft) for tab, draft in project["drafts"].items()}
        return {**project, "draft_hash": hashes["t2i"], "draft_hashes": hashes}

    @app.post("/api/projects")
    async def new_project(request: Request):
        value = await object_body(request)
        return with_hashes(service.projects.create(value.get("name", "未命名創作")))

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        return with_hashes(service.projects.get(project_id))

    @app.patch("/api/projects/{project_id}")
    async def rename_project(project_id: str, request: Request):
        value = await object_body(request)
        return with_hashes(
            await run_in_threadpool(
                service.rename_project,
                project_id,
                value.get("name"),
                value.get("expected_revision"),
            )
        )

    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str, expected_revision: int):
        await run_in_threadpool(service.delete_project, project_id, expected_revision)
        return {"deleted": project_id}

    @app.put("/api/projects/{project_id}/draft")
    async def save_draft(project_id: str, request: Request):
        value = await object_body(request)
        tab = value.get("tab", "t2i")
        project = await run_in_threadpool(
            service.save_draft, project_id, value.get("draft"), value.get("expected_revision"), tab
        )
        return {"revision": project["revision"], "draft_hash": digest(project["drafts"][tab])}

    @app.get("/api/projects/{project_id}/assets")
    def list_assets(project_id: str):
        project = service.projects.get(project_id)
        return [
            {key: meta[key] for key in ("id", "kind", "width", "height")}
            for meta in (service.assets.get(project_id, a) for a in project["asset_ids"])
        ]

    @app.get("/api/models")
    def models():
        return {"models": service.models.list(), "busy": service.busy()}

    @app.post("/api/models/{artifact_id}/download")
    async def download_model(artifact_id: str):
        return await run_in_threadpool(service.models.download, artifact_id)

    @app.delete("/api/models/{artifact_id}")
    def delete_model(artifact_id: str):
        with service.lock:
            return service.models.delete(artifact_id, busy=service.busy())

    @app.post("/api/models/user-loras")
    async def add_user_lora(request: Request):
        value = await object_body(request)
        # Network lookup of the Hub's pinned hash and size; the download is a separate step.
        return await run_in_threadpool(
            service.models.add_user_lora,
            value.get("repo"),
            value.get("revision"),
            value.get("path"),
        )

    @app.post("/api/models/activate")
    async def activate_model(request: Request):
        value = await object_body(request)
        with service.lock:
            return service.models.activate(value.get("artifact_id"), busy=service.busy())

    @app.post("/api/projects/{project_id}/assets")
    async def upload_asset(project_id: str, request: Request, kind: str = "input"):
        # Raw image bytes; the browser file name is never read or stored. Stream with a hard
        # cap so an oversized body is refused before it is fully buffered.
        limit = 20 * 1024**2
        if int(request.headers.get("content-length") or 0) > limit:
            raise HTTPException(413, "圖片需小於 20 MiB")
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, "圖片需小於 20 MiB")
            chunks.append(chunk)
        return await run_in_threadpool(service.import_asset, project_id, b"".join(chunks), kind)

    @app.post("/api/layout/validate")
    async def layout(request: Request):
        value = await object_body(request)
        previous = value.get("previous_items")
        if previous is not None and (
            not isinstance(previous, list) or any(not isinstance(item, dict) for item in previous)
        ):
            raise ValidationError("前一版排版框資料無效")
        parsed = parse_layout(
            value.get("layout"), value.get("width"), value.get("height"), previous
        )
        return {
            "layout": compile_layout(
                parsed["caption"], parsed["items"], value["width"], value["height"], parsed["meta"]
            ),
            "items": parsed["items"],
        }

    @app.post("/api/jobs")
    async def submit(request: Request):
        value = await object_body(request)
        if isinstance(value.get("seed"), str):
            if not value["seed"].isdigit() or len(value["seed"]) > 19:
                raise ValidationError("種子需是非負整數，或留空自動產生")
            value["seed"] = int(value["seed"])
        return wire_job(await run_in_threadpool(service.submit, value))

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str, after_seq: int = 0):
        if after_seq < 0:
            raise ValidationError("事件序號不可為負")
        return wire_job(service.get_job(job_id, after_seq))

    @app.get("/api/jobs/request/{project_id}/{request_id}")
    def find_request(project_id: str, request_id: str):
        existing = service.ledger.find_request(project_id, request_id)
        if not existing:
            raise KeyError("找不到前次提交")
        return wire_job(service.get_job(existing["id"]))

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        return wire_job(await run_in_threadpool(service.cancel, job_id))

    @app.get("/api/assets/{project_id}/{asset_id}")
    def asset(project_id: str, asset_id: str):
        project = service.projects.get(project_id)
        if asset_id not in project["asset_ids"]:
            raise HTTPException(404)
        return FileResponse(
            service.assets.path(project_id, asset_id),
            media_type="image/png",
            filename=f"{asset_id}.png",
        )

    @lru_cache(maxsize=128)
    def thumbnail(project_id: str, asset_id: str) -> bytes:
        with Image.open(service.assets.path(project_id, asset_id)) as image:
            image.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=80)
        return buffer.getvalue()

    @app.get("/api/assets/{project_id}/{asset_id}/thumbnail")
    def asset_thumbnail(project_id: str, asset_id: str):
        # Galleries and pickers list many pictures; full PNGs through the tunnel are 1-4 MB each.
        project = service.projects.get(project_id)
        if asset_id not in project["asset_ids"]:
            raise HTTPException(404)
        return Response(thumbnail(project_id, asset_id), media_type="image/jpeg")

    @app.get("/api/projects/{project_id}/export")
    def export(project_id: str):
        path = private_dir(service.root / "exports") / f"{new_id()}.zip"
        export_project(service.projects, service.assets, project_id, path)
        return FileResponse(path, filename=f"moss-project-{project_id[:8]}.zip")

    @app.post("/api/projects/import")
    async def import_archive(request: Request):
        # Stream to a private temp file with a hard cap; never trust Content-Length alone.
        limit = 1024**3
        if int(request.headers.get("content-length") or 0) > limit:
            raise HTTPException(413, "專案檔超過 1 GiB")
        staging = private_dir(service.root / "staging")
        path = staging / f"{new_id()}.zip"
        size = 0
        try:
            with path.open("xb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, "專案檔超過 1 GiB")
                    stream.write(chunk)
            project = await run_in_threadpool(
                import_project, service.projects, service.assets, path, staging
            )
        finally:
            path.unlink(missing_ok=True)
        return with_hashes(project)

    @app.get("/api/works/{project_id}.zip")
    def works(project_id: str):
        project = service.projects.get(project_id)
        exports = private_dir(service.root / "exports")
        path = exports / f"{new_id()}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for asset_id in sorted(project["asset_ids"]):
                metadata = service.assets.get(project_id, asset_id)
                if metadata["kind"] == "output":
                    bundle.write(service.assets.path(project_id, asset_id), f"{asset_id}.png")
        return FileResponse(path, filename="moss-works.zip")

    static_dir = service.repository / "src/moss_studio/ui/static"
    # Fixed at startup: only the shipped front-end modules, never an arbitrary path.
    static_files = {path.name for path in static_dir.glob("*.js") if not path.is_symlink()}

    @app.get("/static/{filename}")
    def static(filename: str):
        if filename not in static_files:
            raise HTTPException(404)
        return FileResponse(static_dir / filename, media_type="text/javascript")

    theme = gr.themes.Soft(primary_hue="blue", font=["system-ui", "sans-serif"])
    values = theme.to_dict()["theme"]
    # The workbench intentionally uses one light palette, including when the
    # browser prefers dark mode. Keep all component labels and surfaces coherent.
    theme.set(**{k: values[k[:-5]] for k in values if k.endswith("_dark") and k[:-5] in values})
    return gr.mount_gradio_app(
        app,
        ui_factory(service),
        path="/studio",
        max_file_size="20mb",
        theme=theme,
        footer_links=[],
    )
