"""WebSocket endpoint for real-time terminal access to capsules."""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.auth import load_token

logger = logging.getLogger("mms.ws")
router = APIRouter()


@router.websocket("/terminal/{capsule_id}")
async def terminal(websocket: WebSocket, capsule_id: str):
    """WebSocket terminal - stream commands to a capsule in real time."""
    # Auth via query param: ws://host/ws/terminal/id?token=xxx
    token = websocket.query_params.get("token", "")
    if token != load_token():
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    engine = websocket.app.state.engine
    capsule = await engine.store.get_capsule(capsule_id)

    if not capsule:
        await websocket.send_json({"type": "error", "data": "Capsule not found"})
        await websocket.close()
        return

    if capsule["state"] != "running":
        await websocket.send_json({"type": "error", "data": "Capsule is not running"})
        await websocket.close()
        return

    await websocket.send_json({"type": "connected", "data": f"Connected to {capsule['name']}"})

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)

            if data.get("type") == "exec":
                command = data.get("command", "")
                result = await engine.exec_in_capsule(capsule_id, command, timeout=30)
                await websocket.send_json({
                    "type": "output",
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", -1),
                })

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Terminal disconnected for capsule %s", capsule_id)
    except Exception as e:
        logger.error("Terminal error for %s: %s", capsule_id, e)
        await websocket.close()


@router.websocket("/logs/{capsule_id}")
async def stream_logs(websocket: WebSocket, capsule_id: str):
    """WebSocket log stream - follow capsule logs in real time."""
    token = websocket.query_params.get("token", "")
    if token != load_token():
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    engine = websocket.app.state.engine
    last_count = 0

    try:
        while True:
            logs = await engine.store.get_logs(capsule_id, limit=50)
            if len(logs) > last_count:
                new_logs = logs[:len(logs) - last_count]
                for log in reversed(new_logs):
                    await websocket.send_json({
                        "type": "log",
                        "level": log.get("level", "info"),
                        "message": log.get("message", ""),
                        "timestamp": log.get("created_at", ""),
                    })
                last_count = len(logs)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
