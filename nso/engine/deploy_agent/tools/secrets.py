"""
Secrets tools — list and manage project secrets.

Tools:
  - list_secrets: List all project secrets grouped by bucket
  - add_secret: Add or update a project secret
"""

from __future__ import annotations

import json
import re
import uuid
from typing import TYPE_CHECKING

from nso.shared import db
from nso.shared.secrets import classify_secret

if TYPE_CHECKING:
    from nso.engine.deploy_agent.tools import DeployContext


def create_secrets_tools(ctx: DeployContext) -> list[tuple]:
    """Create secret management tools bound to project context."""

    async def list_secrets() -> str:
        """List all secrets for this project grouped by bucket."""
        conn = await db.get_db()
        cursor = await conn.execute(
            "SELECT key, bucket FROM project_secrets WHERE project_id = ? AND scope = 'general' ORDER BY bucket, key",
            (ctx.project_id,),
        )
        rows = await cursor.fetchall()
        grouped: dict[str, list[str]] = {}
        for r in rows:
            row = dict(r)
            b = row.get("bucket", "custom")
            if b not in grouped:
                grouped[b] = []
            grouped[b].append(row["key"])
        return json.dumps({"secrets": grouped, "total": len(rows)})

    async def add_secret(key: str, value: str) -> str:
        """Add or update a project secret. Key must be uppercase with underscores."""
        key = key.strip().upper().replace(" ", "_")
        if not re.match(r"^[A-Z][A-Z0-9_]*$", key):
            return json.dumps({"error": f"Invalid key format: {key}. Must be uppercase letters, digits, underscores."})

        bucket = classify_secret(key)

        existing = await db.fetch_one("project_secrets", project_id=ctx.project_id, key=key, scope="general")
        if existing:
            conn = await db.get_db()
            await conn.execute(
                "UPDATE project_secrets SET value = ?, bucket = ? WHERE id = ?",
                (value, bucket, existing["id"]),
            )
            await conn.commit()
            return json.dumps({"ok": True, "key": key, "bucket": bucket, "action": "updated"})

        await db.insert("project_secrets", {
            "id": f"sec_{uuid.uuid4().hex[:16]}",
            "project_id": ctx.project_id,
            "key": key,
            "value": value,
            "bucket": bucket,
            "scope": "general",
        })
        return json.dumps({"ok": True, "key": key, "bucket": bucket, "action": "created"})

    return [
        (list_secrets, "list_secrets", "List all project secrets grouped by bucket"),
        (add_secret, "add_secret", "Add or update a project secret (environment variable)"),
    ]
