"""
Validator service — core validation engine.

Encapsulates validation checks as objects with description, metadata,
optional DB persistence, and execution via typed runners.

Supports:
  - Inline checks (fire-and-forget, no DB)
  - Persisted checks (saved as templates, with history)
  - Batch execution from validate.toml
  - Individual check execution from API/agent
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import tomli

from nso.shared import db
from .runners import run_check, RUNNER_TYPES

logger = logging.getLogger("nso.validator")


# ── Models ──

@dataclass
class Validation:
    """
    A validation check definition.

    Can exist in-memory only (persist=False) or be stored in DB
    as a reusable template (persist=True).
    """
    name: str
    type: str = "http"                        # http | command | tcp | env | metric | custom
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    persist: bool = False
    id: str = ""
    project_id: str = ""
    enabled: bool = True
    created_by: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"val_{uuid.uuid4().hex[:16]}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "config": self.config,
            "metadata": self.metadata,
            "persist": self.persist,
            "project_id": self.project_id,
            "enabled": self.enabled,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Validation:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            type=d.get("type", "http"),
            description=d.get("description", ""),
            config=d.get("config", {}) if isinstance(d.get("config"), dict) else json.loads(d.get("config", "{}")),
            metadata=d.get("metadata", {}) if isinstance(d.get("metadata"), dict) else json.loads(d.get("metadata", "{}")),
            persist=d.get("persist", False),
            project_id=d.get("project_id", ""),
            enabled=bool(d.get("enabled", True)),
            created_by=d.get("created_by", ""),
        )

    @classmethod
    def from_toml_check(cls, check: dict, project_id: str = "") -> Validation:
        """Create from a [[checks]] entry in validate.toml."""
        return cls(
            name=check.get("name", "unnamed"),
            type=check.get("type", "http"),
            description=check.get("description", ""),
            config={k: v for k, v in check.items() if k not in ("name", "type", "description")},
            project_id=project_id,
        )


@dataclass
class ValidationResult:
    """Result of executing a single validation check."""
    validation_id: str = ""
    name: str = ""
    type: str = ""
    status: str = "pending"                    # pass | fail | skip | error
    duration_ms: int = 0
    output: str = ""
    error: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"vr_{uuid.uuid4().hex[:16]}"

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "validation_id": self.validation_id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ValidationRun:
    """A batch execution of multiple checks."""
    id: str = ""
    project_id: str = ""
    workspace: str = ""
    instance_id: str = ""
    trigger: str = "manual"                    # manual | deploy | schedule | agent
    status: str = "running"
    results: list[ValidationResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = f"vrun_{uuid.uuid4().hex[:16]}"

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skip")

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0

    def summary_status(self) -> str:
        if self.failed > 0:
            return "failed"
        if self.skipped == self.total:
            return "skipped"
        return "passed"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "workspace": self.workspace,
            "instance_id": self.instance_id,
            "trigger": self.trigger,
            "status": self.summary_status(),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "results": [r.to_dict() for r in self.results],
        }


# ── Core execution ──

async def execute_validation(
    validation: Validation,
    *,
    context: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    Execute a single validation check.

    Args:
        validation: The check definition.
        context: Runtime context (domain, ip, instance_id, etc.)
            used for template variable substitution in config.
    """
    ctx = context or {}
    result = ValidationResult(
        validation_id=validation.id,
        name=validation.name,
        type=validation.type,
        config=validation.config,
    )

    if not validation.enabled:
        result.status = "skip"
        result.output = "Validation disabled"
        return result

    if validation.type not in RUNNER_TYPES:
        result.status = "skip"
        result.output = f"Unknown validation type: {validation.type}"
        return result

    # Resolve template variables in config (e.g. {{domain}})
    resolved_config = _resolve_config(validation.config, ctx)

    start = time.monotonic()
    try:
        status, output, error = await run_check(validation.type, resolved_config)
        result.status = status
        result.output = output[:4000]
        result.error = error[:2000] if error else ""
    except Exception as e:
        result.status = "error"
        result.error = str(e)[:2000]
        logger.exception("Validation '%s' raised exception", validation.name)
    finally:
        result.duration_ms = int((time.monotonic() - start) * 1000)

    return result


