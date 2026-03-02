#!/usr/bin/env python3
"""NSO CLI — Manage infrastructure from the terminal.

Usage:
    nso <command> [args] [options]

Deploy:
    nso ship <workspace> <instance>      Pack + push + deploy (all-in-one)
    nso deploy <workspace> <instance>    Deploy from R2 to instance
    nso rollback <workspace> <instance>  Restore previous snapshot
    nso pack <workspace>                 Pack workspace into .zar
    nso push <workspace>                 Push .zar to R2
    nso update <instance>                Self-update agent/frontend/core

Versioning:
    nso versions <workspace>             List versions and branches
    nso branch <workspace> <name>        Create branch from main
    nso merge <workspace> <from> <to>    Merge branches

Resources:
    nso projects [ls|create|rm]          Manage projects
    nso inst [ls|create|rm|status]       Manage VPS instances
    nso ws [ls|create]                   Manage workspaces
    nso exec <instance> <command...>     Run command on instance

System:
    nso login                            Authenticate
    nso status                           Quick overview
    nso doctor                           Diagnose problems
"""
import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ═══════════════════════════════════════════════════════════════════
# Output formatting
# ═══════════════════════════════════════════════════════════════════

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

if not sys.stdout.isatty():
    RED = GREEN = YELLOW = BLUE = CYAN = DIM = BOLD = RESET = ""


def out_ok(msg: str):
    print(f"{GREEN}OK{RESET} {msg}")


def out_err(msg: str):
    print(f"{RED}ERROR{RESET} {msg}", file=sys.stderr)


def out_warn(msg: str):
    print(f"{YELLOW}WARN{RESET} {msg}")


def out_info(msg: str):
    print(f"{BLUE}>{RESET} {msg}")


def out_dim(msg: str):
    print(f"{DIM}{msg}{RESET}")


def out_header(msg: str):
    print(f"\n{BOLD}{msg}{RESET}")
    print(f"{DIM}{'─' * min(len(msg) + 4, 60)}{RESET}")


def out_table(rows: list[dict], columns: list[str] | None = None):
    if not rows:
        out_dim("  (empty)")
        return
    if not columns:
        columns = list(rows[0].keys())
    widths = {}
    for col in columns:
        widths[col] = max(
            len(col),
            max((len(str(row.get(col, ""))) for row in rows), default=0),
        )
    hdr = "  ".join(f"{BOLD}{col:<{widths[col]}}{RESET}" for col in columns)
    print(f"  {hdr}")
    sep = "  ".join("─" * widths[col] for col in columns)
    print(f"  {DIM}{sep}{RESET}")
    for row in rows:
        cells = []
        for col in columns:
            val = str(row.get(col, ""))
            if col.lower() in ("status", "state"):
                if val in ("active", "running", "deployed", "ok", "complete"):
                    val = f"{GREEN}{val}{RESET}"
                elif val in ("error", "failed", "destroyed"):
                    val = f"{RED}{val}{RESET}"
                elif val in ("installing", "pending", "deploying"):
                    val = f"{YELLOW}{val}{RESET}"
            cells.append(f"{val:<{widths[col]}}")
        print(f"  {'  '.join(cells)}")


def out_json(data):
    print(json.dumps(data, indent=2))


def out_kv(data: dict, indent: int = 2):
    if not data:
        out_dim("  (empty)")
        return
    max_key = max(len(str(k)) for k in data.keys())
    for k, v in data.items():
        print(f"{' ' * indent}{CYAN}{k:<{max_key}}{RESET}  {v}")


# ═══════════════════════════════════════════════════════════════════
# HTTP client
# ═══════════════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / ".nso"
TOKEN_FILE = CONFIG_DIR / "token"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_TIMEOUT = 30
DEPLOY_TIMEOUT = 300
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_host() -> str:
    env = os.environ.get("NSO_HOST")
    if env:
        return env.rstrip("/")
    config = _load_config()
    return config.get("host", "http://localhost:8000")


def set_host(host: str):
    config = _load_config()
    config["host"] = host.rstrip("/")
    _save_config(config)


