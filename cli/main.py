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

from cli import client
from cli import output


# ── Helpers ──────────────────────────────────────────────────────

def _pid(args) -> str:
    """Get project_id from args or env."""
    pid = getattr(args, "project", None) or os.environ.get("NSO_PROJECT")
    if not pid:
        output.err("No project. Use -p <id> or set NSO_PROJECT")
        sys.exit(1)
    return pid


def _zar_path(pid: str, name: str, endpoint: str) -> str:
    return f"/api/projects/{pid}/zar/{name}/{endpoint}"


# ── Auth ─────────────────────────────────────────────────────────

def cmd_login(args):
    """Login to the API."""
    if args.key:
        if not args.key.startswith("sk_live_"):
            output.warn("API keys should start with 'sk_live_'")
        client.save_token(args.key)
        output.ok(f"API key saved ({args.key[:12]}...)")
        return 0

    host = args.host or client.get_host()
    if args.host:
        client.set_host(args.host)

    email = args.email or input("Email: ")
    password = args.password or getpass.getpass("Password: ")

    output.info(f"Logging in to {host}...")
    ok, data = client.post("/api/auth/login", {"email": email, "password": password})
    if not ok:
        output.err(data.get("error", "Login failed"))
        return 1

    token = data.get("token", "")
    if not token:
        output.err("No token in response")
        return 1

    client.save_token(token)
    output.ok(f"Logged in as {email}")
    return 0


def cmd_logout(args):
    client.clear_token()
    output.ok("Logged out")
    return 0


def cmd_config(args):
    if args.key and args.value:
        if args.key == "host":
            client.set_host(args.value)
            output.ok(f"Host → {args.value}")
        else:
            output.err(f"Unknown key: {args.key}")
            return 1
        return 0
    output.header("Config")
    output.kv({
        "host": client.get_host(),
        "token": "set" if client.get_token() else "not set",
        "config": str(client.CONFIG_DIR),
    })
    return 0


# ── Ship / Deploy / Rollback ────────────────────────────────────

def cmd_ship(args):
    """Pack + push + deploy in one shot."""
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    output.info(f"Shipping '{args.workspace}' → {args.instance}")
    output.dim("  pack → push R2 → snapshot → extract → restart")

    start = time.time()
    ok, data = client.post(
        _zar_path(pid, args.workspace, "ship"),
        body,
        timeout=client.DEPLOY_TIMEOUT,
    )
    elapsed = time.time() - start

    if not ok:
        error = data.get("error", "Ship failed")
        if "rollback" in str(data).lower():
            output.err("Ship failed — auto-rollback executed")
            output.warn(f"  {error}")
        else:
            output.err(error)
        return 1

    output.ok(f"Shipped in {elapsed:.1f}s")
    output.kv({
        "Version": data.get("version", "?"),
        "Hash": data.get("hash", "?")[:20] + "...",
        "R2": data.get("r2_key", "?"),
    })
    return 0


def cmd_deploy(args):
    """Deploy .zar from R2 to instance."""
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch
    if args.target_dir:
        body["target_dir"] = args.target_dir

    output.info(f"Deploying '{args.workspace}' → {args.instance}")
    output.dim("  snapshot → download → extract → install → restart")

    ok, data = client.post(
        _zar_path(pid, args.workspace, "deploy"),
        body,
        timeout=client.DEPLOY_TIMEOUT,
        retries=0,
    )

    if not ok:
        error = data.get("error", "Deploy failed")
        if "rollback" in str(data).lower():
            output.err("Deploy failed — auto-rollback executed")
            output.warn(f"  {error}")
            output.info(f"  Restored: {data.get('restored_from', 'latest snapshot')}")
        else:
            output.err(error)
        return 1

    output.ok(f"Deployed v{data.get('version', '?')}")
    return 0


def cmd_rollback(args):
    """Rollback to previous snapshot."""
    pid = _pid(args)
    body = {"instance_id": args.instance}
    if args.snapshot:
        body["snapshot"] = args.snapshot

    output.info(f"Rolling back '{args.workspace}' on {args.instance}...")
    ok, data = client.post(
        _zar_path(pid, args.workspace, "rollback"),
        body,
        timeout=client.DEPLOY_TIMEOUT,
    )
    if not ok:
        output.err(data.get("error", "Rollback failed"))
        return 1

    output.ok(f"Restored: {data.get('restored_from', 'previous snapshot')}")
    return 0


def cmd_pack(args):
    """Pack workspace into .zar."""
    pid = _pid(args)
    body = {}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    output.info(f"Packing '{args.workspace}'...")
    ok, data = client.post(_zar_path(pid, args.workspace, "pack"), body)
    if not ok:
        output.err(data.get("error", "Pack failed"))
        return 1

    output.ok(f"Packed v{data.get('version', '?')} ({data.get('size', 0)} bytes)")
    return 0


def cmd_push(args):
    """Push .zar to R2."""
    pid = _pid(args)
    body = {}
    if args.version:
        body["version"] = args.version
    if args.branch:
        body["branch"] = args.branch

    output.info(f"Pushing '{args.workspace}' to R2...")
    ok, data = client.post(_zar_path(pid, args.workspace, "push"), body, timeout=60)
    if not ok:
        output.err(data.get("error", "Push failed"))
        return 1

    output.ok(f"Pushed: {data.get('r2_key', '?')}")
    return 0


