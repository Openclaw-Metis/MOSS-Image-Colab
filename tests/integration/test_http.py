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
    recovered = client.get(
        f"/api/jobs/request/{project['id']}/{job_spec['client_request_id']}"
    )
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
