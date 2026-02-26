"""NSO API client — HTTP layer for the CLI.

Handles auth, retries, timeouts, and error formatting.
All methods return (success: bool, data: dict) tuples.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

CONFIG_DIR = Path.home() / ".nso"
TOKEN_FILE = CONFIG_DIR / "token"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_TIMEOUT = 30
DEPLOY_TIMEOUT = 300  # 5 min for deploys
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]


def _load_config() -> dict:
    """Load CLI config from ~/.nso/config.json."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save_config(config: dict):
    """Save CLI config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_host() -> str:
    """Get the API host URL."""
    env = os.environ.get("NSO_HOST")
    if env:
        return env.rstrip("/")
    config = _load_config()
    return config.get("host", "http://localhost:8000")


def set_host(host: str):
    """Set the API host URL."""
    config = _load_config()
    config["host"] = host.rstrip("/")
    _save_config(config)


def get_token() -> str | None:
    """Read stored auth token."""
    # 1. Environment variable
    env = os.environ.get("NSO_TOKEN")
    if env:
        return env
    # 2. Token file
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def save_token(token: str):
    """Save auth token to ~/.nso/token."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)


def clear_token():
    """Remove stored token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 0,
) -> tuple[bool, dict]:
    """Make an HTTP request to the NSO API.

    Returns (success, response_data).
    On error returns (False, {"error": "message"}).
    """
    host = get_host()
    url = f"{host}{path}"
    token = get_token()

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)

    attempt = 0
    max_attempts = 1 + retries

    while attempt < max_attempts:
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                try:
                    return True, json.loads(raw)
                except json.JSONDecodeError:
                    return True, {"raw": raw}

        except HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode()
            except Exception:
                pass

            try:
                err_data = json.loads(body_text)
            except (json.JSONDecodeError, ValueError):
                err_data = {"error": body_text or str(e)}

            if e.code == 401:
                err_data["error"] = err_data.get("error", "Unauthorized — run: nso login")
            elif e.code == 404:
                err_data["error"] = err_data.get("error", f"Not found: {path}")

            return False, err_data

        except (URLError, ConnectionError, TimeoutError) as e:
            attempt += 1
            if attempt < max_attempts:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                print(f"  Connection failed, retrying in {wait}s... ({attempt}/{retries})")
                time.sleep(wait)
            else:
                return False, {"error": f"Connection failed: {e}"}

    return False, {"error": "Max retries exceeded"}


def get(path: str, **kwargs) -> tuple[bool, dict]:
    return _request("GET", path, **kwargs)


def post(path: str, body: dict | None = None, **kwargs) -> tuple[bool, dict]:
    return _request("POST", path, body=body, **kwargs)


def delete(path: str, **kwargs) -> tuple[bool, dict]:
    return _request("DELETE", path, **kwargs)


def put(path: str, body: dict | None = None, **kwargs) -> tuple[bool, dict]:
    return _request("PUT", path, body=body, **kwargs)
