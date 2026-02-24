#!/usr/bin/env python3
"""MMS CLI - Micro Module System command-line client.

Usage:
    mms health
    mms capsule list
    mms capsule create <name> [--runtime python] [--code <file>]
    mms capsule start <id>
    mms capsule stop <id>
    mms capsule destroy <id>
    mms capsule logs <id>
    mms capsule exec <id> <command>
    mms env list
    mms env create <name> [--runtime python] [--packages pkg1,pkg2]
    mms pipeline run <file.json>
    mms run <file.mms>
    mms token <token>
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint

console = Console()

DEFAULT_HOST = os.environ.get("MMS_HOST", "https://zarnetti.com")
TOKEN_FILE = Path.home() / ".mms" / "token"


def get_token() -> str:
    token = os.environ.get("MMS_TOKEN", "")
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
    if not token:
        console.print("[red]No token. Set MMS_TOKEN or run: mms token <your-token>[/]")
        sys.exit(1)
    return token


def client() -> httpx.Client:
    return httpx.Client(
        base_url=os.environ.get("MMS_HOST", DEFAULT_HOST) + "/api",
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=30,
    )


def api(method: str, path: str, body=None) -> dict:
    with client() as c:
        r = c.request(method, path, json=body)
        if r.status_code == 401:
            console.print("[red]Unauthorized. Check your token.[/]")
            sys.exit(1)
        if r.status_code >= 400:
            console.print(f"[red]Error {r.status_code}: {r.text}[/]")
            sys.exit(1)
        return r.json()


# ── Commands ─────────────────────────────────────────────────────

def cmd_health(_):
    d = api("GET", "/health")
    table = Table(title="MMS Health")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    for k, v in d.items():
        table.add_row(k, str(v))
    console.print(table)


def cmd_capsule_list(_):
    d = api("GET", "/capsules/")
    table = Table(title="Capsules")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Runtime")
    table.add_column("Isolation")
    table.add_column("State")
    for c in d.get("capsules", []):
        m = c.get("manifest", {})
        state_color = {"running": "green", "stopped": "red", "error": "red", "ready": "blue"}.get(c["state"], "yellow")
        table.add_row(c["id"], c["name"], m.get("runtime", "?"), m.get("isolation", "?"),
                      f"[{state_color}]{c['state']}[/]")
    console.print(table)


def cmd_capsule_create(args):
    code = None
    if args.code:
        code = Path(args.code).read_text()

    deps = [d.strip() for d in (args.deps or "").split(",") if d.strip()]

    d = api("POST", "/capsules/", {
        "name": args.name,
        "runtime": args.runtime,
        "isolation": args.isolation,
        "entrypoint": args.entrypoint,
        "code": code,
        "dependencies": deps,
    })
    cap = d["capsule"]
    console.print(Panel(f"[green]Created:[/] {cap['id']} ({cap['manifest']['name']})", title="Capsule"))


def cmd_capsule_start(args):
    d = api("POST", f"/capsules/{args.id}/start")
    console.print(f"[green]Started:[/] {d['capsule']['name']} ({d['capsule']['state']})")


def cmd_capsule_stop(args):
    d = api("POST", f"/capsules/{args.id}/stop")
    console.print(f"[yellow]Stopped:[/] {d['capsule']['name']}")


def cmd_capsule_destroy(args):
    d = api("DELETE", f"/capsules/{args.id}")
    console.print(f"[red]Destroyed:[/] {d['id']}")


def cmd_capsule_logs(args):
    d = api("GET", f"/capsules/{args.id}/logs")
    for log in d.get("logs", []):
        level = log.get("level", "info")
        color = {"error": "red", "warning": "yellow", "info": "white"}.get(level, "white")
        console.print(f"[dim]{log.get('created_at', '')}[/] [{color}]{log.get('message', '')}[/]")


def cmd_capsule_exec(args):
    d = api("POST", "/commands/exec", {"capsule_id": args.id, "command": args.command})
    r = d.get("result", {})
    if r.get("stdout"):
        console.print(r["stdout"], end="")
    if r.get("stderr"):
        console.print(f"[red]{r['stderr']}[/]", end="")
    if r.get("error"):
        console.print(f"[red]{r['error']}[/]")


def cmd_env_list(_):
    d = api("GET", "/envs/")
    table = Table(title="Environments")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Runtime")
    for e in d.get("environments", []):
        table.add_row(e.get("id", "?"), e.get("name", "?"), e.get("runtime", "?"))
    console.print(table)


def cmd_env_create(args):
    pkgs = [p.strip() for p in (args.packages or "").split(",") if p.strip()]
    d = api("POST", "/envs/", {"name": args.name, "runtime": args.runtime, "packages": pkgs})
    console.print(f"[green]Created env:[/] {d['environment']['name']}")


def cmd_pipeline_run(args):
    steps = json.loads(Path(args.file).read_text())
    d = api("POST", "/pipelines/", {"name": Path(args.file).stem, "steps": steps})
    console.print(Panel(json.dumps(d, indent=2), title="Pipeline Result"))


def cmd_run(args):
    """Execute a .mms protocol file."""
    code = Path(args.file).read_text()
    d = api("POST", "/commands/protocol", {"code": code})
    for i, result in enumerate(d.get("results", [])):
        console.print(Panel(json.dumps(result, indent=2, default=str), title=f"Step {i+1}"))


def cmd_token(args):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(args.token)
    TOKEN_FILE.chmod(0o600)
    console.print(f"[green]Token saved to {TOKEN_FILE}[/]")


# ── Argument Parser ──────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(prog="mms", description="MMS - Micro Module System")
    p.add_argument("--host", help="API host URL")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("health")

    tk = sub.add_parser("token")
    tk.add_argument("token")

    # capsule
    cap = sub.add_parser("capsule")
    csub = cap.add_subparsers(dest="capsule_cmd")
    csub.add_parser("list")
    cc = csub.add_parser("create")
    cc.add_argument("name")
    cc.add_argument("--runtime", default="python")
    cc.add_argument("--isolation", default="container")
    cc.add_argument("--entrypoint", default="main.py")
    cc.add_argument("--code", help="Path to code file")
    cc.add_argument("--deps", help="Comma-separated dependencies")
    cs = csub.add_parser("start"); cs.add_argument("id")
    ct = csub.add_parser("stop"); ct.add_argument("id")
    cd = csub.add_parser("destroy"); cd.add_argument("id")
    cl = csub.add_parser("logs"); cl.add_argument("id")
    ce = csub.add_parser("exec"); ce.add_argument("id"); ce.add_argument("command")

    # env
    env = sub.add_parser("env")
    esub = env.add_subparsers(dest="env_cmd")
    esub.add_parser("list")
    ec = esub.add_parser("create")
    ec.add_argument("name")
    ec.add_argument("--runtime", default="python")
    ec.add_argument("--packages", default="")

    # pipeline
    pip = sub.add_parser("pipeline")
    psub = pip.add_subparsers(dest="pipe_cmd")
    pr = psub.add_parser("run"); pr.add_argument("file")

    # run
    run = sub.add_parser("run")
    run.add_argument("file")

    args = p.parse_args()
    if args.host:
        os.environ["MMS_HOST"] = args.host

    dispatch = {
        "health": cmd_health,
        "token": cmd_token,
        "run": cmd_run,
    }

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    elif args.cmd == "capsule":
        {"list": cmd_capsule_list, "create": cmd_capsule_create, "start": cmd_capsule_start,
         "stop": cmd_capsule_stop, "destroy": cmd_capsule_destroy, "logs": cmd_capsule_logs,
         "exec": cmd_capsule_exec}.get(args.capsule_cmd, lambda a: cap.print_help())(args)
    elif args.cmd == "env":
        {"list": cmd_env_list, "create": cmd_env_create}.get(
            args.env_cmd, lambda a: env.print_help())(args)
    elif args.cmd == "pipeline":
        {"run": cmd_pipeline_run}.get(args.pipe_cmd, lambda a: pip.print_help())(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
