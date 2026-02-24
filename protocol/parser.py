"""MMS Protocol Parser - TOML-based format for capsule definitions and instructions.

.mms files use a TOML-like declarative format:

    [capsule.api]
    runtime = "python"
    isolation = "container"
    entrypoint = "main.py"
    deps = ["fastapi", "uvicorn"]

    [capsule.api.env]
    PORT = "8080"
    DEBUG = "false"

    [capsule.api.code.main_py]
    source = '''
    from fastapi import FastAPI
    app = FastAPI()
    '''

    [pipeline.deploy]
    steps = [
        { capsule = "api", action = "build" },
        { capsule = "api", action = "start" },
    ]

    [instruction]
    run = [
        { target = "api", command = "pip install requests" },
        { target = "api", command = "python main.py" },
    ]
"""
import logging
import re
from typing import Any

logger = logging.getLogger("mms.protocol")


class MMSParser:
    """Parse .mms TOML-like files into executable instructions."""

    def parse(self, source: str) -> list[dict]:
        """Parse a .mms file and return a list of instructions."""
        data = self._parse_toml(source)
        instructions = []

        # Process capsule definitions
        for name, config in data.get("capsule", {}).items():
            if isinstance(config, dict):
                instructions.append(self._capsule_instruction(name, config))

        # Process environment definitions
        for name, config in data.get("env", {}).items():
            if isinstance(config, dict):
                instructions.append(self._env_instruction(name, config))

        # Process pipeline definitions
        for name, config in data.get("pipeline", {}).items():
            if isinstance(config, dict):
                instructions.append(self._pipeline_instruction(name, config))

        # Process direct instructions
        for instr in data.get("instruction", {}).get("run", []):
            if isinstance(instr, dict):
                instructions.append({
                    "action": "capsule.exec",
                    "target": instr.get("target", ""),
                    "command": instr.get("command", ""),
                })

        return instructions

    def parse_file(self, filepath: str) -> list[dict]:
        with open(filepath) as f:
            return self.parse(f.read())

    def _capsule_instruction(self, name: str, config: dict) -> dict:
        """Convert a [capsule.X] section into a create instruction."""
        # Extract code sections
        code = None
        code_sections = config.get("code", {})
        if isinstance(code_sections, dict):
            for filename, section in code_sections.items():
                if isinstance(section, dict) and "source" in section:
                    code = section["source"]
                elif isinstance(section, str):
                    code = section

        # Extract env vars
        env = config.get("env", {})
        if not isinstance(env, dict):
            env = {}

        # Extract deps
        deps = config.get("deps", [])
        if isinstance(deps, str):
            deps = [d.strip() for d in deps.split(",") if d.strip()]

        return {
            "action": "capsule.create",
            "name": name,
            "runtime": config.get("runtime", "python"),
            "isolation": config.get("isolation", "container"),
            "entrypoint": config.get("entrypoint", "main.py"),
            "deps": deps,
            "env": env,
            "ports": config.get("ports", []),
            "code": code,
        }

    def _env_instruction(self, name: str, config: dict) -> dict:
        packages = config.get("packages", [])
        if isinstance(packages, str):
            packages = [p.strip() for p in packages.split(",") if p.strip()]
        return {
            "action": "env.create",
            "name": name,
            "runtime": config.get("runtime", "python"),
            "packages": packages,
        }

    def _pipeline_instruction(self, name: str, config: dict) -> dict:
        steps = []
        for step in config.get("steps", []):
            if isinstance(step, dict):
                steps.append({
                    "capsule": step.get("capsule", ""),
                    "params": {
                        "command": step.get("command", ""),
                        "action": step.get("action", "start"),
                    },
                    "depends_on": step.get("depends_on", []),
                })
        return {
            "action": "pipeline.run",
            "name": name,
            "steps": steps,
        }

    # ── Minimal TOML Parser ──────────────────────────────────────
    # Handles the subset of TOML needed for .mms files

    def _parse_toml(self, source: str) -> dict:
        """Parse a TOML-like format into nested dicts."""
        root: dict[str, Any] = {}
        current_table = root
        current_path: list[str] = []

        lines = source.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                i += 1
                continue

            # Table header: [section.name]
            m = re.match(r"^\[([^\]]+)\]$", line)
            if m:
                path = [p.strip() for p in m.group(1).split(".")]
                current_path = path
                current_table = root
                for key in path:
                    if key not in current_table:
                        current_table[key] = {}
                    current_table = current_table[key]
                i += 1
                continue

            # Key = value
            m = re.match(r"^(\w+)\s*=\s*(.+)$", line)
            if m:
                key = m.group(1)
                value_str = m.group(2).strip()

                # Multi-line string (triple quotes)
                if value_str.startswith("'''") or value_str.startswith('"""'):
                    quote = value_str[:3]
                    if value_str.endswith(quote) and len(value_str) > 6:
                        # Single-line triple quote
                        current_table[key] = value_str[3:-3]
                    else:
                        # Multi-line
                        content_lines = [value_str[3:]]
                        i += 1
                        while i < len(lines):
                            if lines[i].strip().endswith(quote):
                                content_lines.append(lines[i].rstrip().removesuffix(quote))
                                break
                            content_lines.append(lines[i])
                            i += 1
                        current_table[key] = "\n".join(content_lines)
                    i += 1
                    continue

                # Array: [...] possibly multi-line
                if value_str.startswith("["):
                    full = value_str
                    while full.count("[") > full.count("]") and i + 1 < len(lines):
                        i += 1
                        full += " " + lines[i].strip()
                    current_table[key] = self._parse_array(full)
                    i += 1
                    continue

                # Simple value
                current_table[key] = self._parse_value(value_str)
                i += 1
                continue

            i += 1

        return root

    def _parse_value(self, s: str) -> Any:
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            return s[1:-1]
        if s.startswith("'") and s.endswith("'"):
            return s[1:-1]
        if s == "true":
            return True
        if s == "false":
            return False
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s

    def _parse_array(self, s: str) -> list:
        """Parse a TOML array, including inline tables."""
        s = s.strip()
        if not s.startswith("[") or not s.endswith("]"):
            return []

        inner = s[1:-1].strip()
        if not inner:
            return []

        # Inline table array: [{ ... }, { ... }]
        if inner.startswith("{"):
            items = []
            depth = 0
            current = ""
            for ch in inner:
                if ch == "{":
                    depth += 1
                    current += ch
                elif ch == "}":
                    depth -= 1
                    current += ch
                    if depth == 0:
                        items.append(self._parse_inline_table(current.strip()))
                        current = ""
                elif ch == "," and depth == 0:
                    continue
                else:
                    current += ch
            return items

        # Simple array: ["a", "b", "c"]
        items = []
        for part in inner.split(","):
            part = part.strip()
            if part:
                items.append(self._parse_value(part))
        return items

    def _parse_inline_table(self, s: str) -> dict:
        """Parse { key = "value", key2 = "value2" }."""
        s = s.strip()
        if s.startswith("{"):
            s = s[1:]
        if s.endswith("}"):
            s = s[:-1]

        result = {}
        for pair in s.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[k.strip()] = self._parse_value(v.strip())
        return result
