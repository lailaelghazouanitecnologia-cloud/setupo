import os
import logging
from typing import Optional

from nso.engine.workspace.config import read_config

logger = logging.getLogger("nso.workspace.nesting")

MAX_NESTING_DEPTH = 5


def resolve_children(workspace_path: str) -> dict:
    config = read_config(workspace_path)
    if not config:
        return {}

    config_file = os.path.join(workspace_path, "config.toml")
    if not os.path.isfile(config_file):
        return {}

    with open(config_file, "r") as f:
        from nso.engine.workspace.config import _parse_toml
        raw = _parse_toml(f.read())

    children_raw = raw.get("workspace", {}).get("children", {})
    children = {}
    for name, child_cfg in children_raw.items():
        if isinstance(child_cfg, dict) and "path" in child_cfg:
            child_path = os.path.join(workspace_path, child_cfg["path"])
            if os.path.isdir(child_path):
                children[name] = {
                    "path": child_path,
                    "config": read_config(child_path),
                }
    return children


def resolve_tree(root_path: str, max_depth: int = MAX_NESTING_DEPTH, _depth: int = 0) -> dict:
    if _depth >= max_depth:
        return {"path": root_path, "children": {}, "truncated": True}

    config = read_config(root_path)
    children = resolve_children(root_path)

    tree = {
        "path": root_path,
        "name": config.name if config else os.path.basename(root_path),
        "config": config,
        "children": {},
    }

    for name, child_info in children.items():
        child_tree = resolve_tree(child_info["path"], max_depth, _depth + 1)
        tree["children"][name] = child_tree

    return tree