def cmd_update(args):
    """Self-update agent/frontend/core on instance."""
    pid = _pid(args)
    body = {"instance_id": args.instance, "target": args.target}

    output.info(f"Updating '{args.target}' on {args.instance}...")
    output.dim(f"  Brief restart of {args.target}")

    ok, data = client.post(
        f"/api/projects/{pid}/zar/self-update",
        body,
        timeout=client.DEPLOY_TIMEOUT,
    )
    if not ok:
        error = data.get("error", "Update failed")
        if "rollback" in str(data).lower():
            output.err(f"Update failed — rolled back")
        else:
            output.err(error)
        return 1

    output.ok(f"Updated '{args.target}'")
    return 0


# ── Versioning ───────────────────────────────────────────────────

def cmd_versions(args):
    """List versions and branches."""
    pid = _pid(args)
    ok, data = client.get(_zar_path(pid, args.workspace, "versions"))
    if not ok:
        output.err(data.get("error", "Failed"))
        return 1

    if getattr(args, "json", False):
        output.as_json(data)
        return 0

    output.header(f"Versions: {args.workspace}")
    branches = data.get("branches", {})
    versions = data.get("versions", [])

    if branches:
        output.info("Branches:")
        for name, ver in branches.items():
            print(f"    {output.CYAN}{name}{output.RESET} → {ver}")
    if versions:
        output.info("History:")
        for v in versions:
            print(f"    {v}")
    return 0


def cmd_branch(args):
    """Create branch in R2."""
    pid = _pid(args)
    body = {"to": args.name}
    if args.source:
        body["from"] = args.source

    output.info(f"Branching '{args.workspace}' → '{args.name}'")
    ok, data = client.post(_zar_path(pid, args.workspace, "branch"), body)
    if not ok:
        output.err(data.get("error", "Branch failed"))
        return 1

    output.ok(f"Branch '{args.name}' created")
    return 0


def cmd_merge(args):
    """Merge branches in R2."""
    pid = _pid(args)
    body = {"from": args.source, "to": args.to}

    output.info(f"Merging '{args.workspace}': {args.source} → {args.to}")
    ok, data = client.post(_zar_path(pid, args.workspace, "merge"), body)
    if not ok:
        output.err(data.get("error", "Merge failed"))
        return 1

    output.ok(f"Merged {args.source} → {args.to}")
    return 0


# ── Resources ────────────────────────────────────────────────────

def cmd_projects(args):
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = client.get("/api/projects")
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        projects = data if isinstance(data, list) else data.get("projects", [])
        if getattr(args, "json", False):
            output.as_json(projects)
            return 0
        output.header("Projects")
        if not projects:
            output.dim("  No projects. Create one: nso projects create <name>")
            return 0
        output.table(projects, ["id", "name", "status", "created_at"])
        return 0

    if subcmd == "create":
        output.info(f"Creating '{args.name}'...")
        ok, data = client.post("/api/projects", {"name": args.name})
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        output.ok(f"Project: {data.get('id', '?')}")
        api_key = data.get("api_key", "")
        if api_key:
            output.info(f"API key: {api_key}")
            output.warn("Save this — won't be shown again")
        return 0

    if subcmd in ("rm", "delete"):
        if not getattr(args, "force", False):
            confirm = input(f"Delete '{args.id}'? All instances destroyed. [y/N] ")
            if confirm.lower() != "y":
                return 0
        ok, data = client.delete(f"/api/projects/{args.id}")
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        output.ok(f"Deleted {args.id}")
        return 0

    output.err(f"Unknown: projects {subcmd}")
    return 1


def cmd_instances(args):
    pid = _pid(args)
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = client.get(f"/api/projects/{pid}/instances")
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        instances = data if isinstance(data, list) else data.get("instances", [])
        if getattr(args, "json", False):
            output.as_json(instances)
            return 0
        output.header(f"Instances ({pid})")
        output.table(instances, ["id", "label", "ip", "status", "region", "plan"])
        return 0

    if subcmd == "create":
        body = {"label": args.label}
        if args.region:
            body["region"] = args.region
        if args.plan:
            body["plan"] = args.plan
        if args.domain:
            body["domain"] = args.domain

        output.info(f"Creating '{args.label}'...")
        output.dim("  1-3 min (VPS + cloud-init)")
        ok, data = client.post(f"/api/projects/{pid}/instances", body, timeout=120)
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        output.ok(f"Instance: {data.get('id', '?')}")
        output.kv({"IP": data.get("ip", "pending"), "Status": data.get("status", "?")})
        return 0

    if subcmd in ("rm", "delete"):
        if not getattr(args, "force", False):
            confirm = input(f"Destroy '{args.id}'? Irreversible. [y/N] ")
            if confirm.lower() != "y":
                return 0
        ok, data = client.delete(f"/api/projects/{pid}/instances/{args.id}")
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        output.ok(f"Destroyed {args.id}")
        return 0

    if subcmd == "status":
        ok, data = client.get(f"/api/projects/{pid}/instances/{args.id}")
        if not ok:
            output.err(data.get("error", "Not found"))
            return 1
        if getattr(args, "json", False):
            output.as_json(data)
            return 0
        output.header(f"Instance: {data.get('label', args.id)}")
        output.kv(data)
        return 0

    output.err(f"Unknown: inst {subcmd}")
    return 1


