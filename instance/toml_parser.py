"""
Extended TOML parser for deploy.toml — NSO deploy configuration.

Supports:
- Standard TOML sections, nested sections, key-value pairs
- Array of tables ([[section]])
- Inline arrays [val1, val2]
- Inline tables {key = val, key2 = val2}
- Multi-line strings (triple quotes)
- Secret references: ${secret:KEY}
- Template variables: {{KEY}}
"""

import logging
import re
from typing import Any

logger = logging.getLogger("nso-agent.toml")


def parse_toml(text: str) -> dict:
    """Parse TOML text into a nested dict."""
    result: dict = {}
    current_section = result
    current_path: list[str] = []
    array_table_path: list[str] | None = None
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip empty / comments
        if not line or line.startswith("#"):
            i += 1
            continue

        # Array of tables: [[section.name]]
        if line.startswith("[[") and line.endswith("]]"):
            section_name = line[2:-2].strip()
            parts = section_name.split(".")
            array_table_path = parts

            # Navigate to parent
            parent = result
            for p in parts[:-1]:
                if p not in parent:
                    parent[p] = {}
                parent = parent[p]

            key = parts[-1]
            if key not in parent:
                parent[key] = []
            if not isinstance(parent[key], list):
                parent[key] = [parent[key]]

            new_entry: dict = {}
            parent[key].append(new_entry)
            current_section = new_entry
            current_path = parts
            i += 1
            continue

        # Regular section: [section.name]
        if line.startswith("[") and line.endswith("]") and not line.startswith("[["):
            section_name = line[1:-1].strip()
            parts = section_name.split(".")
            array_table_path = None

            current_section = result
            for p in parts:
                if p not in current_section:
                    current_section[p] = {}
                val = current_section[p]
                # If it's an array of tables, point to the last entry
                if isinstance(val, list):
                    current_section = val[-1]
                else:
                    current_section = val
            current_path = parts
            i += 1
            continue

        # Key = value
        if "=" in line:
            key, _, raw_value = line.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            # Multi-line string (triple quotes)
            if raw_value.startswith('"""'):
                value_lines = [raw_value[3:]]
                i += 1
                while i < len(lines):
                    if '"""' in lines[i]:
                        value_lines.append(lines[i].split('"""')[0])
                        break
                    value_lines.append(lines[i])
                    i += 1
                current_section[key] = "\n".join(value_lines)
                i += 1
                continue

            parsed = _parse_value(raw_value)
            current_section[key] = parsed

        i += 1

    return result


def _parse_value(raw: str) -> Any:
    """Parse a single TOML value."""
    # Remove inline comment
    val = _strip_comment(raw)

    if not val:
        return ""

    # String (double or single quoted)
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        return val[1:-1]

    # Boolean
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False

    # Inline array: [val1, val2, ...]
    if val.startswith("[") and val.endswith("]"):
        return _parse_inline_array(val)

    # Inline table: {key = val, ...}
    if val.startswith("{") and val.endswith("}"):
        return _parse_inline_table(val)

    # Integer
    if re.match(r'^-?\d+$', val):
        return int(val)

    # Float
    try:
        return float(val)
    except ValueError:
        pass

    return val


def _strip_comment(val: str) -> str:
    """Strip trailing comments, respecting strings."""
    in_str = False
    quote_char = ""
    for i, ch in enumerate(val):
        if ch in ('"', "'") and not in_str:
            in_str = True
            quote_char = ch
        elif ch == quote_char and in_str:
            in_str = False
        elif ch == "#" and not in_str:
            return val[:i].strip()
    return val.strip()


def _parse_inline_array(val: str) -> list:
    """Parse [val1, val2, ...] into a list."""
    inner = val[1:-1].strip()
    if not inner:
        return []

    items = []
    current = ""
    depth = 0
    in_str = False
    quote_char = ""

    for ch in inner:
        if ch in ('"', "'") and not in_str:
            in_str = True
            quote_char = ch
            current += ch
        elif ch == quote_char and in_str:
            in_str = False
            current += ch
        elif ch in ("[", "{") and not in_str:
            depth += 1
            current += ch
        elif ch in ("]", "}") and not in_str:
            depth -= 1
            current += ch
        elif ch == "," and depth == 0 and not in_str:
            items.append(_parse_value(current.strip()))
            current = ""
        else:
            current += ch

    if current.strip():
        items.append(_parse_value(current.strip()))

    return items


def _parse_inline_table(val: str) -> dict:
    """Parse {key = val, key2 = val2} into a dict."""
    inner = val[1:-1].strip()
    if not inner:
        return {}

    result = {}
    pairs = _split_table_pairs(inner)
    for pair in pairs:
        if "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        result[k.strip()] = _parse_value(v.strip())

    return result


def _split_table_pairs(inner: str) -> list[str]:
    """Split inline table by commas, respecting nesting."""
    pairs = []
    current = ""
    depth = 0
    in_str = False
    quote_char = ""

    for ch in inner:
        if ch in ('"', "'") and not in_str:
            in_str = True
            quote_char = ch
            current += ch
        elif ch == quote_char and in_str:
            in_str = False
            current += ch
        elif ch in ("[", "{") and not in_str:
            depth += 1
            current += ch
        elif ch in ("]", "}") and not in_str:
            depth -= 1
            current += ch
        elif ch == "," and depth == 0 and not in_str:
            pairs.append(current.strip())
            current = ""
        else:
            current += ch

    if current.strip():
        pairs.append(current.strip())

    return pairs


def resolve_secrets(config: dict, secrets: dict[str, str]) -> dict:
    """Replace ${secret:KEY} and {{KEY}} references with actual values."""
    return _resolve_recursive(config, secrets)


def _resolve_recursive(obj: Any, secrets: dict[str, str]) -> Any:
    if isinstance(obj, str):
        # ${secret:KEY}
        result = re.sub(
            r'\$\{secret:([^}]+)\}',
            lambda m: secrets.get(m.group(1), m.group(0)),
            obj,
        )
        # {{KEY}}
        result = re.sub(
            r'\{\{([^}]+)\}\}',
            lambda m: secrets.get(m.group(1).strip(), m.group(0)),
            result,
        )
        return result
    if isinstance(obj, dict):
        return {k: _resolve_recursive(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_recursive(v, secrets) for v in obj]
    return obj


def merge_env(deploy_config: dict) -> dict[str, str]:
    """Extract all env vars from deploy config into a flat dict."""
    env: dict[str, str] = {}

    # Top-level [env] section
    top_env = deploy_config.get("env", {})
    if isinstance(top_env, dict):
        for k, v in top_env.items():
            env[k] = str(v)

    # [build].env
    build_env = deploy_config.get("build", {}).get("env", {})
    if isinstance(build_env, dict):
        for k, v in build_env.items():
            env[k] = str(v)

    # Per-service env
    services = deploy_config.get("services", {})
    for svc_name, svc in services.items():
        if isinstance(svc, dict):
            svc_env = svc.get("env", {})
            if isinstance(svc_env, dict):
                for k, v in svc_env.items():
                    env[k] = str(v)

    return env