def get_token() -> str | None:
    env = os.environ.get("NSO_TOKEN")
    if env:
        return env
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def save_token(token: str):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)


def clear_token():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 0,
) -> tuple[bool, dict]:
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


def http_get(path: str, **kwargs) -> tuple[bool, dict]:
    return _request("GET", path, **kwargs)


def http_post(path: str, body: dict | None = None, **kwargs) -> tuple[bool, dict]:
    return _request("POST", path, body=body, **kwargs)


def http_delete(path: str, **kwargs) -> tuple[bool, dict]:
    return _request("DELETE", path, **kwargs)


def http_put(path: str, body: dict | None = None, **kwargs) -> tuple[bool, dict]:
    return _request("PUT", path, body=body, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _pid(args) -> str:
    pid = getattr(args, "project", None) or os.environ.get("NSO_PROJECT")
    if not pid:
        out_err("No project. Use -p <id> or set NSO_PROJECT")
        sys.exit(1)
    return pid


def _zar_path(pid: str, name: str, endpoint: str) -> str:
    return f"/api/projects/{pid}/zar/{name}/{endpoint}"


# ═══════════════════════════════════════════════════════════════════
# Commands — Auth
# ═══════════════════════════════════════════════════════════════════

def cmd_login(args):
    if args.key:
        if not args.key.startswith("sk_live_"):
            out_warn("API keys should start with 'sk_live_'")
        save_token(args.key)
        out_ok(f"API key saved ({args.key[:12]}...)")
        return 0

    host = args.host or get_host()
    if args.host:
        set_host(args.host)

    email = args.email or input("Email: ")
    password = args.password or getpass.getpass("Password: ")

    out_info(f"Logging in to {host}...")
    ok, data = http_post("/api/auth/login", {"email": email, "password": password})
    if not ok:
        out_err(data.get("error", "Login failed"))
        return 1

    token = data.get("token", "")
    if not token:
        out_err("No token in response")
        return 1

    save_token(token)
    out_ok(f"Logged in as {email}")
    return 0


def cmd_logout(args):
    clear_token()
    out_ok("Logged out")
    return 0


def cmd_config(args):
    if args.key and args.value:
        if args.key == "host":
            set_host(args.value)
            out_ok(f"Host → {args.value}")
        else:
            out_err(f"Unknown key: {args.key}")
            return 1
        return 0
    out_header("Config")
    out_kv({
        "host": get_host(),
        "token": "set" if get_token() else "not set",
        "config": str(CONFIG_DIR),
    })
    return 0


# ═══════════════════════════════════════════════════════════════════
# Commands — Ship / Deploy / Rollback
# ═══════════════════════════════════════════════════════════════════

def cmd_ship(args):
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    out_info(f"Shipping '{args.workspace}' → {args.instance}")
    out_dim("  pack → push R2 → snapshot → extract → restart")

    start = time.time()
    ok, data = http_post(
        _zar_path(pid, args.workspace, "ship"),
        body,
        timeout=DEPLOY_TIMEOUT,
    )
    elapsed = time.time() - start

    if not ok:
        error = data.get("error", "Ship failed")
        if "rollback" in str(data).lower():
            out_err("Ship failed — auto-rollback executed")
            out_warn(f"  {error}")
        else:
            out_err(error)
        return 1

    out_ok(f"Shipped in {elapsed:.1f}s")
    out_kv({
        "Version": data.get("version", "?"),
        "Hash": data.get("hash", "?")[:20] + "...",
        "R2": data.get("r2_key", "?"),
    })
    return 0


def cmd_deploy(args):
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch
    if args.target_dir:
        body["target_dir"] = args.target_dir

    out_info(f"Deploying '{args.workspace}' → {args.instance}")
    out_dim("  snapshot → download → extract → install → restart")

    ok, data = http_post(
        _zar_path(pid, args.workspace, "deploy"),
        body,
        timeout=DEPLOY_TIMEOUT,
        retries=0,
    )

    if not ok:
        error = data.get("error", "Deploy failed")
        if "rollback" in str(data).lower():
            out_err("Deploy failed — auto-rollback executed")
            out_warn(f"  {error}")
            out_info(f"  Restored: {data.get('restored_from', 'latest snapshot')}")
        else:
            out_err(error)
        return 1

    out_ok(f"Deployed v{data.get('version', '?')}")
    return 0


def cmd_rollback(args):
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.snapshot:
        body["snapshot"] = args.snapshot

    out_info(f"Rolling back '{args.workspace}' on {args.instance}...")
    ok, data = http_post(
        _zar_path(pid, args.workspace, "rollback"),
        body,
        timeout=DEPLOY_TIMEOUT,
    )
    if not ok:
        out_err(data.get("error", "Rollback failed"))
        return 1

    out_ok(f"Restored: {data.get('restored_from', 'previous snapshot')}")
    return 0


def cmd_pack(args):
    pid = _pid(args)
    body = {}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    out_info(f"Packing '{args.workspace}'...")
    ok, data = http_post(_zar_path(pid, args.workspace, "pack"), body)
    if not ok:
        out_err(data.get("error", "Pack failed"))
        return 1

    out_ok(f"Packed v{data.get('version', '?')} ({data.get('size', 0)} bytes)")
    return 0


def cmd_push(args):
    pid = _pid(args)
    body = {}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    out_info(f"Pushing '{args.workspace}' to R2...")
    ok, data = http_post(_zar_path(pid, args.workspace, "push"), body, timeout=60)
    if not ok:
        out_err(data.get("error", "Push failed"))
        return 1

    out_ok(f"Pushed: {data.get('r2_key', '?')}")
    return 0


def cmd_update(args):
    pid = _pid(args)
    body = {"instance_id": args.instance, "target": args.target}

    out_info(f"Updating '{args.target}' on {args.instance}...")
    out_dim(f"  Brief restart of {args.target}")

    ok, data = http_post(
        f"/api/projects/{pid}/zar/self-update",
        body,
        timeout=DEPLOY_TIMEOUT,
    )
    if not ok:
        error = data.get("error", "Update failed")
        if "rollback" in str(data).lower():
            out_err("Update failed — rolled back")
        else:
            out_err(error)
        return 1

    out_ok(f"Updated '{args.target}'")
    return 0


# ═══════════════════════════════════════════════════════════════════
# Commands — Versioning
# ═══════════════════════════════════════════════════════════════════

def cmd_versions(args):
    pid = _pid(args)
    ok, data = http_get(_zar_path(pid, args.workspace, "versions"))
    if not ok:
        out_err(data.get("error", "Failed"))
        return 1

    if getattr(args, "json", False):
        out_json(data)
        return 0

    out_header(f"Versions: {args.workspace}")
    branches = data.get("branches", {})
    versions = data.get("versions", [])

    if branches:
        out_info("Branches:")
        for name, ver in branches.items():
            print(f"    {CYAN}{name}{RESET} → {ver}")
    if versions:
        out_info("History:")
        for v in versions:
            print(f"    {v}")
    return 0


def cmd_branch(args):
    pid = _pid(args)
    body = {"to": args.name}
    if args.source:
        body["from"] = args.source

    out_info(f"Branching '{args.workspace}' → '{args.name}'")
    ok, data = http_post(_zar_path(pid, args.workspace, "branch"), body)
    if not ok:
        out_err(data.get("error", "Branch failed"))
        return 1

    out_ok(f"Branch '{args.name}' created")
    return 0


def cmd_merge(args):
    pid = _pid(args)
    body = {"from": args.source, "to": args.to}

    out_info(f"Merging '{args.workspace}': {args.source} → {args.to}")
    ok, data = http_post(_zar_path(pid, args.workspace, "merge"), body)
    if not ok:
        out_err(data.get("error", "Merge failed"))
        return 1

    out_ok(f"Merged {args.source} → {args.to}")
    return 0


# ═══════════════════════════════════════════════════════════════════
# Commands — Resources
# ═══════════════════════════════════════════════════════════════════

def cmd_projects(args):
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = http_get("/api/projects")
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        projects = data if isinstance(data, list) else data.get("projects", [])
        if getattr(args, "json", False):
            out_json(projects)
            return 0
        out_header("Projects")
        if not projects:
            out_dim("  No projects. Create one: nso projects create <name>")
            return 0
        out_table(projects, ["id", "name", "status", "created_at"])
        return 0

    if subcmd == "create":
        out_info(f"Creating '{args.name}'...")
        ok, data = http_post("/api/projects", {"name": args.name})
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        out_ok(f"Project: {data.get('id', '?')}")
        api_key = data.get("api_key", "")
        if api_key:
            out_info(f"API key: {api_key}")
            out_warn("Save this — won't be shown again")
        return 0

    if subcmd in ("rm", "delete"):
        if not getattr(args, "force", False):
            confirm = input(f"Delete '{args.id}'? All instances destroyed. [y/N] ")
            if confirm.lower() != "y":
                return 0
        ok, data = http_delete(f"/api/projects/{args.id}")
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        out_ok(f"Deleted {args.id}")
        return 0

    out_err(f"Unknown: projects {subcmd}")
    return 1


def cmd_instances(args):
    pid = _pid(args)
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = http_get(f"/api/projects/{pid}/instances")
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        instances = data if isinstance(data, list) else data.get("instances", [])
        if getattr(args, "json", False):
            out_json(instances)
            return 0
        out_header(f"Instances ({pid})")
        out_table(instances, ["id", "label", "ip", "status", "region", "plan"])
        return 0

    if subcmd == "create":
        body = {"label": args.label}
        if args.region:
            body["region"] = args.region
        if args.plan:
            body["plan"] = args.plan
        if args.domain:
            body["domain"] = args.domain

        out_info(f"Creating '{args.label}'...")
        out_dim("  1-3 min (VPS + cloud-init)")
        ok, data = http_post(f"/api/projects/{pid}/instances", body, timeout=120)
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        out_ok(f"Instance: {data.get('id', '?')}")
        out_kv({"IP": data.get("ip", "pending"), "Status": data.get("status", "?")})
        return 0

    if subcmd in ("rm", "delete"):
        if not getattr(args, "force", False):
            confirm = input(f"Destroy '{args.id}'? Irreversible. [y/N] ")
            if confirm.lower() != "y":
                return 0
        ok, data = http_delete(f"/api/projects/{pid}/instances/{args.id}")
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        out_ok(f"Destroyed {args.id}")
        return 0

    if subcmd == "status":
        ok, data = http_get(f"/api/projects/{pid}/instances/{args.id}")
        if not ok:
            out_err(data.get("error", "Not found"))
            return 1
        if getattr(args, "json", False):
            out_json(data)
            return 0
        out_header(f"Instance: {data.get('label', args.id)}")
        out_kv(data)
        return 0

    out_err(f"Unknown: inst {subcmd}")
    return 1


def cmd_workspaces(args):
    pid = _pid(args)
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = http_get(f"/api/projects/{pid}/workspaces")
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        workspaces = data if isinstance(data, list) else data.get("workspaces", [])
        if getattr(args, "json", False):
            out_json(workspaces)
            return 0
        out_header(f"Workspaces ({pid})")
        out_table(workspaces, ["name", "type", "description"])
        return 0

    if subcmd == "create":
        body = {"name": args.name, "type": getattr(args, "type", "custom") or "custom"}
        if args.repo:
            body["type"] = "git"
            body["repo"] = args.repo
        if args.branch:
            body["branch"] = args.branch
        ok, data = http_post(f"/api/projects/{pid}/workspaces", body)
        if not ok:
            out_err(data.get("error", "Failed"))
            return 1
        out_ok(f"Workspace '{args.name}' created")
        return 0

    out_err(f"Unknown: ws {subcmd}")
    return 1


# ═══════════════════════════════════════════════════════════════════
# Commands — Exec
# ═══════════════════════════════════════════════════════════════════

def cmd_exec(args):
    pid = _pid(args)

    ok, inst = http_get(f"/api/projects/{pid}/instances/{args.instance}")
    if not ok:
        out_err(inst.get("error", "Instance not found"))
        return 1

    ip = inst.get("ip")
    if not ip:
        out_err("Instance has no IP — not provisioned?")
        return 1

    command = " ".join(args.command)
    if not command:
        out_err("No command")
        return 1

    agent_url = f"http://{ip}:8081"
    agent_email = os.environ.get("NSO_ADMIN_EMAIL", "ayman_gha@hotmail.com")
    agent_pass = os.environ.get("AGENT_ADMIN_PASSWORD", "")
    if not agent_pass:
        agent_pass = getpass.getpass("Agent password: ")

    try:
        req = Request(
            f"{agent_url}/auth/login",
            data=json.dumps({"email": agent_email, "password": agent_pass}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            agent_token = json.loads(resp.read()).get("token", "")
    except Exception as e:
        out_err(f"Agent login failed: {e}")
        return 1

    try:
        req = Request(
            f"{agent_url}/exec/",
            data=json.dumps({"command": command}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {agent_token}",
            },
            method="POST",
        )
        with urlopen(req, timeout=args.timeout) as resp:
            result = json.loads(resp.read())

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        code = result.get("returncode", result.get("exit_code", -1))

        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        return code

    except Exception as e:
        out_err(f"Exec failed: {e}")
        return 1


# ═══════════════════════════════════════════════════════════════════
# Commands — Status / Doctor
# ═══════════════════════════════════════════════════════════════════

def cmd_status(args):
    out_header("NSO Status")

    ok, health = http_get("/api/health", timeout=5)
    if ok:
        out_ok(f"API: {get_host()}")
        caps = health.get("capabilities", {})
        if caps:
            out_dim(f"  v{caps.get('version', '?')}")
    else:
        out_err(f"API unreachable: {get_host()}")
        return 1

    token = get_token()
    if token:
        kind = "API key" if token.startswith("sk_live_") else "JWT"
        out_ok(f"Auth: {kind}")
    else:
        out_warn("Auth: not set — run: nso login")

    if token and not token.startswith("sk_live_"):
        ok, data = http_get("/api/projects")
        if ok:
            projects = data if isinstance(data, list) else data.get("projects", [])
            out_info(f"Projects: {len(projects)}")
    return 0


def cmd_doctor(args):
    out_header("NSO Doctor")
    issues = 0

    host = get_host()
    out_info(f"API: {host}")
    ok, _ = http_get("/api/health", timeout=5)
    if ok:
        out_ok("API reachable")
    else:
        out_err("API unreachable")
        out_dim("  nso config host https://your-server.com")
        issues += 1

    token = get_token()
    if token:
        out_ok("Token present")
        ok2, _ = http_get("/api/projects", timeout=5)
        if ok2:
            out_ok("Token valid")
        else:
            out_err("Token expired/invalid — nso login")
            issues += 1
    else:
        out_warn("No token — nso login")
        issues += 1

    val = os.environ.get("NSO_PROJECT")
    if val:
        out_ok(f"NSO_PROJECT = {val}")
    else:
        out_dim("  NSO_PROJECT not set (use -p instead)")

    print()
    if issues == 0:
        out_ok("All checks passed")
    else:
        out_warn(f"{issues} issue(s)")
    return issues


# ═══════════════════════════════════════════════════════════════════
# Argument parser
# ═══════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nso",
        description="NSO — AI agent infrastructure CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  nso login -e admin@example.com
  nso projects create my-saas
  nso inst create prod-1 --domain app.mysite.com
  nso ship backend inst_m3n4
  nso rollback backend inst_m3n4
  nso exec inst_m3n4 ssh user@external uptime
  nso update inst_m3n4 --target agent""",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("-p", "--project", help="Project ID (or NSO_PROJECT)")
    sub = parser.add_subparsers(dest="command")

    # Auth
    p = sub.add_parser("login", help="Authenticate")
    p.add_argument("-e", "--email", help="Email")
    p.add_argument("--password", help="Password")
    p.add_argument("--host", help="API URL")
    p.add_argument("-k", "--key", help="API key (sk_live_...)")

    sub.add_parser("logout", help="Clear credentials")

    p = sub.add_parser("config", help="Show/set config")
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")

    sub.add_parser("status", help="Quick overview")
    sub.add_parser("doctor", help="Diagnose problems")

    # Deploy
    p = sub.add_parser("ship", help="Pack + push + deploy")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("instance", help="Instance ID")
    p.add_argument("-v", "--version")
    p.add_argument("-b", "--branch")

    p = sub.add_parser("deploy", help="Deploy from R2 to instance")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("instance", help="Instance ID")
    p.add_argument("-v", "--version")
    p.add_argument("-b", "--branch")
    p.add_argument("--target-dir")

    p = sub.add_parser("rollback", help="Restore previous snapshot")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("instance", help="Instance ID")
    p.add_argument("-s", "--snapshot", help="Specific snapshot")

    p = sub.add_parser("pack", help="Pack workspace into .zar")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("-v", "--version")
    p.add_argument("-b", "--branch")

    p = sub.add_parser("push", help="Push .zar to R2")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("-v", "--version")
    p.add_argument("-b", "--branch")

    p = sub.add_parser("update", help="Self-update component on instance")
    p.add_argument("instance", help="Instance ID")
    p.add_argument("-t", "--target", default="agent", choices=["agent", "frontend", "core"])

    # Versioning
    p = sub.add_parser("versions", help="List versions and branches")
    p.add_argument("workspace", help="Workspace name")

    p = sub.add_parser("branch", help="Create branch in R2")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("name", help="New branch name")
    p.add_argument("--from", dest="source", default="main", help="Source branch")

    p = sub.add_parser("merge", help="Merge branches in R2")
    p.add_argument("workspace", help="Workspace name")
    p.add_argument("source", help="Source branch")
    p.add_argument("to", help="Target branch")

    # Resources
    proj = sub.add_parser("projects", help="Manage projects")
    proj_sub = proj.add_subparsers(dest="subcmd")
    proj_sub.add_parser("ls", help="List")
    p = proj_sub.add_parser("create", help="Create")
    p.add_argument("name")
    p = proj_sub.add_parser("rm", help="Delete")
    p.add_argument("id")
    p.add_argument("-f", "--force", action="store_true")

    inst = sub.add_parser("inst", help="Manage instances")
    inst_sub = inst.add_subparsers(dest="subcmd")
    inst_sub.add_parser("ls", help="List")
    p = inst_sub.add_parser("create", help="Create VPS")
    p.add_argument("label")
    p.add_argument("-r", "--region")
    p.add_argument("--plan")
    p.add_argument("-d", "--domain")
    p = inst_sub.add_parser("rm", help="Destroy")
    p.add_argument("id")
    p.add_argument("-f", "--force", action="store_true")
    p = inst_sub.add_parser("status", help="Details")
    p.add_argument("id")

    ws = sub.add_parser("ws", help="Manage workspaces")
    ws_sub = ws.add_subparsers(dest="subcmd")
    ws_sub.add_parser("ls", help="List")
    p = ws_sub.add_parser("create", help="Create")
    p.add_argument("name")
    p.add_argument("-t", "--type", default="custom")
    p.add_argument("--repo")
    p.add_argument("-b", "--branch")

    # Exec
    ex = sub.add_parser("exec", help="Run command on instance")
    ex.add_argument("instance")
    ex.add_argument("command", nargs=argparse.REMAINDER)
    ex.add_argument("--timeout", type=int, default=30)

    return parser


# ═══════════════════════════════════════════════════════════════════
# Dispatch
# ═══════════════════════════════════════════════════════════════════

COMMANDS = {
    "login": cmd_login,
    "logout": cmd_logout,
    "config": cmd_config,
    "status": cmd_status,
    "doctor": cmd_doctor,
    "ship": cmd_ship,
    "deploy": cmd_deploy,
    "rollback": cmd_rollback,
    "pack": cmd_pack,
    "push": cmd_push,
    "update": cmd_update,
    "versions": cmd_versions,
    "branch": cmd_branch,
    "merge": cmd_merge,
    "projects": cmd_projects,
    "inst": cmd_instances,
    "ws": cmd_workspaces,
    "exec": cmd_exec,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handler = COMMANDS.get(args.command)
    if handler:
        return handler(args)

    out_err(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