def cmd_workspaces(args):
    pid = _pid(args)
    subcmd = args.subcmd or "ls"

    if subcmd in ("ls", "list"):
        ok, data = client.get(f"/api/projects/{pid}/workspaces")
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        workspaces = data if isinstance(data, list) else data.get("workspaces", [])
        if getattr(args, "json", False):
            output.as_json(workspaces)
            return 0
        output.header(f"Workspaces ({pid})")
        output.table(workspaces, ["name", "type", "description"])
        return 0

    if subcmd == "create":
        body = {"name": args.name, "type": getattr(args, "type", "custom") or "custom"}
        if args.repo:
            body["type"] = "git"
            body["repo"] = args.repo
        if args.branch:
            body["branch"] = args.branch
        ok, data = client.post(f"/api/projects/{pid}/workspaces", body)
        if not ok:
            output.err(data.get("error", "Failed"))
            return 1
        output.ok(f"Workspace '{args.name}' created")
        return 0

    output.err(f"Unknown: ws {subcmd}")
    return 1


# ── Exec ─────────────────────────────────────────────────────────

def cmd_exec(args):
    """Execute command on instance via agent."""
    pid = _pid(args)

    ok, inst = client.get(f"/api/projects/{pid}/instances/{args.instance}")
    if not ok:
        output.err(inst.get("error", "Instance not found"))
        return 1

    ip = inst.get("ip")
    if not ip:
        output.err("Instance has no IP — not provisioned?")
        return 1

    command = " ".join(args.command)
    if not command:
        output.err("No command")
        return 1

    agent_url = f"http://{ip}:8081"
    agent_email = os.environ.get("NSO_ADMIN_EMAIL", "ayman_gha@hotmail.com")
    agent_pass = os.environ.get("AGENT_ADMIN_PASSWORD", "")
    if not agent_pass:
        agent_pass = getpass.getpass("Agent password: ")

    # Login to agent
    try:
        from urllib.request import Request, urlopen
        req = Request(
            f"{agent_url}/auth/login",
            data=json.dumps({"email": agent_email, "password": agent_pass}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            agent_token = json.loads(resp.read()).get("token", "")
    except Exception as e:
        output.err(f"Agent login failed: {e}")
        return 1

    # Execute
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
        output.err(f"Exec failed: {e}")
        return 1


# ── Status / Doctor ──────────────────────────────────────────────

def cmd_status(args):
    output.header("NSO Status")

    ok, health = client.get("/api/health", timeout=5)
    if ok:
        output.ok(f"API: {client.get_host()}")
        caps = health.get("capabilities", {})
        if caps:
            output.dim(f"  v{caps.get('version', '?')}")
    else:
        output.err(f"API unreachable: {client.get_host()}")
        return 1

    token = client.get_token()
    if token:
        kind = "API key" if token.startswith("sk_live_") else "JWT"
        output.ok(f"Auth: {kind}")
    else:
        output.warn("Auth: not set — run: nso login")

    if token and not token.startswith("sk_live_"):
        ok, data = client.get("/api/projects")
        if ok:
            projects = data if isinstance(data, list) else data.get("projects", [])
            output.info(f"Projects: {len(projects)}")
    return 0


def cmd_doctor(args):
    output.header("NSO Doctor")
    issues = 0

    host = client.get_host()
    output.info(f"API: {host}")
    ok, _ = client.get("/api/health", timeout=5)
    if ok:
        output.ok("API reachable")
    else:
        output.err("API unreachable")
        output.dim("  nso config host https://your-server.com")
        issues += 1

    token = client.get_token()
    if token:
        output.ok("Token present")
        ok2, _ = client.get("/api/projects", timeout=5)
        if ok2:
            output.ok("Token valid")
        else:
            output.err("Token expired/invalid — nso login")
            issues += 1
    else:
        output.warn("No token — nso login")
        issues += 1

    val = os.environ.get("NSO_PROJECT")
    if val:
        output.ok(f"NSO_PROJECT = {val}")
    else:
        output.dim("  NSO_PROJECT not set (use -p instead)")

    print()
    if issues == 0:
        output.ok("All checks passed")
    else:
        output.warn(f"{issues} issue(s)")
    return issues


# ── Parser ───────────────────────────────────────────────────────

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

    # ── Auth ──
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

    # ── Deploy commands (top-level) ──
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

    # ── Versioning ──
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

    # ── Resources ──
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

    # ── Exec ──
    ex = sub.add_parser("exec", help="Run command on instance")
    ex.add_argument("instance")
    ex.add_argument("command", nargs=argparse.REMAINDER)
    ex.add_argument("--timeout", type=int, default=30)

    return parser


# ── Dispatch ─────────────────────────────────────────────────────

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

    output.err(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
