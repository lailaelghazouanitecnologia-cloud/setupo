"""
Workspace tools — analysis, file ops, config generation.

Tools:
  - analyze_project: Scan workspace to detect stack/framework/entry points
  - generate_deploy_config: Generate deploy.toml from analysis
  - list_workspaces: List project workspaces
  - list_instances: List VPS instances
  - read_workspace_file: Read a file from workspace
  - write_workspace_file: Write/create a file in workspace
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from nso.shared import db

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext


def create_workspace_tools(ctx: DeployContext) -> list[tuple]:
    """Create workspace-related tools bound to project context."""

    async def analyze_project(workspace: str = "") -> str:
        """Analyze a workspace or entire project to detect stack, dependencies, and entry points."""
        if workspace:
            ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
            if not ws:
                return json.dumps({"error": f"Workspace '{workspace}' not found"})
            ws_path = ws.get("path", "")
            if not ws_path or not os.path.isdir(ws_path):
                return json.dumps({"error": f"Workspace path not found: {ws_path}"})
            return json.dumps(_analyze_directory(ws_path, workspace))
        else:
            workspaces = await db.fetch_all("workspaces", project_id=ctx.project_id)
            if not workspaces:
                return json.dumps({"workspaces": [], "hint": "No workspaces found. Create one first."})
            results = []
            for ws in workspaces:
                ws_path = ws.get("path", "")
                if ws_path and os.path.isdir(ws_path):
                    results.append(_analyze_directory(ws_path, ws.get("name", "")))
                else:
                    results.append({"name": ws.get("name", ""), "error": "path not found"})
            return json.dumps({"workspaces": results})

    async def generate_deploy_config(workspace: str, analysis: str = "") -> str:
        """Generate deploy.toml for a workspace based on analysis."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path:
            return json.dumps({"error": "Workspace has no path"})

        if not analysis:
            info = _analyze_directory(ws_path, workspace)
        else:
            try:
                info = json.loads(analysis)
            except Exception:
                info = _analyze_directory(ws_path, workspace)

        deploy_toml = _generate_deploy_toml(info)
        deploy_path = os.path.join(ws_path, "deploy.toml")
        Path(deploy_path).write_text(deploy_toml)

        return json.dumps({
            "ok": True,
            "path": deploy_path,
            "content": deploy_toml,
            "message": f"deploy.toml written to {deploy_path}",
        })

    async def list_workspaces() -> str:
        """List all workspaces in the project that are visible to the agent."""
        workspaces = await db.fetch_all("workspaces", project_id=ctx.project_id)
        result = []
        for ws in workspaces:
            # Skip workspaces hidden from agent
            if not ws.get("agent_visible", 1):
                continue
            result.append({
                "name": ws.get("name", ""),
                "path": ws.get("path", ""),
                "instance_id": ws.get("instance_id", ""),
                "created_at": ws.get("created_at", ""),
            })
        return json.dumps({"workspaces": result})

    async def list_instances() -> str:
        """List all VPS instances in the project."""
        instances = await db.fetch_all("instances", project_id=ctx.project_id)
        result = []
        for inst in instances:
            result.append({
                "id": inst.get("id", ""),
                "label": inst.get("label", ""),
                "ip": inst.get("ip", ""),
                "state": inst.get("state", ""),
                "region": inst.get("region", ""),
                "plan": inst.get("plan", ""),
                "workspace": inst.get("workspace", ""),
            })
        return json.dumps({"instances": result})

    async def read_workspace_file(workspace: str, file_path: str) -> str:
        """Read a file from a workspace directory."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        full = os.path.join(ws_path, file_path)

        if ".." in file_path or not os.path.abspath(full).startswith(os.path.abspath(ws_path)):
            return json.dumps({"error": "Path traversal not allowed"})
        if not os.path.isfile(full):
            return json.dumps({"error": f"File not found: {file_path}"})

        try:
            content = Path(full).read_text()
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            return json.dumps({"path": file_path, "content": content})
        except Exception as e:
            return json.dumps({"error": f"Cannot read file: {e}"})

    async def write_workspace_file(workspace: str, file_path: str, content: str) -> str:
        """Write a file to a workspace directory."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        full = os.path.join(ws_path, file_path)

        if ".." in file_path or not os.path.abspath(full).startswith(os.path.abspath(ws_path)):
            return json.dumps({"error": "Path traversal not allowed"})

        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)
            return json.dumps({"ok": True, "path": file_path, "size": len(content)})
        except Exception as e:
            return json.dumps({"error": f"Cannot write file: {e}"})

    return [
        (analyze_project, "analyze_project", "Analyze workspace to detect stack, files, dependencies, entry points"),
        (generate_deploy_config, "generate_deploy_config", "Generate deploy.toml from analysis"),
        (list_workspaces, "list_workspaces", "List all workspaces in the project"),
        (list_instances, "list_instances", "List all VPS instances in the project"),
        (read_workspace_file, "read_workspace_file", "Read a file from workspace"),
        (write_workspace_file, "write_workspace_file", "Write a file to workspace"),
    ]


