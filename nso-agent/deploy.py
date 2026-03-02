import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from auth import require_admin, AdminUser

logger = logging.getLogger("nso-agent.deploy")
router = APIRouter(prefix="/deploy", tags=["deploy"])
APP_DIR = Path("/opt/app")
SNAPSHOTS_DIR = Path("/opt/nso/snapshots")
NSO_DIR = Path("/opt/nso")
DEPLOY_STATE_FILE = Path("/opt/nso/data/deploy-state.json")
MAX_SNAPSHOTS = 5
R2_DOWNLOAD_TIMEOUT = 120.0
DEPS_INSTALL_TIMEOUT = 300
MAX_LOG_LINES = 500

INSTALL_COMMANDS = {
    "node": "npm install --production 2>&1",
    "python": "pip install -r requirements.txt 2>&1",
    "go": "go build ./... 2>&1",
    "rust": "cargo build --release 2>&1",
    "docker": "docker compose up -d --build 2>&1",
    "static": "echo ok",
}

STACK_INDICATORS = [
    ("package.json", "node"),
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("pyproject.toml", "python"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("Dockerfile", "docker"),
    ("docker-compose.yml", "docker"),
    ("index.html", "static"),
]

class PullRequest(BaseModel):
    r2_key: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    target_dir: str = "/opt/app"
    restart_service: str = "nso-app"
    install_deps: bool = True


class SelfUpdateRequest(BaseModel):
    component: str
    r2_key: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str


class DeployStatus(BaseModel):
    current_version: str = ""
    current_hash: str = ""
    workspace: str = ""
    branch: str = ""
    deployed_at: str = ""
    stack: str = ""
    snapshots: list[str] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    snapshot: str = ""


COMPONENT_MAP = {
    "agent": {"target": "/opt/nso/nso-agent", "service": "nso-agent"},
    "frontend": {"target": "/opt/nso/dashboard/static", "service": None},
    "core": {"target": "/opt/nso", "service": "nso"},
}


def _detect_stack(directory: str) -> str:
    for filename, stack in STACK_INDICATORS:
        if os.path.exists(os.path.join(directory, filename)):
            return stack
    return "unknown"


def _load_state() -> dict:
    if DEPLOY_STATE_FILE.exists():
        try:
            return json.loads(DEPLOY_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    DEPLOY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEPLOY_STATE_FILE.write_text(json.dumps(state, indent=2))


def _list_snapshots(target_dir: str = "/opt/app") -> list[str]:
    snap_dir = SNAPSHOTS_DIR / Path(target_dir).name
    if not snap_dir.exists():
        return []
    snaps = sorted(snap_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return [s.name for s in snaps if s.is_dir()]


def _create_snapshot(target_dir: str) -> str | None:
    target = Path(target_dir)
    if not target.exists() or not any(target.iterdir()):
        return None

    snap_name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_dir = SNAPSHOTS_DIR / target.name / snap_name
    snap_dir.parent.mkdir(parents=True, exist_ok=True)

    shutil.copytree(target, snap_dir, dirs_exist_ok=True)
    logger.info("Created snapshot: %s", snap_dir)

    all_snaps = _list_snapshots(target_dir)
    for old in all_snaps[MAX_SNAPSHOTS:]:
        old_path = SNAPSHOTS_DIR / target.name / old
        shutil.rmtree(old_path, ignore_errors=True)
        logger.info("Pruned old snapshot: %s", old)

    return snap_name


def _restore_snapshot(target_dir: str, snapshot_name: str) -> bool:
    target = Path(target_dir)
    snap_path = SNAPSHOTS_DIR / target.name / snapshot_name
    if not snap_path.exists():
        return False

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(snap_path, target)
    logger.info("Restored snapshot %s → %s", snapshot_name, target_dir)
    return True


async def _download_from_r2(
    endpoint: str, bucket: str, key: str,
    access_key: str, secret_key: str,
) -> bytes:
    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    host = endpoint.replace("https://", "").replace("http://", "")
    empty_hash = hashlib.sha256(b"").hexdigest()
    region = "auto"
    service = "s3"

    headers_to_sign = {
        "host": host,
        "x-amz-content-sha256": empty_hash,
        "x-amz-date": amz_date,
    }
    signed_header_keys = sorted(headers_to_sign.keys())
    signed_headers = ";".join(signed_header_keys)
    canonical_headers = "".join(f"{k}:{headers_to_sign[k]}\n" for k in signed_header_keys)

    canonical_request = (
        f"GET\n/{bucket}/{quote(key, safe='/')}\n\n"
        f"{canonical_headers}\n{signed_headers}\n{empty_hash}"
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _hmac(k: bytes, m: str) -> bytes:
        return hmac_mod.new(k, m.encode(), hashlib.sha256).digest()

    signing_key = _hmac(_hmac(_hmac(_hmac(
        f"AWS4{secret_key}".encode(), date_stamp), region), service), "aws4_request")
    signature = hmac_mod.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"{endpoint}/{bucket}/{quote(key, safe='/')}"
    async with httpx.AsyncClient(timeout=R2_DOWNLOAD_TIMEOUT) as client:
        resp = await client.get(url, headers={
            "Authorization": auth_header,
            "x-amz-content-sha256": empty_hash,
            "x-amz-date": amz_date,
        })
    if resp.status_code != 200:
        raise HTTPException(502, f"R2 download failed: {resp.status_code} {resp.text[:200]}")
    return resp.content


def _extract_zar(zar_bytes: bytes, target_dir: str) -> dict:
    target = Path(target_dir)
    env_backup = None
    env_path = target / ".env"
    if env_path.exists():
        env_backup = env_path.read_text()

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    manifest = {}
    with tarfile.open(fileobj=BytesIO(zar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                logger.warning("Skipping unsafe path: %s", member.name)
                continue

            if member.name == ".zar-manifest.json":
                f = tar.extractfile(member)
                if f:
                    manifest = json.loads(f.read())
                tar.extract(member, target)
                continue
            if member.name == "config.toml":
                tar.extract(member, target)
                continue
            if member.name.startswith("files/"):
                member.name = member.name[6:]
                if member.name:
                    resolved = (target / member.name).resolve()
                    if not str(resolved).startswith(str(target.resolve())):
                        logger.warning("Skipping path traversal: %s", member.name)
                        continue
                    tar.extract(member, target)

    if env_backup:
        env_path.write_text(env_backup)

    return manifest


async def _install_deps(target_dir: str, stack: str) -> tuple[str, int]:
    cmd = INSTALL_COMMANDS.get(stack)
    if not cmd:
        return "No install command for stack", 0

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=target_dir,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=DEPS_INSTALL_TIMEOUT)
    return stdout.decode(errors="replace"), proc.returncode


async def _restart_service(name: str) -> tuple[str, int]:
    if not name:
        return "", 0
    proc = await asyncio.create_subprocess_shell(
        f"systemctl restart {name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode(errors="replace"), proc.returncode

@router.post("/pull")
async def deploy_pull(req: PullRequest, admin: AdminUser = Depends(require_admin)):
    logger.info("Deploy pull: %s → %s", req.r2_key, req.target_dir)

    zar_bytes = await _download_from_r2(
        req.r2_endpoint, req.r2_bucket, req.r2_key,
        req.r2_access_key_id, req.r2_secret_access_key,
    )
    logger.info("Downloaded %d bytes from R2", len(zar_bytes))

    snap = _create_snapshot(req.target_dir)
    if snap:
        logger.info("Snapshot created: %s", snap)

    manifest = _extract_zar(zar_bytes, req.target_dir)
    logger.info("Extracted to %s", req.target_dir)

    install_output = ""
    stack = manifest.get("stack", "") or _detect_stack(req.target_dir)
    if req.install_deps and stack not in ("static", "unknown", ""):
        install_output, code = await _install_deps(req.target_dir, stack)
        if code != 0:
            logger.error("Dep install failed (code %d), rolling back", code)
            if snap:
                _restore_snapshot(req.target_dir, snap)
                await _restart_service(req.restart_service)
            raise HTTPException(500, f"Dependency install failed: {install_output[-500:]}")

    restart_out, restart_code = await _restart_service(req.restart_service)
    if restart_code != 0:
        logger.error("Service restart failed, rolling back")
        if snap:
            _restore_snapshot(req.target_dir, snap)
            await _restart_service(req.restart_service)
        raise HTTPException(500, f"Service restart failed: {restart_out}")

    state = _load_state()
    state[req.target_dir] = {
        "version": manifest.get("version", ""),
        "hash": manifest.get("hash", ""),
        "workspace": manifest.get("name", ""),
        "branch": manifest.get("branch", ""),
        "stack": stack,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": snap,
    }
    _save_state(state)

    return {
        "ok": True,
        "version": manifest.get("version", ""),
        "workspace": manifest.get("name", ""),
        "stack": stack,
        "snapshot": snap,
        "install_output": install_output[-500:] if install_output else "",
    }


@router.post("/upload")
async def deploy_upload(
    file: UploadFile = File(...),
    target_dir: str = "/opt/app",
    restart_service: str = "nso-app",
    install_deps: bool = True,
    admin: AdminUser = Depends(require_admin),
):
    zar_bytes = await file.read()
    logger.info("Received upload: %d bytes → %s", len(zar_bytes), target_dir)

    snap = _create_snapshot(target_dir)
    manifest = _extract_zar(zar_bytes, target_dir)
    stack = manifest.get("stack", "") or _detect_stack(target_dir)

    if install_deps and stack not in ("static", "unknown", ""):
        output, code = await _install_deps(target_dir, stack)
        if code != 0:
            if snap:
                _restore_snapshot(target_dir, snap)
            raise HTTPException(500, f"Dependency install failed: {output[-500:]}")

    restart_out, restart_code = await _restart_service(restart_service)
    if restart_code != 0:
        if snap:
            _restore_snapshot(target_dir, snap)
            await _restart_service(restart_service)
        raise HTTPException(500, f"Service restart failed: {restart_out}")

    state = _load_state()
    state[target_dir] = {
        "version": manifest.get("version", ""),
        "hash": manifest.get("hash", ""),
        "workspace": manifest.get("name", ""),
        "branch": manifest.get("branch", ""),
        "stack": stack,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": snap,
    }
    _save_state(state)

    return {
        "ok": True,
        "version": manifest.get("version", ""),
        "workspace": manifest.get("name", ""),
        "stack": stack,
        "snapshot": snap,
    }


@router.post("/rollback")
async def deploy_rollback(
    req: RollbackRequest,
    target_dir: str = "/opt/app",
    restart_service: str = "nso-app",
    admin: AdminUser = Depends(require_admin),
):
    snaps = _list_snapshots(target_dir)
    if not snaps:
        raise HTTPException(404, "No snapshots available")

    snap_name = req.snapshot or snaps[0]
    if snap_name not in snaps:
        raise HTTPException(404, f"Snapshot '{snap_name}' not found")

    ok = _restore_snapshot(target_dir, snap_name)
    if not ok:
        raise HTTPException(500, "Snapshot restore failed")

    out, code = await _restart_service(restart_service)

    state = _load_state()
    state[target_dir] = {
        **state.get(target_dir, {}),
        "version": f"rollback:{snap_name}",
        "deployed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(state)

    return {"ok": True, "restored": snap_name, "service_restart": code == 0}


@router.get("/current")
async def deploy_current(admin: AdminUser = Depends(require_admin)):
    state = _load_state()
    result = {}
    for target_dir, info in state.items():
        info["snapshots"] = _list_snapshots(target_dir)
        result[target_dir] = info
    return result


@router.get("/snapshots")
async def deploy_snapshots(
    target_dir: str = "/opt/app",
    admin: AdminUser = Depends(require_admin),
):
    return {"target": target_dir, "snapshots": _list_snapshots(target_dir)}


@router.post("/self-update")
async def self_update(req: SelfUpdateRequest, admin: AdminUser = Depends(require_admin)):
    if req.component not in COMPONENT_MAP:
        raise HTTPException(400, f"Unknown component: {req.component}. Use: {list(COMPONENT_MAP.keys())}")

    comp = COMPONENT_MAP[req.component]
    target = comp["target"]
    service = comp["service"]

    logger.info("Self-update: %s → %s", req.component, target)

    zar_bytes = await _download_from_r2(
        req.r2_endpoint, req.r2_bucket, req.r2_key,
        req.r2_access_key_id, req.r2_secret_access_key,
    )

    snap = _create_snapshot(target)
    manifest = _extract_zar(zar_bytes, target)

    if req.component in ("agent", "core"):
        req_file = os.path.join(target, "requirements.txt")
        if os.path.exists(req_file):
            proc = await asyncio.create_subprocess_shell(
                f"/opt/nso/venv/bin/pip install -r {req_file} --quiet 2>&1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.communicate()

    restart_ok = True
    if service:
        out, code = await _restart_service(service)
        if code != 0:
            logger.error("Self-update restart failed for %s, rolling back", service)
            if snap:
                _restore_snapshot(target, snap)
                await _restart_service(service)
            raise HTTPException(500, f"Service restart failed after update: {out}")
        restart_ok = code == 0

    state = _load_state()
    state[f"self:{req.component}"] = {
        "version": manifest.get("version", ""),
        "hash": manifest.get("hash", ""),
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": snap,
    }
    _save_state(state)

    return {
        "ok": True,
        "component": req.component,
        "version": manifest.get("version", ""),
        "snapshot": snap,
        "restarted": service,
        "restart_ok": restart_ok,
    }
