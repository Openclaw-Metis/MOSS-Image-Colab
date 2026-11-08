import io
import time
from pathlib import Path

import pytest
from PIL import Image

gr = pytest.importorskip("gradio")
from fastapi.testclient import TestClient  # noqa: E402

from moss_studio.adapters.http import create_http_app  # noqa: E402
from moss_studio.services.studio import StudioService  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def http_studio(tmp_path):
    class Engine:
        def object_info(self):
            names = [
                "UNETLoader",
                "CLIPLoader",
                "VAELoader",
                "CLIPTextEncode",
                "KSampler",
                "EmptyFlux2LatentImage",
                "VAEDecode",
                "SaveImage",
                "ModelSamplingAuraFlow",
                "SkipLayerGuidanceDiTSimple",
            ]
            return {name: {"input": {"required": {}}} for name in names}

    buffer = io.BytesIO()
    Image.new("RGB", (1024, 1024), "blue").save(buffer, format="PNG")

    def runner(graph, prompt_id, event):
        event("executing", {"node": "7"})
        event("executing", {"node": "8"})
        return [buffer.getvalue()]

    service = StudioService(ROOT, tmp_path, engine=Engine(), runner=runner)

    def ui(_):
        with gr.Blocks(analytics_enabled=False) as demo:
            gr.Markdown("HTTP boundary test; no GPU inference claim")
        return demo

    app = create_http_app(service, "test-only-password-" + "x" * 32, ui)
    try:
        with TestClient(app, base_url="https://testserver") as client:
            yield client, service
    finally:
        service.close()