# ── Helpers ──

def _analyze_directory(ws_path: str, name: str) -> dict:
    """Scan a workspace directory and return structured analysis."""
    info: dict = {"name": name, "path": ws_path, "files": [], "stack": "unknown", "entry_points": []}

    if not os.path.isdir(ws_path):
        info["error"] = "Directory not found"
        return info

    all_files = []
    for entry in sorted(os.listdir(ws_path))[:100]:
        full = os.path.join(ws_path, entry)
        if entry.startswith(".") or entry in ("node_modules", "__pycache__", "venv", ".venv", ".git"):
            continue
        is_dir = os.path.isdir(full)
        size = os.path.getsize(full) if not is_dir else 0
        all_files.append({"name": entry, "is_dir": is_dir, "size": size})
    info["files"] = all_files

    # Stack detection
    stack_indicators = [
        ("package.json", "node"),
        ("requirements.txt", "python"),
        ("pyproject.toml", "python"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("Dockerfile", "docker"),
        ("docker-compose.yml", "docker"),
        ("index.html", "static"),
        ("Gemfile", "ruby"),
    ]
    for filename, stack in stack_indicators:
        if os.path.exists(os.path.join(ws_path, filename)):
            info["stack"] = stack
            break

    # Framework detection for node
    pkg_path = os.path.join(ws_path, "package.json")
    if os.path.isfile(pkg_path):
        try:
            with open(pkg_path) as f:
                pkg = json.load(f)
            info["package_name"] = pkg.get("name", "")
            info["package_version"] = pkg.get("version", "")
            info["scripts"] = list(pkg.get("scripts", {}).keys())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                info["framework"] = "nextjs"
            elif "nuxt" in deps:
                info["framework"] = "nuxt"
            elif "vite" in deps:
                info["framework"] = "vite"
            elif "react" in deps:
                info["framework"] = "react"
            elif "vue" in deps:
                info["framework"] = "vue"
            elif "express" in deps:
                info["framework"] = "express"
            elif "fastify" in deps:
                info["framework"] = "fastify"
            info["has_build"] = "build" in pkg.get("scripts", {})
            info["has_start"] = "start" in pkg.get("scripts", {})
            info["has_dev"] = "dev" in pkg.get("scripts", {})
        except Exception:
            pass

    # Python analysis
    req_path = os.path.join(ws_path, "requirements.txt")
    if os.path.isfile(req_path):
        try:
            reqs = Path(req_path).read_text().strip().splitlines()
            info["python_deps"] = [r.strip() for r in reqs if r.strip() and not r.startswith("#")][:20]
            for dep in info["python_deps"]:
                dep_lower = dep.lower().split("==")[0].split(">=")[0]
                if dep_lower == "fastapi":
                    info["framework"] = "fastapi"
                elif dep_lower == "django":
                    info["framework"] = "django"
                elif dep_lower == "flask":
                    info["framework"] = "flask"
        except Exception:
            pass

    entry_candidates = [
        "main.py", "app.py", "server.py", "index.py", "manage.py",
        "server.js", "index.js", "app.js", "main.js",
        "server.ts", "index.ts", "app.ts", "main.ts",
        "main.go", "cmd/main.go",
    ]
    for ep in entry_candidates:
        if os.path.isfile(os.path.join(ws_path, ep)):
            info["entry_points"].append(ep)

    info["has_deploy_toml"] = os.path.isfile(os.path.join(ws_path, "deploy.toml"))
    info["has_config_toml"] = os.path.isfile(os.path.join(ws_path, "config.toml"))
    info["has_dockerfile"] = os.path.isfile(os.path.join(ws_path, "Dockerfile"))

    return info


def _generate_deploy_toml(info: dict) -> str:
    """Generate a deploy.toml based on project analysis."""
    stack = info.get("stack", "unknown")
    framework = info.get("framework", "")
    name = info.get("name", "app")

    lines = [
        f'# Deploy configuration for {name}',
        '# Auto-generated by NSO deploy agent',
        '',
        '[workspace]',
        f'name = "{name}"',
        '',
    ]

    # Install section
    if stack == "node":
        lines += ['[install]', 'command = "npm install"', 'timeout = 300', '']
    elif stack == "python":
        lines += ['[install]', 'command = "pip install -r requirements.txt"', 'timeout = 300', '']
    elif stack == "go":
        lines += ['[install]', 'command = "go mod download"', 'timeout = 120', '']
    elif stack == "rust":
        lines += ['[install]', 'command = "cargo fetch"', 'timeout = 120', '']

    # Build section
    if info.get("has_build"):
        if framework == "nextjs":
            lines += ['[build]', 'command = "npm run build"', 'timeout = 600', '', '[build.env]', 'NODE_ENV = "production"', '']
        elif framework == "vite":
            lines += ['[build]', 'command = "npm run build"', 'timeout = 300', '', '[build.env]', 'NODE_ENV = "production"', '']
        elif framework in ("react", "vue", "nuxt"):
            lines += ['[build]', 'command = "npm run build"', 'timeout = 600', '']
    elif stack == "go":
        lines += ['[build]', 'command = "go build -o app ./..."', 'timeout = 300', '']
    elif stack == "rust":
        lines += ['[build]', 'command = "cargo build --release"', 'timeout = 600', '']

    # Services section
    if framework in ("express", "fastify") or (stack == "node" and info.get("has_start")):
        lines += ['[services.app]', 'command = "npm start"', 'port = 3000', 'user = "root"', '']
    elif framework == "nextjs":
        lines += ['[services.app]', 'command = "npm start"', 'port = 3000', 'user = "root"', '']
    elif framework == "fastapi":
        entry = info.get("entry_points", ["main.py"])[0].replace(".py", "")
        lines += ['[services.app]', f'command = "uvicorn {entry}:app --host 0.0.0.0 --port 8000"', 'port = 8000', 'user = "root"', '']
    elif framework == "django":
        lines += ['[services.app]', 'command = "gunicorn --bind 0.0.0.0:8000 --workers 2 app.wsgi"', 'port = 8000', 'user = "root"', '']
    elif framework == "flask":
        entry = info.get("entry_points", ["app.py"])[0].replace(".py", "")
        lines += ['[services.app]', f'command = "gunicorn --bind 0.0.0.0:8000 {entry}:app"', 'port = 8000', 'user = "root"', '']
    elif stack == "go":
        lines += ['[services.app]', 'command = "./app"', 'port = 8080', 'user = "root"', '']
    elif stack == "static":
        lines += ['# Static site — served directly by nginx', '']

    # Health check
    if stack != "static":
        port = "3000" if stack == "node" else "8000"
        lines += ['[health]', 'strategy = "http"', f'url = "http://localhost:{port}/"', 'timeout = 30', 'retries = 5', '']

    return "\n".join(lines) + "\n"


def _detect_build_cmd(ws_path: str) -> str:
    """Auto-detect build command."""
    checks = [
        ("package.json", "npm run build"),
        ("Makefile", "make build"),
        ("Cargo.toml", "cargo build --release"),
        ("go.mod", "go build -o app ./..."),
    ]
    for filename, cmd in checks:
        fpath = os.path.join(ws_path, filename)
        if not os.path.exists(fpath):
            continue
        if filename == "package.json":
            try:
                with open(fpath) as f:
                    pkg = json.load(f)
                if "build" not in pkg.get("scripts", {}):
                    continue
            except Exception:
                continue
        return cmd
    return ""
