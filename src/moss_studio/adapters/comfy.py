"""Pinned ComfyUI HTTP contract. This client only connects to numeric loopback."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from moss_studio.domain.contracts import ValidationError, new_id, validate_id


class EngineError(RuntimeError):
    pass


class EngineSettledError(EngineError):
    """The prompt is confirmed finished (or was cancelled before submission)."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 10):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or not parsed.port
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValidationError("引擎必須綁定 127.0.0.1 與明確連接埠")
        self.base_url, self.timeout = base_url.rstrip("/"), timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _json(self, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body, allow_nan=False).encode() if body is not None else None
        request = Request(
            self.base_url + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                payload = response.read(16 * 1024**2 + 1)
                if len(payload) > 16 * 1024**2:
                    raise EngineError("E_ENGINE：引擎回應過大")
                return json.loads(payload) if payload else {}
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            # Do not include engine messages: upstream errors can embed prompts or secrets.
            raise EngineError("E_ENGINE：引擎無回應或拒絕請求，請查看本機診斷") from exc

    def health(self) -> dict:
        return self._json("/system_stats")

    def object_info(self) -> dict:
        return self._json("/object_info")

    def queue(self) -> dict:
        return self._json("/queue")

    def history(self, prompt_id: str) -> dict:
        return self._json(f"/history/{validate_id(prompt_id)}")

    def submit(self, graph: dict, client_id: str, prompt_id: str | None = None) -> dict:
        """Accept trusted API graphs from the workflow compiler, never raw user JSON."""
        validate_id(client_id)
        prompt_id = validate_id(prompt_id or new_id())
        if not isinstance(graph, dict) or not graph:
            raise ValidationError("工作流不可為空")
        if any(not isinstance(node, dict) or "class_type" not in node for node in graph.values()):
            raise ValidationError("必須使用 API graph，不能提交 UI graph")
        return self._json(
            "/prompt", {"prompt": graph, "client_id": client_id, "prompt_id": prompt_id}
        )

    def upload_image(self, name: str, data: bytes) -> str:
        """POST /upload/image (type=input, overwrite). Names are UUID-based, never user files."""
        if not name.startswith("moss_") or "/" in name or "\\" in name or not name.endswith(".png"):
            raise ValidationError("引擎輸入檔名必須由本工具產生")
        boundary = "moss-" + new_id()
        parts = [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                f'filename="{name}"\r\nContent-Type: image/png\r\n\r\n'
            ).encode()
            + data
            + b"\r\n"
        ]
        for field, value in (("type", "input"), ("overwrite", "true")):
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n'
                f"{value}\r\n".encode()
            )
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        request = Request(
            self.base_url + "/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with self.opener.open(request, timeout=max(self.timeout, 60)) as response:
                result = json.loads(response.read(64 * 1024))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise EngineError("E_ENGINE：參考圖無法送入引擎") from exc
        if result.get("name") != name or result.get("subfolder", "") != "":
            raise EngineError("E_ENGINE：引擎回報的參考圖名稱不符")
        return name

    def cancel_owned(self, prompt_id: str, *, exclusive_engine: bool) -> str:
        validate_id(prompt_id)
        if not exclusive_engine:
            raise ValidationError("未持有引擎所有權，不可中斷")
        queue = self.queue()
        if any(item[1] == prompt_id for item in queue.get("queue_pending", [])):
            self._json("/queue", {"delete": [prompt_id]})
            return "cancelling"
        if any(item[1] == prompt_id for item in queue.get("queue_running", [])):
            self._json("/interrupt", {"prompt_id": prompt_id})
            return "cancelling"
        return "not_queued"
