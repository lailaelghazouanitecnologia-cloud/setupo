"""
LB Router — selects the best backend for a request using the configured algorithm.

RR counters are stored in Redis for consistent distribution across gateway nodes.
"""
import hashlib
import logging
from typing import Optional

from nso.engine.orchestrator.lb_models import (
    Backend, LBPool, LBAlgorithm, LBRule, RouteMatchType,
)
from nso.engine.orchestrator import pool_manager

logger = logging.getLogger("nso.lb.router")


async def resolve_backend(
    path: str,
    host: str = "",
    client_ip: str = "",
    cookie_sid: str = "",
) -> Optional[Backend]:
    """
    Given a request path/host, find the matching rule → pool → best backend.
    Returns None if no rule matches or no healthy backend available.
    """
    rules = await pool_manager.list_rules()
    active_rules = [r for r in rules if r.active]

    matched_rule = _match_rule(active_rules, path, host)
    if not matched_rule:
        return None

    pool = await pool_manager.get_pool(matched_rule.pool_id)
    if not pool.active:
        return None

    backends = await pool_manager.get_healthy_backends(pool.id)
    if not backends:
        logger.warning("No healthy backends in pool %s", pool.id)
        return None

    backend = _select_backend(pool, backends, client_ip, cookie_sid)

    if backend:
        # Increment stats
        from nso.shared import db
        await db.update("lb_backends", backend.id, {
            "active_connections": backend.active_connections + 1,
            "total_requests": backend.total_requests + 1,
        })

    return backend


def _match_rule(rules: list[LBRule], path: str, host: str) -> Optional[LBRule]:
    """Find the first matching rule (sorted by priority DESC)."""
    for rule in rules:
        if rule.match_type == RouteMatchType.PREFIX:
            if path.startswith(rule.match_value):
                return rule
        elif rule.match_type == RouteMatchType.EXACT:
            if path == rule.match_value:
                return rule
        elif rule.match_type == RouteMatchType.HOST:
            if host == rule.match_value or host.split(":")[0] == rule.match_value:
                return rule
    return None


def _select_backend(
    pool: LBPool,
    backends: list[Backend],
    client_ip: str = "",
    cookie_sid: str = "",
) -> Optional[Backend]:
    """Pick a backend based on the pool's algorithm."""
    if not backends:
        return None

    algo = pool.algorithm

    if algo == LBAlgorithm.ROUND_ROBIN:
        return await _round_robin(pool.id, backends)

    elif algo == LBAlgorithm.LEAST_CONNECTIONS:
        return min(backends, key=lambda b: b.active_connections)

    elif algo == LBAlgorithm.WEIGHTED:
        return await _weighted_select(pool.id, backends)

    elif algo == LBAlgorithm.IP_HASH:
        if not client_ip:
            return await _round_robin(pool.id, backends)
        idx = int(hashlib.md5(client_ip.encode()).hexdigest(), 16) % len(backends)
        return backends[idx]

    elif algo == LBAlgorithm.LEAST_LOAD:
        # Use CPU from orchestrator metrics if available
        return min(backends, key=lambda b: b.active_connections)

    return backends[0]


async def _round_robin(pool_id: str, backends: list[Backend]) -> Backend:
    from nso.shared.redis import incr
    idx = await incr(f"rr:{pool_id}")
    return backends[(idx - 1) % len(backends)]


async def _weighted_select(pool_id: str, backends: list[Backend]) -> Backend:
    """Weighted round-robin: backends with higher weight get more requests."""
    weighted = []
    for b in backends:
        weighted.extend([b] * max(1, b.weight))

    from nso.shared.redis import incr
    idx = await incr(f"rr:w:{pool_id}")
    return weighted[(idx - 1) % len(weighted)]
