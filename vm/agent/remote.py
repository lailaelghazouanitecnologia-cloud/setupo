import asyncio
import logging
import os
import shutil
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from auth import AdminUser, require_admin, verify_token

logger = logging.getLogger("nso-agent.remote")
router = APIRouter(prefix="/remote", tags=["remote"])

MOS_GATEWAY_BIND = os.environ.get("MOS_GATEWAY_BIND", "127.0.0.1:8091")
MOS_GATEWAY_COMMAND = os.environ.get("MOS_GATEWAY_COMMAND", "/opt/nso/bin/mos-gateway")
MOS_GATEWAY_START_TIMEOUT = float(os.environ.get("MOS_GATEWAY_START_TIMEOUT", "8"))
MOS_GATEWAY_URL = f"http://{MOS_GATEWAY_BIND}"
MOS_GATEWAY_WS_URL = f"ws://{MOS_GATEWAY_BIND}"

_gateway_lock = asyncio.Lock()
_gateway_proc: asyncio.subprocess.Process | None = None


def _resolve_gateway_command() -> str | None:
    explicit = MOS_GATEWAY_COMMAND.strip()
    explicit_head = explicit.split(" ")[0]
    if explicit and os.path.exists(explicit_head):
        return explicit

    cargo = shutil.which("cargo")
    manifest = "/opt/nso/vm/mos-gateway/Cargo.toml"
    if cargo and os.path.exists(manifest):
        return f"{cargo} run --manifest-path {manifest}"

    return None


async def _gateway_health() -> tuple[bool, dict[str, Any] | None]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{MOS_GATEWAY_URL}/health")
        if resp.status_code == 200:
            return True, resp.json()
    except Exception:
        pass
    return False, None


async def _ensure_gateway_running() -> dict[str, Any]:
    ok, data = await _gateway_health()
    if ok and data:
        return data

    async with _gateway_lock:
        ok, data = await _gateway_health()
        if ok and data:
            return data

        global _gateway_proc
        if _gateway_proc and _gateway_proc.returncode is None:
            await _wait_for_gateway()
            ok, data = await _gateway_health()
            if ok and data:
                return data

        command = _resolve_gateway_command()
        if not command:
            raise HTTPException(
                503,
                f"mos-gateway binary not found: {MOS_GATEWAY_COMMAND}. "
                "Build and install the Rust gateway first or set MOS_GATEWAY_COMMAND.",
            )

        logger.info("Starting mos-gateway: %s", command)
        _gateway_proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        await _wait_for_gateway()
        ok, data = await _gateway_health()
        if ok and data:
            return data

        raise HTTPException(502, "mos-gateway failed to start or did not become healthy")


async def _wait_for_gateway():
    deadline = time.monotonic() + MOS_GATEWAY_START_TIMEOUT
    while time.monotonic() < deadline:
        ok, _ = await _gateway_health()
        if ok:
            return
        await asyncio.sleep(0.25)


async def _stop_gateway_process() -> bool:
    global _gateway_proc
    if not _gateway_proc or _gateway_proc.returncode is not None:
        _gateway_proc = None
        return False

    _gateway_proc.terminate()
    try:
        await asyncio.wait_for(_gateway_proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        _gateway_proc.kill()
        await _gateway_proc.wait()
    finally:
        _gateway_proc = None
    return True


async def _proxy(method: str, path: str, *, json: Any = None) -> JSONResponse:
    await _ensure_gateway_running()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, f"{MOS_GATEWAY_URL}{path}", json=json)
    try:
        body = resp.json()
    except Exception:
        body = {"detail": resp.text}
    return JSONResponse(status_code=resp.status_code, content=body)


@router.get("/health")
async def remote_health(admin: AdminUser = Depends(require_admin)):
    ok, data = await _gateway_health()
    return {
        "ok": ok,
        "gateway_url": MOS_GATEWAY_URL,
        "gateway_command": MOS_GATEWAY_COMMAND,
        "gateway": data,
    }


@router.get("/gateway/status")
async def gateway_status(admin: AdminUser = Depends(require_admin)):
    ok, data = await _gateway_health()
    return {
        "ok": ok,
        "running": ok,
        "gateway": data,
        "command": MOS_GATEWAY_COMMAND,
        "bind": MOS_GATEWAY_BIND,
    }


@router.post("/gateway/start")
async def gateway_start(admin: AdminUser = Depends(require_admin)):
    data = await _ensure_gateway_running()
    return {"ok": True, "gateway": data, "bind": MOS_GATEWAY_BIND}


@router.post("/gateway/stop")
async def gateway_stop(admin: AdminUser = Depends(require_admin)):
    stopped = await _stop_gateway_process()
    return {"ok": True, "stopped": stopped}


@router.post("/sessions")
async def create_session(req: Request, admin: AdminUser = Depends(require_admin)):
    body = await req.json()
    return await _proxy("POST", "/sessions", json=body)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, admin: AdminUser = Depends(require_admin)):
    return await _proxy("GET", f"/sessions/{session_id}")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, admin: AdminUser = Depends(require_admin)):
    return await _proxy("DELETE", f"/sessions/{session_id}")


@router.get("/sessions/{session_id}/framebuffer")
async def get_framebuffer(session_id: str, admin: AdminUser = Depends(require_admin)):
    return await _proxy("GET", f"/sessions/{session_id}/framebuffer")


@router.post("/sessions/{session_id}/input")
async def send_input(session_id: str, req: Request, admin: AdminUser = Depends(require_admin)):
    body = await req.json()
    return await _proxy("POST", f"/sessions/{session_id}/input", json=body)


@router.post("/sessions/{session_id}/clipboard")
async def send_clipboard(session_id: str, req: Request, admin: AdminUser = Depends(require_admin)):
    body = await req.json()
    return await _proxy("POST", f"/sessions/{session_id}/clipboard", json=body)


@router.websocket("/sessions/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token", "")
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    try:
        await _ensure_gateway_running()
    except HTTPException as e:
        await websocket.close(code=1013, reason=str(e.detail))
        return
    await websocket.accept()

    query = urlencode({"token": token}) if token else ""
    target_url = f"{MOS_GATEWAY_WS_URL}/sessions/{session_id}/stream"
    if query:
        target_url = f"{target_url}?{query}"

    try:
        async with websockets.connect(target_url) as upstream:
            async def client_to_upstream():
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if "text" in msg and msg["text"] is not None:
                        await upstream.send(msg["text"])
                    elif "bytes" in msg and msg["bytes"] is not None:
                        await upstream.send(msg["bytes"])

            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.warning("remote stream proxy error: %s", e)
        try:
            await websocket.close(code=1011, reason="Gateway stream error")
        except Exception:
            pass
