"""
NSO Deploy Pipeline — executes deploy.toml phases on the agent.

Pipeline phases:
  0. Prepare   — parse config, resolve secrets, snapshot, extract
  1. Pre-hooks — hooks.pre_deploy
  2. System    — apt packages, users, firewall, OS services
  3. Setup     — dirs, files, scripts
  4. Install   — dependency installation
  5. Build     — compilation, asset generation
  6. Data      — migrations, seeds
  7. Services  — systemd units, nginx, SSL
  8. Health    — post-deploy verification
  9. Post-hooks — hooks.post_deploy, smoke tests
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toml_parser import parse_toml, resolve_secrets, merge_env
from generators import generate_systemd_unit, generate_nginx_config, generate_env_file, SERVICE_PREFIX
from healthcheck import run_health_check

logger = logging.getLogger("nso-agent.pipeline")

DEPLOY_STATE_FILE = Path("/opt/nso/data/deploy-state.json")
FIRST_DEPLOY_MARKER = ".nso-first-deploy-done"
DEFAULT_TIMEOUT = 300
MAX_LOG_LINES = 200


class PipelineResult:
    """Collects results from each pipeline phase."""

    def __init__(self):
        self.phases: list[dict[str, Any]] = []
        self.ok = True
        self.error = ""
        self.rolled_back = False

    def log_phase(self, name: str, ok: bool, message: str = "", duration: float = 0):
        self.phases.append({
            "phase": name,
            "ok": ok,
            "message": message[:500],
            "duration_s": round(duration, 2),
        })
        if not ok:
            self.ok = False
            self.error = f"Phase '{name}' failed: {message[:300]}"

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error": self.error,
            "rolled_back": self.rolled_back,
            "phases": self.phases,
        }


class DeployPipeline:
    """Orchestrates the full deploy pipeline from deploy.toml."""

    def __init__(
        self,
        target_dir: str = "/opt/app",
        secrets: dict[str, str] | None = None,
    ):
        self.target_dir = target_dir
        self.secrets = secrets or {}
        self.config: dict[str, Any] = {}
        self.env: dict[str, str] = {}
        self.result = PipelineResult()
        self.snapshot_name: str = ""
        self.is_first_deploy = False

    async def run(self, deploy_toml_content: str | None = None) -> PipelineResult:
        """Execute the full pipeline.

        Args:
            deploy_toml_content: Raw deploy.toml text. If None, reads from target_dir.
        """
        # Phase 0: Prepare
        t0 = _now()
        try:
            self._prepare(deploy_toml_content)
            self.result.log_phase("prepare", True, "Config parsed, secrets resolved", _elapsed(t0))
        except Exception as exc:
            self.result.log_phase("prepare", False, str(exc), _elapsed(t0))
            return self.result

        # Phase 1: Pre-deploy hooks
        ok = await self._run_hooks("pre_deploy")
        if not ok and self._hook_aborts("pre_deploy"):
            return self.result

        # Phase 2: System
        await self._phase_system()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 3: Setup
        await self._phase_setup()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 4: Install
        await self._phase_install()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 5: Build
        await self._phase_build()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 6: Data
        await self._phase_data()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 7: Services
        await self._phase_services()
        if not self.result.ok:
            await self._rollback()
            return self.result

        # Phase 8: Health check
        await self._phase_health()
        if not self.result.ok:
            rollback_cfg = self.config.get("rollback", {})
            if rollback_cfg.get("auto", True):
                await self._rollback()
            return self.result

        # Phase 9: Post-deploy hooks
        await self._run_hooks("post_deploy")

        # Mark first deploy as done
        marker = os.path.join(self.target_dir, FIRST_DEPLOY_MARKER)
        if not os.path.exists(marker):
            Path(marker).touch()

        return self.result

    def _prepare(self, deploy_toml_content: str | None):
        """Parse deploy.toml and resolve secrets."""
        if deploy_toml_content:
            self.config = parse_toml(deploy_toml_content)
        else:
            toml_path = os.path.join(self.target_dir, "deploy.toml")
            if os.path.exists(toml_path):
                with open(toml_path) as f:
                    self.config = parse_toml(f.read())
            else:
                # Fallback: no deploy.toml, use minimal config
                self.config = {}
                return

        # Resolve secrets
        if self.secrets:
            self.config = resolve_secrets(self.config, self.secrets)

        # Merge all env vars
        self.env = merge_env(self.config)
        # Also add resolved secrets as env
        for k, v in self.secrets.items():
            if k not in self.env:
                self.env[k] = v

        # Write .env file
        env_path = os.path.join(self.target_dir, ".env")
        Path(env_path).write_text(generate_env_file(self.env))

        # Check first deploy
        marker = os.path.join(self.target_dir, FIRST_DEPLOY_MARKER)
        self.is_first_deploy = not os.path.exists(marker)

    async def _phase_system(self):
        """Install system packages, create users, configure firewall."""
        system = self.config.get("system", {})
        if not system:
            self.result.log_phase("system", True, "No system config, skipping")
            return

        t0 = _now()
        messages = []

        # Packages
        packages = system.get("packages", [])
        if packages and isinstance(packages, list):
            pkg_list = " ".join(packages)
            out, code = await _run_cmd(
                f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list}",
                timeout=300,
            )
            if code != 0:
                self.result.log_phase("system", False, f"apt install failed: {out[-300:]}", _elapsed(t0))
                return
            messages.append(f"Installed: {pkg_list}")

        # Users
        users = system.get("users", [])
        if isinstance(users, list):
            for user in users:
                if not isinstance(user, dict):
                    continue
                name = user.get("name", "")
                if not name:
                    continue
                shell = user.get("shell", "/bin/bash")
                home = user.get("home", f"/home/{name}")
                groups = user.get("groups", [])

                cmd = f"id {name} 2>/dev/null || useradd -m -s {shell} -d {home} {name}"
                await _run_cmd(cmd)

                if groups and isinstance(groups, list):
                    for g in groups:
                        await _run_cmd(f"usermod -aG {g} {name} 2>/dev/null || true")
                messages.append(f"User: {name}")

        # Firewall rules
        firewall = system.get("firewall", [])
        if isinstance(firewall, list):
            for rule in firewall:
                if not isinstance(rule, dict):
                    continue
                port = rule.get("port", "")
                proto = rule.get("proto", "tcp")
                from_addr = rule.get("from", "")
                action = rule.get("action", "allow")

                if from_addr:
                    cmd = f"ufw {action} from {from_addr} to any port {port} proto {proto}"
                else:
                    cmd = f"ufw {action} {port}/{proto}"
                await _run_cmd(cmd)
                messages.append(f"Firewall: {action} {port}/{proto}")

        # System services
        services = system.get("services", {})
        if isinstance(services, dict):
            for svc in services.get("enable", []):
                await _run_cmd(f"systemctl enable --now {svc} 2>/dev/null || true")
                messages.append(f"Enabled: {svc}")
            for svc in services.get("disable", []):
                await _run_cmd(f"systemctl disable --now {svc} 2>/dev/null || true")

        self.result.log_phase("system", True, "; ".join(messages), _elapsed(t0))

    async def _phase_setup(self):
        """Create directories, write files, run setup scripts."""
        setup = self.config.get("setup", {})
        if not setup:
            self.result.log_phase("setup", True, "No setup config, skipping")
            return

        t0 = _now()
        messages = []

        # Directories
        dirs = setup.get("dirs", {})
        dir_list = dirs.get("create", []) if isinstance(dirs, dict) else []
        if isinstance(dir_list, list):
            for d in dir_list:
                if isinstance(d, dict):
                    path = d.get("path", "")
                    owner = d.get("owner", "")
                    mode = d.get("mode", "0755")
                elif isinstance(d, str):
                    path = d
                    owner = ""
                    mode = "0755"
                else:
                    continue
                if path:
                    os.makedirs(path, exist_ok=True)
                    if mode:
                        await _run_cmd(f"chmod {mode} {path}")
                    if owner:
                        await _run_cmd(f"chown {owner}:{owner} {path} 2>/dev/null || true")
                    messages.append(f"Dir: {path}")

        # Files
        files = setup.get("files", [])
        if isinstance(files, list):
            for f in files:
                if not isinstance(f, dict):
                    continue
                path = f.get("path", "")
                content = f.get("content", "")
                owner = f.get("owner", "")
                mode = f.get("mode", "0644")
                is_template = f.get("template", False)

                if not path:
                    continue

                # Template interpolation
                if is_template and self.env:
                    for k, v in self.env.items():
                        content = content.replace(f"{{{{{k}}}}}", v)

                os.makedirs(os.path.dirname(path), exist_ok=True)
                Path(path).write_text(content)
                if mode:
                    await _run_cmd(f"chmod {mode} {path}")
                if owner:
                    await _run_cmd(f"chown {owner}:{owner} {path} 2>/dev/null || true")
                messages.append(f"File: {path}")

        # Scripts
        scripts = setup.get("scripts", [])
        if isinstance(scripts, list):
            for s in scripts:
                if not isinstance(s, dict):
                    continue
                name = s.get("name", "unnamed")
                command = s.get("command", "")
                timeout = s.get("timeout", 60)
                user = s.get("user", "")

                if not command:
                    continue

                if user and user != "root":
                    command = f"su - {user} -c '{command}'"

                out, code = await _run_cmd(command, timeout=timeout, cwd=self.target_dir)
                if code != 0:
                    on_fail = s.get("on_fail", "abort")
                    msg = f"Script '{name}' failed (code {code}): {out[-200:]}"
                    if on_fail == "abort":
                        self.result.log_phase("setup", False, msg, _elapsed(t0))
                        return
                    elif on_fail == "warn":
                        messages.append(f"Script '{name}' failed (warning)")
                        logger.warning(msg)
                    # ignore: continue
                else:
                    messages.append(f"Script: {name}")

        self.result.log_phase("setup", True, "; ".join(messages), _elapsed(t0))

    async def _phase_install(self):
        """Install dependencies."""
        install = self.config.get("install", {})
        t0 = _now()

        if isinstance(install, dict):
            command = install.get("command", "")
            timeout = install.get("timeout", DEFAULT_TIMEOUT)
        else:
            command = ""
            timeout = DEFAULT_TIMEOUT

        # Auto-detect if no command specified
        if not command:
            stack = self._detect_stack()
            from deploy import INSTALL_COMMANDS
            command = INSTALL_COMMANDS.get(stack, "")
            if not command:
                self.result.log_phase("install", True, f"No install needed (stack={stack})")
                return

        out, code = await _run_cmd(command, timeout=timeout, cwd=self.target_dir)
        if code != 0:
            self.result.log_phase("install", False, f"Install failed: {out[-300:]}", _elapsed(t0))
        else:
            self.result.log_phase("install", True, f"Dependencies installed", _elapsed(t0))

    async def _phase_build(self):
        """Run build commands."""
        build = self.config.get("build", {})
        if not build:
            self.result.log_phase("build", True, "No build config, skipping")
            return

        t0 = _now()
        command = build.get("command", "")
        timeout = build.get("timeout", 600)
        build_env = build.get("env", {})

        # Build env string
        env_prefix = ""
        if isinstance(build_env, dict) and build_env:
            env_parts = [f"{k}={v}" for k, v in build_env.items()]
            env_prefix = " ".join(env_parts) + " "

        if command:
            out, code = await _run_cmd(
                f"{env_prefix}{command}",
                timeout=timeout,
                cwd=self.target_dir,
            )
            if code != 0:
                self.result.log_phase("build", False, f"Build failed: {out[-300:]}", _elapsed(t0))
                return

        # Additional build steps
        steps = build.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                name = step.get("name", "unnamed")
                cmd = step.get("command", "")
                step_timeout = step.get("timeout", 120)

                if not cmd:
                    continue
                out, code = await _run_cmd(cmd, timeout=step_timeout, cwd=self.target_dir)
                if code != 0:
                    self.result.log_phase("build", False, f"Build step '{name}' failed: {out[-300:]}", _elapsed(t0))
                    return

        self.result.log_phase("build", True, "Build completed", _elapsed(t0))

    async def _phase_data(self):
        """Run migrations and seeds."""
        data = self.config.get("data", {})
        if not data:
            self.result.log_phase("data", True, "No data config, skipping")
            return

        t0 = _now()
        messages = []

        # Migrate
        migrate = data.get("migrate", {})
        if isinstance(migrate, dict) and migrate.get("command"):
            cmd = migrate["command"]
            timeout = migrate.get("timeout", 120)
            on_fail = migrate.get("on_fail", "abort")

            out, code = await _run_cmd(cmd, timeout=timeout, cwd=self.target_dir)
            if code != 0:
                msg = f"Migration failed: {out[-300:]}"
                if on_fail == "abort":
                    self.result.log_phase("data", False, msg, _elapsed(t0))
                    return
                elif on_fail == "warn":
                    messages.append("Migration failed (warning)")
                    logger.warning(msg)
            else:
                messages.append("Migrations applied")

        # Seed
        seed = data.get("seed", {})
        if isinstance(seed, dict) and seed.get("command"):
            only_if = seed.get("only_if", "always")
            should_run = (
                only_if == "always" or
                (only_if == "first_deploy" and self.is_first_deploy)
            )

            if should_run:
                cmd = seed["command"]
                timeout = seed.get("timeout", 60)
                on_fail = seed.get("on_fail", "warn")

                out, code = await _run_cmd(cmd, timeout=timeout, cwd=self.target_dir)
                if code != 0:
                    msg = f"Seed failed: {out[-200:]}"
                    if on_fail == "abort":
                        self.result.log_phase("data", False, msg, _elapsed(t0))
                        return
                    elif on_fail == "warn":
                        messages.append("Seed failed (warning)")
                else:
                    messages.append("Seed completed")

        # Data scripts
        scripts = data.get("scripts", [])
        if isinstance(scripts, list):
            for s in scripts:
                if not isinstance(s, dict):
                    continue
                name = s.get("name", "")
                cmd = s.get("command", "")
                timeout = s.get("timeout", 60)
                on_fail = s.get("on_fail", "ignore")

                if not cmd:
                    continue
                out, code = await _run_cmd(cmd, timeout=timeout, cwd=self.target_dir)
                if code != 0 and on_fail == "abort":
                    self.result.log_phase("data", False, f"Data script '{name}' failed", _elapsed(t0))
                    return
                elif code == 0:
                    messages.append(f"Script: {name}")

        self.result.log_phase("data", True, "; ".join(messages), _elapsed(t0))

    async def _phase_services(self):
        """Generate and start systemd services, nginx, SSL."""
        services = self.config.get("services", {})
        t0 = _now()
        messages = []

        if not services:
            # Legacy: just restart nso-app if no services defined
            await _run_cmd("systemctl restart nso-app 2>/dev/null || true")
            self.result.log_phase("services", True, "Restarted nso-app (legacy)")
            return

        # Resolve start order (topological sort on depends_on)
        ordered = _topo_sort(services)

        # Generate and install systemd units
        for svc_name in ordered:
            svc_config = services[svc_name]
            if not isinstance(svc_config, dict):
                continue

            unit_content = generate_systemd_unit(
                svc_name, svc_config, self.env, self.target_dir,
            )
            unit_name = f"{SERVICE_PREFIX}-{svc_name}"
            unit_path = f"/etc/systemd/system/{unit_name}.service"
            Path(unit_path).write_text(unit_content)
            messages.append(f"Unit: {unit_name}")

        # Reload systemd
        await _run_cmd("systemctl daemon-reload")

        # Generate and install nginx config
        nginx = self.config.get("nginx", {})
        if nginx:
            domains_list = []
            config_domains = self.config.get("domains", [])
            if isinstance(config_domains, list):
                for d in config_domains:
                    if isinstance(d, dict) and d.get("name"):
                        domains_list.append(d["name"])

            nginx_content = generate_nginx_config(self.config, domains_list)
            ws_name = self.config.get("workspace", {}).get("name", "app")
            nginx_path = f"/etc/nginx/sites-available/nso-app-{ws_name}"
            nginx_link = f"/etc/nginx/sites-enabled/nso-app-{ws_name}"

            Path(nginx_path).write_text(nginx_content)
            if not os.path.exists(nginx_link):
                os.symlink(nginx_path, nginx_link)

            # Test and reload nginx
            out, code = await _run_cmd("nginx -t 2>&1")
            if code == 0:
                await _run_cmd("systemctl reload nginx")
                messages.append("Nginx configured")
            else:
                logger.warning("Nginx config test failed: %s", out)
                messages.append(f"Nginx config invalid: {out[:100]}")

        # Start services in order
        for svc_name in ordered:
            unit_name = f"{SERVICE_PREFIX}-{svc_name}"
            await _run_cmd(f"systemctl enable {unit_name}")
            out, code = await _run_cmd(f"systemctl restart {unit_name}")
            if code != 0:
                self.result.log_phase("services", False,
                    f"Service {unit_name} failed to start: {out[:200]}", _elapsed(t0))
                return
            messages.append(f"Started: {unit_name}")

        # SSL
        domains_cfg = self.config.get("domains", [])
        if isinstance(domains_cfg, list):
            for d in domains_cfg:
                if isinstance(d, dict) and d.get("ssl", False) and d.get("name"):
                    domain = d["name"]
                    # Non-blocking certbot
                    await _run_cmd(
                        f"certbot certonly --nginx -d {domain} --non-interactive "
                        f"--agree-tos --register-unsafely-without-email 2>&1 || true",
                        timeout=120,
                    )
                    messages.append(f"SSL: {domain}")

        self.result.log_phase("services", True, "; ".join(messages), _elapsed(t0))

    async def _phase_health(self):
        """Run health checks."""
        health = self.config.get("health", {})
        if not health or health.get("strategy") == "none":
            self.result.log_phase("health", True, "No health check configured")
            return

        t0 = _now()
        passed, message = await run_health_check(health)
        self.result.log_phase("health", passed, message, _elapsed(t0))

    async def _run_hooks(self, hook_type: str) -> bool:
        """Run hooks of a given type (pre_deploy, post_deploy, on_rollback)."""
        hooks = self.config.get("hooks", {})
        hook_list = hooks.get(hook_type, [])
        if not isinstance(hook_list, list) or not hook_list:
            return True

        t0 = _now()
        for hook in hook_list:
            if not isinstance(hook, dict):
                continue
            name = hook.get("name", "unnamed")
            command = hook.get("command", "")
            timeout = hook.get("timeout", 60)
            on_fail = hook.get("on_fail", "ignore")

            if not command:
                continue

            # Interpolate template vars in hook commands
            for k, v in self.env.items():
                command = command.replace(f"{{{{{k}}}}}", v)

            # Also replace {{VERSION}} and {{DOMAIN}}
            ws = self.config.get("workspace", {})
            command = command.replace("{{VERSION}}", ws.get("version", ""))
            domains = self.config.get("domains", [])
            if isinstance(domains, list) and domains:
                first_domain = domains[0] if isinstance(domains[0], str) else domains[0].get("name", "")
                command = command.replace("{{DOMAIN}}", first_domain)

            out, code = await _run_cmd(command, timeout=timeout, cwd=self.target_dir)
            if code != 0:
                msg = f"Hook '{name}' failed (code {code}): {out[-200:]}"
                if on_fail == "abort":
                    self.result.log_phase(f"hooks.{hook_type}", False, msg, _elapsed(t0))
                    return False
                elif on_fail == "rollback":
                    self.result.log_phase(f"hooks.{hook_type}", False, msg, _elapsed(t0))
                    await self._rollback()
                    return False
                elif on_fail == "warn":
                    logger.warning(msg)
                # ignore: continue
            else:
                logger.info("Hook '%s' completed successfully", name)

        self.result.log_phase(f"hooks.{hook_type}", True, f"{len(hook_list)} hooks executed", _elapsed(t0))
        return True

    def _hook_aborts(self, hook_type: str) -> bool:
        """Check if any hook of this type has on_fail=abort."""
        hooks = self.config.get("hooks", {})
        hook_list = hooks.get(hook_type, [])
        if isinstance(hook_list, list):
            return any(
                isinstance(h, dict) and h.get("on_fail") == "abort"
                for h in hook_list
            )
        return False

    async def _rollback(self):
        """Rollback to previous snapshot."""
        if not self.snapshot_name:
            logger.warning("No snapshot available for rollback")
            return

        from deploy import _restore_snapshot, _list_snapshots
        ok = _restore_snapshot(self.target_dir, self.snapshot_name)
        if ok:
            self.result.rolled_back = True
            logger.info("Rolled back to snapshot %s", self.snapshot_name)

            # Restart all services
            services = self.config.get("services", {})
            if services:
                for svc_name in services:
                    await _run_cmd(f"systemctl restart {SERVICE_PREFIX}-{svc_name} 2>/dev/null || true")
            else:
                await _run_cmd("systemctl restart nso-app 2>/dev/null || true")

            # Run on_rollback hooks
            await self._run_hooks("on_rollback")
        else:
            logger.error("Rollback failed — snapshot %s not found", self.snapshot_name)

    def _detect_stack(self) -> str:
        """Auto-detect project stack from marker files."""
        from deploy import STACK_INDICATORS
        for filename, stack in STACK_INDICATORS:
            if os.path.exists(os.path.join(self.target_dir, filename)):
                return stack
        return "unknown"


def _topo_sort(services: dict[str, Any]) -> list[str]:
    """Topological sort of services based on depends_on."""
    result = []
    visited = set()
    visiting = set()

    def visit(name: str):
        if name in visited:
            return
        if name in visiting:
            # Circular dependency — just add it
            result.append(name)
            visited.add(name)
            return
        visiting.add(name)

        svc = services.get(name, {})
        if isinstance(svc, dict):
            deps = svc.get("depends_on", [])
            if isinstance(deps, list):
                for dep in deps:
                    if dep in services:
                        visit(dep)

        visiting.discard(name)
        visited.add(name)
        result.append(name)

    for name in services:
        visit(name)

    return result


async def _run_cmd(
    command: str,
    timeout: int = 120,
    cwd: str | None = None,
) -> tuple[str, int]:
    """Run a shell command and return (output, return_code)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace")
        # Truncate very long output
        lines = output.splitlines()
        if len(lines) > MAX_LOG_LINES:
            output = "\n".join(lines[:50] + ["... truncated ..."] + lines[-50:])
        return output, proc.returncode or 0
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return f"Command timed out after {timeout}s", 1
    except Exception as exc:
        return f"Command error: {exc}", 1


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _elapsed(start: float) -> float:
    return datetime.now(timezone.utc).timestamp() - start