def authenticate(client):
    response = client.post(
        "/login", data={"password": "test-only-password-" + "x" * 32}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    return {"X-Moss-CSRF": client.get("/api/session").json()["csrf"]}


@pytest.mark.parametrize(
    "path",
    [
        "/api/session",
        "/api/projects",
        "/api/runtime",
        "/studio/config",
        "/studio/gradio_api/upload",
        "/api/assets/invalid/invalid",
        "/static/studio.js",
        "/api/jobs/request/invalid/invalid",
    ],
)
def test_unauthenticated_boundary_covers_api_assets_and_gradio(http_studio, path):
    client, _ = http_studio
    assert client.get(path).status_code == 401


def test_one_time_login_link(http_studio, monkeypatch):
    client, _ = http_studio
    password = "test-only-password-" + "x" * 32
    assert client.post("/login-link", data={"password": "wrong"}).status_code == 401
    minted = client.post("/login-link", data={"password": password}).json()
    assert minted["expires_in"] == 1800 and minted["path"].startswith("/login?token=")
    assert client.get("/api/session").status_code == 401
    redeemed = client.get(minted["path"], follow_redirects=False)
    assert redeemed.status_code == 303 and redeemed.headers["location"] == "/studio/"
    assert (
        "HttpOnly" in redeemed.headers["set-cookie"] and "Secure" in redeemed.headers["set-cookie"]
    )
    assert redeemed.headers["referrer-policy"] == "no-referrer"
    assert client.get("/api/session").status_code == 200
    client.cookies.clear()
    assert client.get(minted["path"], follow_redirects=False).status_code == 401  # single use
    assert client.get("/login?token=made-up", follow_redirects=False).status_code == 401
    # Expired links do not work, and at most five unredeemed links are alive at once.
    monkeypatch.setattr("moss_studio.adapters.http.time.monotonic", lambda: time.time() + 10**6)
    stale = client.post("/login-link", data={"password": password}).json()["path"]
    monkeypatch.setattr("moss_studio.adapters.http.time.monotonic", lambda: time.time() + 10**9)
    assert client.get(stale, follow_redirects=False).status_code == 401
    paths = [
        client.post("/login-link", data={"password": password}).json()["path"] for _ in range(6)
    ]
    assert client.get(paths[0], follow_redirects=False).status_code == 401
    assert client.get(paths[-1], follow_redirects=False).status_code == 303


def test_csrf_origin_invalid_json_and_unicode_password(http_studio):
    client, _ = http_studio
    assert client.post("/login", data={"password": "非本次密碼"}).status_code == 401
    headers = authenticate(client)
    assert client.post("/api/projects", json={"name": "test"}).status_code == 403
    assert (
        client.post(
            "/api/projects",
            json={"name": "test"},
            headers={**headers, "Origin": "https://other.invalid"},
        ).status_code
        == 403
    )
    assert client.post("/api/projects", content="{", headers=headers).status_code == 422
    assert (
        client.post(
            "/api/layout/validate", json={"width": 0, "height": 1024}, headers=headers
        ).status_code
        == 422
    )


def test_seed_precision_project_conflict_and_saved_asset_auth(http_studio, job_spec):
    client, service = http_studio
    headers = authenticate(client)
    project = client.post("/api/projects", json={"name": "exact seed"}, headers=headers).json()
    job_spec.update(project_id=project["id"], seed=str(2**63 - 1))
    submitted = client.post("/api/jobs", json=job_spec, headers=headers)
    assert submitted.status_code == 200, submitted.text
    job = submitted.json()
    assert job["seed"] == str(2**63 - 1)
    recovered = client.get(f"/api/jobs/request/{project['id']}/{job_spec['client_request_id']}")
    assert recovered.status_code == 200
    assert recovered.json()["id"] == job["id"]
    # Losing the POST response must not force another inference submission.
    duplicate = client.post("/api/jobs", json=job_spec, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == job["id"]
    assert len(service.ledger.list(project["id"])) == 1
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert job["status"] == "succeeded"
    asset_id = job["record"]["output_assets"][0]
    asset_url = f"/api/assets/{project['id']}/{asset_id}"
    assert client.get(asset_url).status_code == 200
    assert (
        client.put(
            f"/api/projects/{project['id']}/draft",
            json={"expected_revision": 0, "draft": {}},
            headers=headers,
        ).status_code
        == 409
    )
    client.cookies.clear()
    assert client.get(asset_url).status_code == 401
    assert service.ledger.get(job["id"])["snapshot"]["seed"] == 2**63 - 1


def test_raw_upload_needs_csrf_caps_size_and_returns_edit_size(http_studio):
    client, _ = http_studio
    headers = authenticate(client)
    project = client.post("/api/projects", json={"name": "upload"}, headers=headers).json()
    buffer = io.BytesIO()
    Image.new("RGB", (1920, 1080), "white").save(buffer, format="JPEG")
    url = f"/api/projects/{project['id']}/assets?kind=input"
    image = {"Content-Type": "image/jpeg"}
    assert client.post(url, content=buffer.getvalue(), headers=image).status_code == 403
    uploaded = client.post(url, content=buffer.getvalue(), headers={**headers, **image})
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["mime"] == "image/png" and body["edit_size"] == [1360, 768]
    assert "filename" not in body
    assert client.get(f"/api/projects/{project['id']}").json()["asset_ids"] == [body["id"]]
    too_big = client.post(url, content=b"0" * (20 * 1024**2 + 1), headers={**headers, **image})
    assert too_big.status_code == 413
    junk = client.post(url, content=b"not an image", headers={**headers, **image})
    assert junk.status_code == 422
    draft = client.put(
        f"/api/projects/{project['id']}/draft",
        json={"tab": "edit", "expected_revision": body["project_revision"], "draft": {"x": 1}},
        headers=headers,
    )
    assert draft.status_code == 200
    saved = client.get(f"/api/projects/{project['id']}").json()
    assert saved["drafts"]["edit"] == {"x": 1} and saved["drafts"]["t2i"] == {}
    bad_tab = client.put(
        f"/api/projects/{project['id']}/draft",
        json={"tab": "../x", "expected_revision": draft.json()["revision"], "draft": {}},
        headers=headers,
    )
    assert bad_tab.status_code == 422