async def execute_batch(
    validations: list[Validation],
    *,
    project_id: str = "",
    workspace: str = "",
    instance_id: str = "",
    trigger: str = "manual",
    context: dict[str, Any] | None = None,
    persist: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ValidationRun:
    """
    Execute a batch of validations and return a run.

    Args:
        validations: List of checks to execute.
        project_id: Project scope.
        workspace: Workspace being validated.
        instance_id: Target instance (for command/tcp checks).
        trigger: What triggered this run.
        context: Template variables for config resolution.
        persist: Whether to save the run and results to DB.
        metadata: Extra metadata for the run.
    """
    run = ValidationRun(
        project_id=project_id,
        workspace=workspace,
        instance_id=instance_id,
        trigger=trigger,
        metadata=metadata or {},
    )

    start = time.monotonic()

    for validation in validations:
        result = await execute_validation(validation, context=context)
        run.results.append(result)

    run.duration_ms = int((time.monotonic() - start) * 1000)
    run.status = run.summary_status()

    # Persist if requested
    if persist:
        await _persist_run(run)

    logger.info(
        "Validation run %s: %d/%d passed (%s) in %dms",
        run.id, run.passed, run.total, run.status, run.duration_ms,
    )

    return run


# ── TOML parsing ──

def parse_validate_toml(content: str, project_id: str = "") -> list[Validation]:
    """Parse a validate.toml file into a list of Validation objects."""
    try:
        data = tomli.loads(content)
    except Exception as e:
        raise ValueError(f"Invalid validate.toml: {e}") from e

    checks = data.get("checks", [])
    if not isinstance(checks, list):
        raise ValueError("validate.toml must have a [[checks]] array")

    validations = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        if not check.get("name"):
            continue
        validations.append(Validation.from_toml_check(check, project_id=project_id))

    return validations


# ── DB operations ──

async def save_validation(validation: Validation) -> dict:
    """Save a validation definition to DB (upsert by project_id + name)."""
    existing = await db.fetch_one(
        "validations", project_id=validation.project_id, name=validation.name,
    )

    row = {
        "id": validation.id,
        "project_id": validation.project_id,
        "name": validation.name,
        "description": validation.description,
        "type": validation.type,
        "config": json.dumps(validation.config),
        "metadata": json.dumps(validation.metadata),
        "enabled": 1 if validation.enabled else 0,
        "created_by": validation.created_by,
    }

    if existing:
        await db.update("validations", existing["id"], {
            k: v for k, v in row.items() if k != "id"
        })
        row["id"] = existing["id"]
    else:
        await db.insert("validations", row)

    return row


async def list_validations(project_id: str) -> list[dict]:
    """List all saved validation definitions for a project."""
    rows = await db.fetch_all("validations", project_id=project_id)
    results = []
    for row in rows:
        d = dict(row)
        for f in ("config", "metadata"):
            if isinstance(d.get(f), str):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    pass
        results.append(d)
    return results


async def get_validation(project_id: str, name: str) -> dict | None:
    """Get a single validation definition by name."""
    row = await db.fetch_one("validations", project_id=project_id, name=name)
    if not row:
        return None
    d = dict(row)
    for f in ("config", "metadata"):
        if isinstance(d.get(f), str):
            try:
                d[f] = json.loads(d[f])
            except Exception:
                pass
    return d


async def delete_validation(project_id: str, name: str) -> bool:
    """Delete a validation definition."""
    row = await db.fetch_one("validations", project_id=project_id, name=name)
    if not row:
        return False
    await db.delete("validations", row["id"])
    return True


async def list_runs(project_id: str, limit: int = 20) -> list[dict]:
    """List recent validation runs for a project."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM validation_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
    )
    rows = await cursor.fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("metadata"), str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except Exception:
                pass
        results.append(d)
    return results


async def get_run(run_id: str) -> dict | None:
    """Get a validation run with its results."""
    run = await db.fetch_one("validation_runs", id=run_id)
    if not run:
        return None

    d = dict(run)
    if isinstance(d.get("metadata"), str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass

    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM validation_results WHERE run_id = ? ORDER BY created_at ASC",
        (run_id,),
    )
    rows = await cursor.fetchall()
    d["results"] = []
    for row in rows:
        r = dict(row)
        for f in ("config", "metadata"):
            if isinstance(r.get(f), str):
                try:
                    r[f] = json.loads(r[f])
                except Exception:
                    pass
        d["results"].append(r)

    return d


# ── Internal ──

async def _persist_run(run: ValidationRun) -> None:
    """Save a run and its results to DB."""
    await db.insert("validation_runs", {
        "id": run.id,
        "project_id": run.project_id,
        "workspace": run.workspace,
        "instance_id": run.instance_id,
        "trigger": run.trigger,
        "status": run.summary_status(),
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "skipped": run.skipped,
        "duration_ms": run.duration_ms,
        "metadata": json.dumps(run.metadata),
        "completed_at": "CURRENT_TIMESTAMP",
    })

    for result in run.results:
        await db.insert("validation_results", {
            "id": result.id,
            "run_id": run.id,
            "validation_id": result.validation_id,
            "name": result.name,
            "type": result.type,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "output": result.output,
            "error": result.error,
            "config": json.dumps(result.config),
            "metadata": json.dumps(result.metadata),
        })


def _resolve_config(config: dict, context: dict) -> dict:
    """Replace {{var}} placeholders in config string values."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str):
            for ctx_key, ctx_val in context.items():
                value = value.replace(f"{{{{{ctx_key}}}}}", str(ctx_val))
            resolved[key] = value
        else:
            resolved[key] = value
    return resolved
