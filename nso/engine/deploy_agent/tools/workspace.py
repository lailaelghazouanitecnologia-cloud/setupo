"""
Workspace tools — analysis, file ops, config generation, creation.

Tools:
  - analyze_project: Scan workspace to detect stack/framework/entry points
  - generate_deploy_config: Generate deploy.toml from analysis
  - list_workspaces: List project workspaces
  - list_instances: List VPS instances
  - read_workspace_file: Read a file from workspace
  - write_workspace_file: Write/create a file in workspace
  - create_workspace: Create a new workspace
  - delete_workspace_file: Delete a file from workspace
"""

from __future__ import annotations

import json
import os
import re
import secrets as token_gen
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from nso.shared import db
from nso.config import settings

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext

# Files that cannot be overwritten in protected workspaces
PROTECTED_FILE_PATTERNS = [
    "config.toml",
    ".zar-manifest.json",
    "deploy.toml",
]


def _is_protected_file(file_path: str, ws_data: dict) -> bool:
    """Check if a file is protected from writes."""
    if not ws_data.get("readonly"):
        return False
    protected = ws_data.get("protected_files", "")
    if isinstance(protected, str):
        try:
            protected = json.loads(protected) if protected else []
        except Exception:
            protected = []
    # Always protect certain files in readonly workspaces
    all_protected = set(PROTECTED_FILE_PATTERNS)
    if isinstance(protected, list):
        all_protected.update(protected)
    return file_path in all_protected or os.path.basename(file_path) in all_protected


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
                "stack": ws.get("stack", ""),
                "path": ws.get("path", ""),
                "instance_id": ws.get("instance_id", ""),
                "readonly": bool(ws.get("readonly", 0)),
                "description": ws.get("description", ""),
                "created_at": ws.get("created_at", ""),
            })
        return json.dumps({"workspaces": result, "count": len(result)})

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

    # Sensitive file patterns that should never be read/exposed
    SENSITIVE_FILES = {".env", ".env.local", ".env.production", ".env.staging",
                       "credentials.json", "service-account.json", ".npmrc", ".pypirc"}

    def _safe_workspace_path(ws_path: str, file_path: str) -> tuple[str, str | None]:
        """Validate and resolve a file path within a workspace.
        Returns (resolved_path, error_message). error_message is None if valid."""
        if ".." in file_path:
            return "", "Path traversal not allowed"

        full = os.path.join(ws_path, file_path)
        abs_ws = os.path.abspath(ws_path)

        # Check before resolving (basic path traversal)
        if not os.path.abspath(full).startswith(abs_ws):
            return "", "Path traversal not allowed"

        # Check the real path after resolving symlinks
        real_full = os.path.realpath(full)
        if not real_full.startswith(abs_ws):
            return "", "Symlink escape not allowed — target is outside workspace"

        return real_full, None

    async def read_workspace_file(workspace: str, file_path: str) -> str:
        """Read a file from a workspace directory."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        # Block sensitive files
        basename = os.path.basename(file_path)
        if basename in SENSITIVE_FILES or basename.startswith(".env"):
            return json.dumps({"error": f"Cannot read '{basename}' — sensitive file. Use list_secrets to view configured secrets."})

        ws_path = ws.get("path", "")
        full, err = _safe_workspace_path(ws_path, file_path)
        if err:
            return json.dumps({"error": err})

        if os.path.islink(full):
            return json.dumps({"error": "Cannot read symlinks — security restriction"})
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
        """Write a file to a workspace directory. Respects workspace protection settings."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        # Check readonly workspace
        if ws.get("readonly"):
            if _is_protected_file(file_path, ws):
                return json.dumps({"error": f"File '{file_path}' is protected in this workspace and cannot be modified"})

        ws_path = ws.get("path", "")

        # Validate path before creating dirs
        if ".." in file_path:
            return json.dumps({"error": "Path traversal not allowed"})

        full = os.path.join(ws_path, file_path)
        abs_ws = os.path.abspath(ws_path)
        if not os.path.abspath(full).startswith(abs_ws):
            return json.dumps({"error": "Path traversal not allowed"})

        # Check parent directory doesn't escape via symlink
        parent = os.path.dirname(full)
        if parent and os.path.exists(parent):
            real_parent = os.path.realpath(parent)
            if not real_parent.startswith(abs_ws):
                return json.dumps({"error": "Symlink escape not allowed — parent directory points outside workspace"})

        try:
            if parent:
                os.makedirs(parent, exist_ok=True)
            Path(full).write_text(content)
            return json.dumps({"ok": True, "path": file_path, "size": len(content)})
        except Exception as e:
            return json.dumps({"error": f"Cannot write file: {e}"})

    async def delete_workspace_file(workspace: str, file_path: str) -> str:
        """Delete a file from a workspace directory."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        if ws.get("readonly"):
            return json.dumps({"error": "This workspace is read-only — files cannot be deleted"})

        ws_path = ws.get("path", "")
        full, err = _safe_workspace_path(ws_path, file_path)
        if err:
            return json.dumps({"error": err})

        if not os.path.exists(full):
            return json.dumps({"error": f"File not found: {file_path}"})

        # Don't follow symlinks for deletion — remove the link itself
        if os.path.islink(full):
            os.unlink(full)
            return json.dumps({"ok": True, "path": file_path, "deleted": True, "was_symlink": True})

        try:
            if os.path.isdir(full):
                import shutil
                shutil.rmtree(full, onerror=lambda *_: None)
            else:
                os.remove(full)
            return json.dumps({"ok": True, "path": file_path, "deleted": True})
        except Exception as e:
            return json.dumps({"error": f"Cannot delete: {e}"})

    async def create_workspace(
        name: str,
        stack: str = "custom",
        description: str = "",
        git_url: str = "",
        branch: str = "main",
        instance_id: str = "",
        readonly: str = "false",
    ) -> str:
        """Create a new workspace. stack can be: python, node, static, custom. git_url clones a repo."""
        import asyncio

        # Validate name
        name = name.strip().lower()
        if not re.match(r"^[a-z][a-z0-9_-]{1,30}$", name):
            return json.dumps({"error": "Name must be 2-31 chars, lowercase, start with letter, only a-z0-9_-"})

        existing = await db.fetch_one("workspaces", project_id=ctx.project_id, name=name)
        if existing:
            return json.dumps({
                "ok": True,
                "already_exists": True,
                "workspace": name,
                "id": existing.get("id", ""),
                "path": existing.get("path", ""),
                "stack": existing.get("stack", existing.get("ws_type", "custom")),
                "instance_id": existing.get("instance_id", ""),
            })

        ws_path = str(settings.workspace_path(name))
        ws_id = f"ws_{token_gen.token_hex(8)}"
        is_readonly = readonly.lower() in ("true", "1", "yes")

        # Clone or create directory
        if git_url:
            if not git_url.startswith("http"):
                git_url = f"https://github.com/{git_url}.git"
            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "-b", branch, git_url, ws_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return json.dumps({"error": f"Clone failed: {stdout.decode()[:500]}"})
        else:
            os.makedirs(ws_path, exist_ok=True)
            _scaffold_workspace(ws_path, stack, name)

        # Write config.toml
        from nso.shared.models import WorkspaceConfig, WorkspaceGitConfig, WorkspaceDeployConfig
        from nso.engine.workspace.config import write_config

        config = WorkspaceConfig(
            name=name,
            type=stack or "custom",
            description=description,
            git=WorkspaceGitConfig(url=git_url, branch=branch),
            deploy=WorkspaceDeployConfig(instance_id=instance_id or None),
        )
        write_config(ws_path, config)

        now = datetime.now(timezone.utc).isoformat()
        await db.insert("workspaces", {
            "id": ws_id,
            "project_id": ctx.project_id,
            "name": name,
            "path": ws_path,
            "ws_type": "git" if git_url else "custom",
            "stack": stack,
            "description": description,
            "instance_id": instance_id or None,
            "git_url": git_url,
            "branch": branch,
            "readonly": 1 if is_readonly else 0,
            "protected_files": "[]",
            "created_at": now,
            "updated_at": now,
        })

        return json.dumps({
            "ok": True,
            "workspace": name,
            "id": ws_id,
            "path": ws_path,
            "stack": stack,
            "readonly": is_readonly,
            "message": f"Workspace '{name}' created successfully",
        })

    # Allowed command prefixes for workspace execution
    _ALLOWED_CMD_PREFIXES = [
        # Node.js / npm / yarn / pnpm
        "npm ", "npm install", "npx ", "yarn ", "pnpm ", "node ",
        # Python
        "pip ", "pip install", "pip3 ", "python ", "python3 ",
        "pip install -r", "pip3 install -r",
        # Build tools
        "make", "cmake ", "cargo ", "go ", "rustc ",
        # Package/dependency management
        "composer ", "bundle ", "gem ",
        # Common build/test commands
        "cat ", "ls ", "head ", "tail ", "wc ", "grep ", "find ",
        "mkdir ", "cp ", "mv ", "touch ",
        # Git (read-only operations)
        "git status", "git log", "git diff", "git branch",
        "git clone", "git pull", "git fetch",
        # System info
        "whoami", "pwd", "env", "which ", "echo ",
        # Process
        "kill ", "pkill ",
    ]

    # Patterns that are NEVER allowed regardless of prefix match
    _BLOCKED_PATTERNS = [
        "rm -rf /", "rm -rf /*", "rm -rf ~",
        "mkfs", "dd if=", "dd of=/dev",
        "> /dev/sd", "> /dev/nv",
        "shutdown", "reboot", "poweroff", "halt",
        "init 0", "init 6",
        ":(){ :|:", "fork",  # fork bomb
        "chmod 777 /", "chown root /",
        "curl|bash", "curl|sh", "wget|bash", "wget|sh",  # pipe to shell
        "/etc/shadow", "/etc/passwd",
        "master_key", "id_rsa", "id_ed25519",  # SSH key access
        "NSO_JWT_SECRET", "AGENT_ADMIN",  # secret env vars
    ]

    async def exec_in_workspace(workspace: str, command: str, timeout: int = 120) -> str:
        """Execute a shell command inside a workspace directory. Use this for:
        - npm install, npm run build, pip install, etc.
        - Any command the user asks you to run
        - Setting up dependencies, building, testing
        Always prefer EXECUTING commands over telling the user what to run."""
        import asyncio as _asyncio

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        if not ws_path or not os.path.isdir(ws_path):
            return json.dumps({"error": f"Workspace path not found: {ws_path}"})

        # Block dangerous patterns first
        cmd_lower = command.lower().strip()
        for pattern in _BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return json.dumps({"error": f"Command blocked for safety: contains '{pattern}'"})

        # Split compound commands and validate each part
        # Handle &&, ||, ;, | chains
        import re
        parts = re.split(r'\s*(?:&&|\|\||;)\s*', command.strip())
        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                continue
            # Check if the first word/prefix matches allowed commands
            part_lower = part_stripped.lower()
            allowed = False
            for prefix in _ALLOWED_CMD_PREFIXES:
                if part_lower.startswith(prefix) or part_lower == prefix.strip():
                    allowed = True
                    break
            if not allowed:
                return json.dumps({
                    "error": f"Command not allowed: '{part_stripped.split()[0]}'. "
                             f"Allowed: npm, npx, yarn, pip, python, node, make, cargo, go, git, etc.",
                })

        # Prevent reading outside workspace via command arguments
        abs_ws = os.path.abspath(ws_path)
        if "/opt/nso/data" in command or "/opt/nso/config" in command:
            return json.dumps({"error": "Cannot access NSO system directories from workspace"})

        try:
            proc = await _asyncio.create_subprocess_shell(
                command,
                cwd=ws_path,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.STDOUT,
                env={**os.environ, "HOME": "/root", "NODE_ENV": "production"},
            )
            try:
                stdout, _ = await _asyncio.wait_for(proc.communicate(), timeout=timeout)
            except _asyncio.TimeoutError:
                proc.kill()
                return json.dumps({"error": f"Command timed out after {timeout}s", "command": command})

            output = stdout.decode(errors="replace")
            if len(output) > 5000:
                output = output[:2000] + "\n...(truncated)...\n" + output[-2000:]

            return json.dumps({
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "output": output,
                "command": command,
                "cwd": ws_path,
            })
        except Exception as e:
            return json.dumps({"error": f"Exec failed: {e}", "command": command})

    async def list_workspace_files(workspace: str, path: str = "") -> str:
        """List files and directories in a workspace. Returns file names, sizes, types."""
        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        ws_path = ws.get("path", "")
        target = os.path.join(ws_path, path) if path else ws_path

        if ".." in path or not os.path.abspath(target).startswith(os.path.abspath(ws_path)):
            return json.dumps({"error": "Path traversal not allowed"})

        if not os.path.isdir(target):
            return json.dumps({"error": f"Directory not found: {path or '/'}"})

        items = []
        try:
            for entry in sorted(os.listdir(target))[:100]:
                if entry.startswith(".") or entry in ("node_modules", "__pycache__", "venv", ".venv"):
                    continue
                full = os.path.join(target, entry)
                is_dir = os.path.isdir(full)
                items.append({
                    "name": entry,
                    "type": "dir" if is_dir else "file",
                    "size": os.path.getsize(full) if not is_dir else 0,
                })
        except Exception as e:
            return json.dumps({"error": f"Cannot list: {e}"})

        return json.dumps({"path": path or "/", "items": items, "count": len(items)})

    async def clean_workspace(workspace: str, keep: str = "deploy.toml,config.toml") -> str:
        """Delete ALL files in a workspace EXCEPT the ones listed in 'keep' (comma-separated).
        Use this when user says 'delete everything except X' or 'clean the workspace'.
        Default keeps: deploy.toml, config.toml."""
        import shutil

        ws = await db.fetch_one("workspaces", project_id=ctx.project_id, name=workspace)
        if not ws:
            return json.dumps({"error": f"Workspace '{workspace}' not found"})

        if ws.get("readonly"):
            return json.dumps({"error": "This workspace is read-only"})

        ws_path = ws.get("path", "")
        if not ws_path or not os.path.isdir(ws_path):
            return json.dumps({"error": "Workspace path not found"})

        keep_set = {f.strip() for f in keep.split(",") if f.strip()}
        keep_set.add("config.toml")  # Always protect config.toml

        deleted = []
        kept = []
        for entry in os.listdir(ws_path):
            if entry.startswith("."):
                continue
            if entry in keep_set:
                kept.append(entry)
                continue
            full = os.path.join(ws_path, entry)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
                deleted.append(entry)
            except Exception as e:
                kept.append(f"{entry} (error: {e})")

        return json.dumps({
            "ok": True,
            "deleted": deleted,
            "kept": kept,
            "message": f"Deleted {len(deleted)} items, kept {len(kept)}",
        })

    return [
        (analyze_project, "analyze_project", "Analyze workspace to detect stack, files, dependencies, entry points"),
        (generate_deploy_config, "generate_deploy_config", "Generate deploy.toml from analysis"),
        (list_workspaces, "list_workspaces", "List all workspaces in the project"),
        (list_instances, "list_instances", "List all VPS instances in the project"),
        (read_workspace_file, "read_workspace_file", "Read a file from workspace"),
        (write_workspace_file, "write_workspace_file", "Write/create a file in workspace (respects protection)"),
        (delete_workspace_file, "delete_workspace_file", "Delete a file from workspace"),
        (clean_workspace, "clean_workspace", "Delete ALL files except specified ones (e.g. keep='deploy.toml,config.toml'). Use when user says 'delete everything except X'."),
        (list_workspace_files, "list_workspace_files", "List files/dirs in a workspace path"),
        (exec_in_workspace, "exec_in_workspace", "Execute a shell command inside workspace dir (npm install, build, pip install, etc.)"),
        (create_workspace, "create_workspace", "Create a new workspace with stack (python/node/static/custom), optional git URL"),
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


def _scaffold_workspace(ws_path: str, stack: str, name: str) -> None:
    """Create starter files for a workspace based on its stack."""
    if not stack or stack == "custom":
        return

    existing = set(os.listdir(ws_path)) if os.path.isdir(ws_path) else set()
    if existing - {"config.toml", ".git"}:
        return

    os.makedirs(ws_path, exist_ok=True)

    def _write(fname: str, content: str) -> None:
        fpath = os.path.join(ws_path, fname)
        if not os.path.exists(fpath):
            Path(fpath).write_text(content)

    if stack == "node":
        _write("package.json", json.dumps({
            "name": name, "version": "0.1.0", "private": True,
            "scripts": {"dev": "npx serve -l 3000 .", "start": "npx serve -l 3000 ."}
        }, indent=2))
        _write("index.html", f"<!DOCTYPE html>\n<html><head><title>{name}</title></head>\n<body><h1>{name}</h1><p>Ready.</p></body></html>")
    elif stack == "python":
        _write("requirements.txt", "fastapi\nuvicorn\n")
        _write("main.py", f'from fastapi import FastAPI\n\napp = FastAPI(title="{name}")\n\n@app.get("/")\ndef root():\n    return {{"workspace": "{name}", "status": "running"}}\n')
    elif stack == "static":
        _write("index.html", f"<!DOCTYPE html>\n<html><head><title>{name}</title></head>\n<body><h1>{name}</h1><p>Static workspace ready.</p></body></html>")


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
