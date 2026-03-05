"""
Run cancellation management.

Provides cancellation tokens for graceful run termination.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class RunCancellation:
    """Cancellation token for a single run."""

    run_id: str = ""
    cancelled: bool = False
    cancel_reason: str = ""
    cancelled_at: str | None = None
    cancelled_by: str | None = None
    _event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self, reason: str = "", by: str = "user") -> None:
        self.cancelled = True
        self.cancel_reason = reason
        self.cancelled_at = datetime.now(timezone.utc).isoformat()
        self.cancelled_by = by
        self._event.set()
        logger.info("Run %s cancelled by %s: %s", self.run_id, by, reason)

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled

    async def wait_for_cancel(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


@dataclass
class CancellationManager:
    """Global registry for tracking and cancelling active runs."""

    _runs: dict[str, RunCancellation] = field(default_factory=dict)

    def register(self, run_id: str) -> RunCancellation:
        token = RunCancellation(run_id=run_id)
        self._runs[run_id] = token
        return token

    def is_cancelled(self, run_id: str) -> bool:
        token = self._runs.get(run_id)
        return token.is_cancelled if token else False

    def cancel(self, run_id: str, reason: str = "", by: str = "user") -> bool:
        token = self._runs.get(run_id)
        if not token:
            return False
        token.cancel(reason=reason, by=by)
        return True

    def get_token(self, run_id: str) -> RunCancellation | None:
        return self._runs.get(run_id)

    def cleanup(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def get_active_runs(self) -> list[str]:
        return [rid for rid, token in self._runs.items() if not token.is_cancelled]

    def cancel_all(self, reason: str = "shutdown") -> int:
        count = 0
        for token in self._runs.values():
            if not token.is_cancelled:
                token.cancel(reason=reason, by="system")
                count += 1
        return count


_global_manager = CancellationManager()


def get_cancellation_manager() -> CancellationManager:
    return _global_manager
