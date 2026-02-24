"""MMS Terminal - Real system shell via WebSocket PTY."""
import asyncio
import os
import pty
import select
import struct
import fcntl
import termios
import logging
import signal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from server.auth import load_token

logger = logging.getLogger("mms.terminal")
router = APIRouter()


@router.websocket("/shell")
async def ws_shell(ws: WebSocket, token: str = Query("")):
    """Real bash PTY over WebSocket."""
    import secrets
    if not secrets.compare_digest(token, load_token()):
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()

    # Create PTY
    master_fd, slave_fd = pty.openpty()

    # Fork process
    pid = os.fork()
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()
        # Set controlling terminal
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
        os.execvpe("/bin/bash", ["/bin/bash", "--login"], {
            "TERM": "xterm-256color",
            "HOME": os.environ.get("HOME", "/root"),
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "en_US.UTF-8",
            "SHELL": "/bin/bash",
        })

    # Parent process
    os.close(slave_fd)

    # Make master_fd non-blocking
    import fcntl as fcntl_mod
    flags = fcntl_mod.fcntl(master_fd, fcntl_mod.F_GETFL)
    fcntl_mod.fcntl(master_fd, fcntl_mod.F_SETFL, flags | os.O_NONBLOCK)

    logger.info("Terminal session started (pid=%d)", pid)

    async def read_pty():
        """Read from PTY and send to WebSocket."""
        loop = asyncio.get_event_loop()
        try:
            while True:
                await asyncio.sleep(0.01)
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        await ws.send_bytes(data)
                except OSError:
                    await asyncio.sleep(0.05)
        except Exception:
            pass

    reader_task = asyncio.create_task(read_pty())

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "bytes" in msg and msg["bytes"]:
                os.write(master_fd, msg["bytes"])
            elif "text" in msg and msg["text"]:
                text = msg["text"]
                # Handle resize: JSON {"type":"resize","cols":80,"rows":24}
                if text.startswith("{"):
                    import json
                    try:
                        data = json.loads(text)
                        if data.get("type") == "resize":
                            cols = data.get("cols", 80)
                            rows = data.get("rows", 24)
                            winsize = struct.pack("HHHH", rows, cols, 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            continue
                    except json.JSONDecodeError:
                        pass
                os.write(master_fd, text.encode())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Terminal error: %s", e)
    finally:
        reader_task.cancel()
        os.close(master_fd)
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except Exception:
            pass
        logger.info("Terminal session ended (pid=%d)", pid)
