"""Setupo Slave Agent - Runs inside each VM/MicroVM.
Exposes a local HTTP API on port 9000 for the orchestrator to control.
Handles command execution, capsule management, and health reporting.
"""
import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from urllib.request import urlopen, Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [slave] %(message)s",
)
logger = logging.getLogger("slave")

MASTER_IP = os.environ.get("SETUPO_MASTER", "172.16.0.1")
MASTER_PORT = os.environ.get("SETUPO_MASTER_PORT", "8000")
SLAVE_PORT = int(os.environ.get("SETUPO_SLAVE_PORT", "9000"))
INSTANCE_ID = os.environ.get("SETUPO_INSTANCE_ID", "unknown")


class SlaveHandler(BaseHTTPRequestHandler):
    """HTTP request handler for slave agent."""

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, self._health_info())
        elif self.path == "/info":
            self._respond(200, self._system_info())
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()

        if self.path == "/exec":
            result = self._exec_command(body.get("command", ""))
            self._respond(200, result)

        elif self.path == "/capsule/install":
            result = self._install_capsule(body.get("name", ""), body.get("script", ""))
            self._respond(200, result)

        elif self.path == "/file/write":
            result = self._write_file(body.get("path", ""), body.get("content", ""))
            self._respond(200, result)

        elif self.path == "/file/read":
            result = self._read_file(body.get("path", ""))
            self._respond(200, result)

        else:
            self._respond(404, {"error": "not found"})

    def _exec_command(self, command: str) -> dict:
        """Execute a shell command and return output."""
        logger.info("Executing: %s", command[:100])
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out (300s)", "returncode": -1}
        except Exception as e:
            return {"error": str(e), "returncode": -1}

    def _install_capsule(self, name: str, script: str) -> dict:
        """Install a capsule by running its install script."""
        logger.info("Installing capsule: %s", name)
        capsule_dir = f"/opt/capsules/{name}"
        os.makedirs(capsule_dir, exist_ok=True)

        script_path = f"{capsule_dir}/install.sh"
        with open(script_path, "w") as f:
            f.write(script)
        os.chmod(script_path, 0o755)

        return self._exec_command(f"bash {script_path}")

    def _write_file(self, path: str, content: str) -> dict:
        """Write content to a file on this VM."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return {"status": "ok", "path": path}
        except Exception as e:
            return {"error": str(e)}

    def _read_file(self, path: str) -> dict:
        """Read a file from this VM."""
        try:
            with open(path) as f:
                return {"content": f.read(), "path": path}
        except FileNotFoundError:
            return {"error": f"File not found: {path}"}
        except Exception as e:
            return {"error": str(e)}

    def _health_info(self) -> dict:
        disk = shutil.disk_usage("/")
        return {
            "status": "ok",
            "instance_id": INSTANCE_ID,
            "uptime": time.time(),
            "disk_free_mb": disk.free // (1024 * 1024),
        }

    def _system_info(self) -> dict:
        return {
            "instance_id": INSTANCE_ID,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "hostname": platform.node(),
        }

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        logger.debug(format, *args)


def register_with_master():
    """Register this slave with the orchestrator."""
    try:
        data = json.dumps({
            "instance_id": INSTANCE_ID,
            "port": SLAVE_PORT,
        }).encode()
        req = Request(
            f"http://{MASTER_IP}:{MASTER_PORT}/api/slave/register",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urlopen(req, timeout=10)
        logger.info("Registered with master at %s:%s", MASTER_IP, MASTER_PORT)
    except Exception as e:
        logger.warning("Could not register with master: %s", e)


def heartbeat_loop():
    """Send periodic heartbeats to the master."""
    while True:
        try:
            data = json.dumps({
                "instance_id": INSTANCE_ID,
                "status": "alive",
            }).encode()
            req = Request(
                f"http://{MASTER_IP}:{MASTER_PORT}/api/slave/heartbeat",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urlopen(req, timeout=5)
        except Exception:
            pass
        time.sleep(30)


def main():
    logger.info("Setupo Slave Agent starting on port %d (ID: %s)", SLAVE_PORT, INSTANCE_ID)

    # Register with master
    register_with_master()

    # Start heartbeat in background
    hb = Thread(target=heartbeat_loop, daemon=True)
    hb.start()

    # Start HTTP server
    server = HTTPServer(("0.0.0.0", SLAVE_PORT), SlaveHandler)
    logger.info("Slave agent listening on 0.0.0.0:%d", SLAVE_PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
