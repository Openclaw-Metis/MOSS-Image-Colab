import json
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from moss_studio.adapters.comfy import ComfyClient
from moss_studio.domain.contracts import ConflictError, ValidationError, new_id
from moss_studio.services.bootstrap import ColabBootstrap
from moss_studio.services.processes import ManagedProcess, identity


@pytest.fixture
def engine_stub():
    calls = []
    prompt_id = new_id()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append(("GET", self.path, None))
            result = (
                {"queue_running": [[0, prompt_id]], "queue_pending": []}
                if self.path == "/queue"
                else {"ok": True}
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, payload))
            self.send_response(200)
            self.end_headers()
            if self.path == "/prompt":
                self.wfile.write(json.dumps({"prompt_id": payload["prompt_id"]}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield ComfyClient(f"http://127.0.0.1:{server.server_port}"), calls, prompt_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_pinned_http_payloads_and_targeted_cancel(engine_stub):
    client, calls, prompt_id = engine_stub
    assert client.health() == {"ok": True}
    assert client.object_info() == {"ok": True}
    graph = {"1": {"class_type": "Example", "inputs": {}}}
    assert client.submit(graph, new_id(), prompt_id)["prompt_id"] == prompt_id
    assert client.cancel_owned(prompt_id, exclusive_engine=True) == "cancelling"
    assert calls[-1] == ("POST", "/interrupt", {"prompt_id": prompt_id})
    with pytest.raises(ValidationError):
        client.cancel_owned(prompt_id, exclusive_engine=False)
    before = len(calls)
    assert client.cancel_owned(new_id(), exclusive_engine=True) == "not_queued"
    assert len(calls) == before + 1


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:8188",
        "http://127.0.0.1:8188/a",
        "http://user@127.0.0.1:8188",
        "http://127.0.0.1:8188?secret=x",
        "http://0.0.0.0:8188",
    ],
)
def test_comfy_public_or_ambiguous_urls_rejected(url):
    with pytest.raises(ValidationError):
        ComfyClient(url)


def test_engine_vram_mode_comes_from_lock_and_rejects_unknown(tmp_path):
    root = Path(__file__).resolve().parents[2]
    bootstrap = ColabBootstrap(root, tmp_path / "runtime", tmp_path / "models")
    default = bootstrap.engine_command()
    assert "--lowvram" in default  # current pinned default until Stage 3 measures 'auto'
    auto = bootstrap.engine_command("auto")
    assert not any(flag in auto for flag in ("--lowvram", "--highvram", "--normalvram"))
    assert auto[:7] == default[:7]
    with pytest.raises(ValidationError):
        bootstrap.engine_command("gpu-only")


@pytest.mark.skipif(
    not Path("/proc/self").exists(), reason="程序所有權檢查依賴 Linux /proc（Colab 執行階段）"
)
def test_managed_process_rerun_stop_and_no_unowned_adoption(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
    manager = ManagedProcess(tmp_path / "runtime", "probe")

    def health():
        with urlopen(f"http://127.0.0.1:{port}", timeout=1) as response:
            assert response.status == 200

    try:
        first = manager.start(command, tmp_path, port, health, timeout=5)
        second = manager.start(command, tmp_path, port, health, timeout=5)
        assert first["pid"] == second["pid"]
        assert second["reused"] is True
        with pytest.raises(ConflictError):
            ManagedProcess(tmp_path / "other", "probe").start(command, tmp_path, port, health)
    finally:
        manager.stop()
    assert identity(first["pid"]) is None
    manager.stop()


def test_fresh_clone_checkout_rerun_and_dirty_protection(tmp_path, monkeypatch):
    """Real local git operations; pip/GPU are excluded from this CPU regression."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-q", str(upstream)], check=True)
    (upstream / "README.md").write_text("pinned\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    commit = [
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
    ]
    subprocess.run([*commit, "first"], cwd=upstream, check=True)
    pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    (upstream / "README.md").write_text("newer\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run([*commit, "second"], cwd=upstream, check=True)
    repository = tmp_path / "studio"
    (repository / "configs").mkdir(parents=True)
    runtime = {
        "status": "candidate",
        "comfyui": {"repo": str(upstream), "commit": pin},
        "gradio": "6.31.0",
        "huggingface_hub": "1.33.0",
        "transitive_lock": "pins.lock",
    }
    (repository / "configs/runtime.lock.json").write_text(json.dumps(runtime))
    (repository / "configs/models.lock.json").write_text('{"artifacts":[]}')
    (repository / "pins.lock").write_text("")
    monkeypatch.setattr("moss_studio.services.bootstrap.inspect_runtime", lambda _: {})
    monkeypatch.setattr("moss_studio.services.bootstrap.l4_preflight", lambda _: [])

    class FakeVenv:
        def __init__(self, **kwargs):
            assert kwargs == {"with_pip": False, "system_site_packages": True}

        def create(self, path):
            path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("moss_studio.services.bootstrap.venv.EnvBuilder", FakeVenv)
    actual_run = subprocess.run
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "git":
            return actual_run(command, **kwargs)
        assert command[1:3] == ["-m", "pip"]
        if "stdout" in kwargs:
            kwargs["stdout"].write("test-pin==1.0\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("moss_studio.services.bootstrap.subprocess.run", run)
    bootstrap = ColabBootstrap(repository, tmp_path / "runtime", tmp_path / "models")
    bootstrap.prepare(allow_candidate=True)
    bootstrap.prepare(allow_candidate=True)
    assert (bootstrap.comfy / "README.md").read_text() == "pinned\n"
    assert len([c for c in calls if c[:2] == ["git", "clone"]]) == 1
    (bootstrap.comfy / "README.md").write_text("local changes\n")
    with pytest.raises(ConflictError):
        bootstrap.prepare(allow_candidate=True)
    assert (bootstrap.comfy / "README.md").read_text() == "local changes\n"
