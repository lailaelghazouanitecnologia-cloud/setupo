#!/usr/bin/env python3
"""Setupo CLI - Command-line client for the Setupo Orchestrator.

Usage:
    setupo health
    setupo vm list
    setupo vm create <name> [--vcpus N] [--memory N] [--disk N]
    setupo vm stop <id>
    setupo vm destroy <id>
    setupo microvm list
    setupo microvm create <name> [--vcpus N] [--memory N] [--disk N]
    setupo microvm stop <id>
    setupo microvm destroy <id>
    setupo capsule list
    setupo capsule load <name> --target <instance_id>
    setupo exec <instance_id> <command>
    setupo ssh <host> <command>
    setupo run <file.setupo>
    setupo token
"""
import argparse
import json
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DEFAULT_HOST = os.environ.get("SETUPO_HOST", "https://zarnetti.com")
TOKEN_FILE = os.path.expanduser("~/.setupo/token")


def get_token() -> str:
    token = os.environ.get("SETUPO_TOKEN", "")
    if not token and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
    if not token:
        print("Error: No token found. Set SETUPO_TOKEN or run: setupo token <your-token>")
        sys.exit(1)
    return token


def api(method: str, path: str, body: dict = None) -> dict:
    host = os.environ.get("SETUPO_HOST", DEFAULT_HOST)
    url = f"{host}/api{path}"
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {get_token()}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            print(f"Error {e.code}: {err.get('message', err.get('error', body))}")
        except json.JSONDecodeError:
            print(f"Error {e.code}: {body}")
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}")
        sys.exit(1)


def pp(data):
    """Pretty-print JSON data."""
    print(json.dumps(data, indent=2))


# ── Commands ─────────────────────────────────────────────────────

def cmd_health(args):
    pp(api("GET", "/health"))


def cmd_vm_list(args):
    pp(api("GET", "/vms/"))


def cmd_vm_create(args):
    pp(api("POST", "/vms/", {
        "name": args.name,
        "vcpus": args.vcpus,
        "memory_mb": args.memory,
        "disk_mb": args.disk,
    }))


def cmd_vm_stop(args):
    pp(api("POST", f"/vms/{args.id}/stop"))


def cmd_vm_destroy(args):
    pp(api("DELETE", f"/vms/{args.id}"))


def cmd_microvm_list(args):
    pp(api("GET", "/microvms/"))


def cmd_microvm_create(args):
    pp(api("POST", "/microvms/", {
        "name": args.name,
        "vcpus": args.vcpus,
        "memory_mb": args.memory,
        "disk_mb": args.disk,
    }))


def cmd_microvm_stop(args):
    pp(api("POST", f"/microvms/{args.id}/stop"))


def cmd_microvm_destroy(args):
    pp(api("DELETE", f"/microvms/{args.id}"))


def cmd_capsule_list(args):
    pp(api("GET", "/capsules/"))


def cmd_capsule_load(args):
    pp(api("POST", "/capsules/load", {
        "capsule_name": args.name,
        "target_instance": args.target,
    }))


def cmd_exec(args):
    pp(api("POST", "/commands/exec", {
        "instance_id": args.instance_id,
        "command": args.command,
    }))


def cmd_ssh(args):
    pp(api("POST", "/commands/ssh", {
        "host": args.host,
        "command": args.command,
    }))


def cmd_run(args):
    """Execute a .setupo protocol file."""
    with open(args.file) as f:
        code = f.read()
    pp(api("POST", "/commands/protocol", {"code": code}))


def cmd_token(args):
    """Save token to local config."""
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(args.token)
    os.chmod(TOKEN_FILE, 0o600)
    print(f"Token saved to {TOKEN_FILE}")


def main():
    parser = argparse.ArgumentParser(prog="setupo", description="Setupo Orchestrator CLI")
    parser.add_argument("--host", help="Orchestrator URL", default=DEFAULT_HOST)
    sub = parser.add_subparsers(dest="command")

    # health
    sub.add_parser("health", help="Check orchestrator health")

    # token
    p = sub.add_parser("token", help="Save API token")
    p.add_argument("token", help="The API token")

    # vm
    vm = sub.add_parser("vm", help="Manage VMs")
    vm_sub = vm.add_subparsers(dest="vm_command")
    vm_sub.add_parser("list")
    p = vm_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--vcpus", type=int, default=2)
    p.add_argument("--memory", type=int, default=1024)
    p.add_argument("--disk", type=int, default=4096)
    p = vm_sub.add_parser("stop")
    p.add_argument("id")
    p = vm_sub.add_parser("destroy")
    p.add_argument("id")

    # microvm
    mvm = sub.add_parser("microvm", help="Manage MicroVMs")
    mvm_sub = mvm.add_subparsers(dest="mvm_command")
    mvm_sub.add_parser("list")
    p = mvm_sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--vcpus", type=int, default=1)
    p.add_argument("--memory", type=int, default=256)
    p.add_argument("--disk", type=int, default=512)
    p = mvm_sub.add_parser("stop")
    p.add_argument("id")
    p = mvm_sub.add_parser("destroy")
    p.add_argument("id")

    # capsule
    cap = sub.add_parser("capsule", help="Manage capsules")
    cap_sub = cap.add_subparsers(dest="cap_command")
    cap_sub.add_parser("list")
    p = cap_sub.add_parser("load")
    p.add_argument("name")
    p.add_argument("--target", required=True)

    # exec
    p = sub.add_parser("exec", help="Execute command on instance")
    p.add_argument("instance_id")
    p.add_argument("command")

    # ssh
    p = sub.add_parser("ssh", help="Execute via SSH on external host")
    p.add_argument("host")
    p.add_argument("command")

    # run
    p = sub.add_parser("run", help="Execute a .setupo protocol file")
    p.add_argument("file")

    args = parser.parse_args()

    if args.host:
        os.environ["SETUPO_HOST"] = args.host

    handlers = {
        "health": cmd_health,
        "token": cmd_token,
        "exec": cmd_exec,
        "ssh": cmd_ssh,
        "run": cmd_run,
    }

    if args.command in handlers:
        handlers[args.command](args)
    elif args.command == "vm":
        {"list": cmd_vm_list, "create": cmd_vm_create,
         "stop": cmd_vm_stop, "destroy": cmd_vm_destroy}.get(
            args.vm_command, lambda a: vm.print_help())(args)
    elif args.command == "microvm":
        {"list": cmd_microvm_list, "create": cmd_microvm_create,
         "stop": cmd_microvm_stop, "destroy": cmd_microvm_destroy}.get(
            args.mvm_command, lambda a: mvm.print_help())(args)
    elif args.command == "capsule":
        {"list": cmd_capsule_list, "load": cmd_capsule_load}.get(
            args.cap_command, lambda a: cap.print_help())(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
