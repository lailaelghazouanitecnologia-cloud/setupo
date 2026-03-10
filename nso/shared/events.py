"""
Event Bus — lightweight pub/sub for system-wide events.

No external deps. No LLM. Just async callbacks.

Usage:
    from nso.shared.events import emit, on

    # Register handler
    @on("deploy.completed")
    async def handle_deploy(event):
        print(f"Deployed {event['workspace']} to {event['instance_id']}")

    # Or register dynamically
    on("instance.created", my_handler)

    # Emit
    await emit("deploy.completed", {
        "workspace": "api",
        "instance_id": "inst_xxx",
        "version": "1.2.0",
    })

Events are fire-and-forget. Handlers run concurrently.
Failed handlers are logged but don't block the emitter.

Event naming: {resource}.{action}
    instance.created, instance.deleted, instance.error, instance.recovered
    deploy.started, deploy.completed, deploy.failed, deploy.rolled_back
    workspace.updated, workspace.packed, workspace.pushed
    supervisor.process_started, supervisor.process_crashed, supervisor.rollback
    scaling.up_recommended, scaling.down_recommended, scaling.executed
    health.check_passed, health.check_failed
    billing.invoice_created, billing.payment_received
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger("nso.events")

# Type for event handlers
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class Event:
    """An emitted event."""
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    timestamp: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"evt_{secrets.token_hex(8)}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


# ── Registry ──

_handlers: dict[str, list[EventHandler]] = defaultdict(list)
_wildcard_handlers: list[EventHandler] = []
_event_log: list[dict] = []
_max_log_size = 500
_persist_handler: EventHandler | None = None


def on(event_type: str, handler: EventHandler | None = None):
    """
    Register a handler for an event type.

    Can be used as decorator or called directly:
        @on("deploy.completed")
        async def handle(event): ...

        on("deploy.completed", my_handler)

    Use "*" to catch all events.
    """
    def decorator(fn: EventHandler) -> EventHandler:
        if event_type == "*":
            _wildcard_handlers.append(fn)
        else:
            _handlers[event_type].append(fn)
        logger.debug("Handler registered for '%s': %s", event_type, fn.__name__)
        return fn

    if handler is not None:
        # Direct call: on("type", handler)
        if event_type == "*":
            _wildcard_handlers.append(handler)
        else:
            _handlers[event_type].append(handler)
        return handler

    # Decorator usage
    return decorator


def off(event_type: str, handler: EventHandler):
    """Remove a handler."""
    if event_type == "*":
        _wildcard_handlers.remove(handler)
    elif event_type in _handlers:
        _handlers[event_type].remove(handler)


def set_persist_handler(handler: EventHandler):
    """Set a handler that persists events to DB (called for every event)."""
    global _persist_handler
    _persist_handler = handler


async def emit(event_type: str, data: dict[str, Any] | None = None, source: str = "") -> Event:
    """
    Emit an event. All registered handlers run concurrently.

    Returns the Event object.
    """
    event = Event(type=event_type, data=data or {}, source=source)
    event_dict = event.to_dict()

    # In-memory log (ring buffer)
    _event_log.append(event_dict)
    if len(_event_log) > _max_log_size:
        _event_log.pop(0)

    # Publish to Redis for cross-node propagation
    try:
        from nso.shared.redis import publish, is_available
        if is_available():
            await publish("events", event_dict)
    except Exception:
        pass  # Don't block event emission on Redis failure

    # Collect handlers
    handlers = list(_handlers.get(event_type, []))

    # Pattern matching: "deploy.*" handlers match "deploy.completed"
    prefix = event_type.rsplit(".", 1)[0] if "." in event_type else ""
    if prefix:
        handlers.extend(_handlers.get(f"{prefix}.*", []))

    handlers.extend(_wildcard_handlers)

    if _persist_handler:
        handlers.append(_persist_handler)

    if not handlers:
        logger.debug("Event '%s' emitted (no handlers)", event_type)
        return event

    # Run all handlers concurrently, don't let failures propagate
    tasks = []
    for handler in handlers:
        tasks.append(_safe_call(handler, event_dict))

    if tasks:
        await asyncio.gather(*tasks)

    logger.debug("Event '%s' emitted (%d handlers)", event_type, len(handlers))
    return event


async def _safe_call(handler: EventHandler, event: dict):
    """Call a handler, catching and logging any errors."""
    try:
        await handler(event)
    except Exception as e:
        logger.error(
            "Event handler %s failed for '%s': %s",
            handler.__name__, event.get("type", "?"), e,
        )


# ── Querying ──

def recent_events(limit: int = 50, event_type: str = "") -> list[dict]:
    """Get recent events from in-memory log."""
    if event_type:
        filtered = [e for e in _event_log if e["type"] == event_type or e["type"].startswith(event_type)]
        return filtered[-limit:]
    return _event_log[-limit:]


def clear_handlers():
    """Clear all handlers (for testing)."""
    _handlers.clear()
    _wildcard_handlers.clear()


# ── Built-in event persistence to DB ──

async def _db_persist_handler(event: dict):
    """Persist event to billing_events or a generic events table."""
    try:
        from nso.shared import db
        conn = await db.get_db()
        await conn.execute(
            """INSERT INTO system_events (id, type, data, source, created_at)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
            (event["id"], event["type"], json.dumps(event["data"]),
             event.get("source", ""), event["timestamp"]),
        )
        await conn.commit()
    except Exception as e:
        logger.warning("Failed to persist event %s: %s", event.get("type", "?"), e)


EVENTS_MIGRATION = [
    """
    CREATE TABLE IF NOT EXISTS system_events (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        data TEXT DEFAULT '{}',
        source TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(type)",
    "CREATE INDEX IF NOT EXISTS idx_system_events_created ON system_events(created_at)",
]
