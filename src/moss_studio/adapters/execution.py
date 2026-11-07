"""Private ComfyUI WebSocket events + HTTP history, with no inference resubmission."""

import asyncio
import json
import time
from urllib.parse import urlencode

from moss_studio.adapters.comfy import ComfyClient, EngineError, EngineSettledError
from moss_studio.domain.contracts import new_id


def execute_graph(graph: dict, prompt_id: str, on_event, timeout: float = 900) -> list[bytes]:
    import aiohttp

    async def execute():
        client_id = new_id()
        base = "http://127.0.0.1:8188"
        client = ComfyClient()
        async with aiohttp.ClientSession(trust_env=False) as session:
            async with session.ws_connect(
                base + "/ws?" + urlencode({"clientId": client_id}), heartbeat=20
            ) as ws:
                on_event("before_submit", {})
                async with session.post(
                    base + "/prompt",
                    json={"prompt": graph, "client_id": client_id, "prompt_id": prompt_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        raise EngineError("E_ENGINE：工作流被引擎拒絕")
                    accepted = await response.json()
                    if accepted.get("prompt_id") != prompt_id:
                        raise EngineError("E_ENGINE：引擎工作識別碼不符")
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        message = await ws.receive(timeout=60)
                    except TimeoutError:
                        history = client.history(prompt_id).get(prompt_id)
                        if history:
                            break
                        on_event("diagnostic", {"code": "E_STALLED"})
                        continue
                    if message.type == aiohttp.WSMsgType.BINARY:
                        continue  # Preview is optional; never treat it as a saved result.
                    if message.type != aiohttp.WSMsgType.TEXT:
                        history = client.history(prompt_id).get(prompt_id)
                        if history:
                            break
                        raise EngineError("E_ENGINE：事件連線中斷，請核對既有工作")
                    event = json.loads(message.data)
                    data = event.get("data", {})
                    if data.get("prompt_id", prompt_id) != prompt_id:
                        continue
                    on_event(event.get("type"), data)
                    if event.get("type") in {
                        "execution_success",
                        "execution_error",
                        "execution_interrupted",
                    }:
                        break
                    if event.get("type") == "executing" and data.get("node") is None:
                        break
                else:
                    raise EngineError("E_ENGINE：工作逾時，請先核對原工作紀錄")
            history = client.history(prompt_id).get(prompt_id)
            for _ in range(50):
                if history:
                    break
                await asyncio.sleep(0.1)
                history = client.history(prompt_id).get(prompt_id)
            if not history:
                raise EngineError("E_ENGINE：工作未成功，輸入與工作紀錄仍保留")
            if history["status"]["status_str"] != "success":
                raise EngineSettledError("E_ENGINE：引擎已結束此工作，未產生成功結果")
            outputs = history["outputs"]
            # Node "9" is always the result; other SaveImage nodes (e.g. the estimated
            # control map) are auxiliary outputs returned after it, in node order.
            main = outputs.get("9", {}).get("images", [])
            if len(main) != 1:
                raise EngineError("E_ENGINE：預期單張輸出，請核對工作流")
            extras = [
                image
                for node in sorted(outputs, key=str)
                if node != "9"
                for image in outputs[node].get("images", [])
                if image.get("type") == "output"
            ]
            if len(extras) > 4:
                raise EngineError("E_ENGINE：輔助輸出過多，請核對工作流")
            files = []
            for image in [*main, *extras]:
                query = urlencode({key: image[key] for key in ("filename", "subfolder", "type")})
                async with session.get(
                    base + "/view?" + query, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise EngineError("E_ENGINE：輸出讀取失敗")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(1024**2):
                        size += len(chunk)
                        if size > 32 * 1024**2:
                            raise EngineError("E_ENGINE：輸出超過限制")
                        chunks.append(chunk)
                    files.append(b"".join(chunks))
            return files

    return asyncio.run(execute())
