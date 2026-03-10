"""
NSO Redis Client — distributed state for multi-node clusters.

Provides:
- Connection pool lifecycle (init/close)
- Distributed locking (leader election, mutex)
- Key-value state (scaling cooldowns, RR counters, rate limits)
- Pub/Sub for cross-node event propagation

Falls back to in-memory dicts when Redis is not configured,
so single-node deployments work without Redis.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any

logger = logging.getLogger("nso.redis")

# Node identity — unique per process
NODE_ID = uuid.uuid4().hex[:12]

# ── Redis connection ──

_redis = None
_pubsub_task: asyncio.Task | None = None
_subscribers: dict[str, list] = defaultdict(list)


def _get_redis_url() -> str:
    import os
    return os.environ.get("REDIS_URL", "")


async def init_redis():
    """Initialize Redis connection pool. No-op if REDIS_URL not set."""
    global _redis
    url = _get_redis_url()
    if not url:
        logger.info("REDIS_URL not set — using in-memory fallback (single-node mode)")
        return

    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(url, decode_responses=True, max_connections=20)
        await _redis.ping()
        logger.info("Redis connected: %s", url.split("@")[-1] if "@" in url else url)
    except ImportError:
        logger.warning("redis package not installed — using in-memory fallback")
        _redis = None
    except Exception as e:
        logger.error("Redis connection failed: %s — using in-memory fallback", e)
        _redis = None


async def close_redis():
    """Close Redis connection pool."""
    global _redis, _pubsub_task
    if _pubsub_task and not _pubsub_task.done():
        _pubsub_task.cancel()
        _pubsub_task = None
    if _redis:
        await _redis.aclose()
        _redis = None


def is_available() -> bool:
    """Check if Redis is connected."""
    return _redis is not None


# ── Distributed Key-Value ──

_mem_store: dict[str, Any] = {}
_mem_expiry: dict[str, float] = {}


async def get(key: str) -> str | None:
    """Get a value. Falls back to in-memory."""
    if _redis:
        return await _redis.get(f"nso:{key}")
    # In-memory with expiry check
    if key in _mem_expiry and time.monotonic() > _mem_expiry[key]:
        _mem_store.pop(key, None)
        _mem_expiry.pop(key, None)
        return None
    val = _mem_store.get(key)
    return str(val) if val is not None else None


async def set(key: str, value: str | int | float, ex: int | None = None):
    """Set a value with optional expiry in seconds."""
    if _redis:
        await _redis.set(f"nso:{key}", value, ex=ex)
        return
    _mem_store[key] = value
    if ex:
        _mem_expiry[key] = time.monotonic() + ex


async def incr(key: str) -> int:
    """Atomic increment. Returns new value."""
    if _redis:
        return await _redis.incr(f"nso:{key}")
    val = int(_mem_store.get(key, 0)) + 1
    _mem_store[key] = val
    return val


async def delete(key: str):
    """Delete a key."""
    if _redis:
        await _redis.delete(f"nso:{key}")
        return
    _mem_store.pop(key, None)
    _mem_expiry.pop(key, None)


async def hset(key: str, field: str, value: str):
    """Set a hash field."""
    if _redis:
        await _redis.hset(f"nso:{key}", field, value)
        return
    if key not in _mem_store:
        _mem_store[key] = {}
    _mem_store[key][field] = value


async def hget(key: str, field: str) -> str | None:
    """Get a hash field."""
    if _redis:
        return await _redis.hget(f"nso:{key}", field)
    store = _mem_store.get(key, {})
    return store.get(field) if isinstance(store, dict) else None


# ── Distributed Locking ──

_mem_locks: dict[str, tuple[str, float]] = {}  # lock_name -> (holder, expires_at)


async def try_acquire_lock(lock_name: str, ttl: int = 30) -> bool:
    """Try to acquire a distributed lock. Returns True if acquired.

    Uses Redis SET NX (set if not exists) with TTL for leader election.
    Only one node can hold the lock at a time.
    """
    if _redis:
        result = await _redis.set(
            f"nso:lock:{lock_name}", NODE_ID, nx=True, ex=ttl
        )
        return result is not None

    # In-memory fallback
    now = time.monotonic()
    if lock_name in _mem_locks:
        holder, expires = _mem_locks[lock_name]
        if now < expires and holder != NODE_ID:
            return False
    _mem_locks[lock_name] = (NODE_ID, now + ttl)
    return True


async def renew_lock(lock_name: str, ttl: int = 30) -> bool:
    """Renew a lock's TTL. Only succeeds if we still hold it."""
    if _redis:
        # Lua script: only renew if we still hold the lock
        lua = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('expire', KEYS[1], ARGV[2])
        end
        return 0
        """
        result = await _redis.eval(lua, 1, f"nso:lock:{lock_name}", NODE_ID, ttl)
        return result == 1

    if lock_name in _mem_locks:
        holder, _ = _mem_locks[lock_name]
        if holder == NODE_ID:
            _mem_locks[lock_name] = (NODE_ID, time.monotonic() + ttl)
            return True
    return False


async def release_lock(lock_name: str):
    """Release a lock. Only releases if we hold it."""
    if _redis:
        lua = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await _redis.eval(lua, 1, f"nso:lock:{lock_name}", NODE_ID)
        return

    if lock_name in _mem_locks:
        holder, _ = _mem_locks[lock_name]
        if holder == NODE_ID:
            del _mem_locks[lock_name]


async def get_lock_holder(lock_name: str) -> str | None:
    """Get the current lock holder's node ID."""
    if _redis:
        return await _redis.get(f"nso:lock:{lock_name}")
    if lock_name in _mem_locks:
        holder, expires = _mem_locks[lock_name]
        if time.monotonic() < expires:
            return holder
    return None


# ── Rate Limiting (distributed sliding window) ──

_mem_rate: dict[str, list[float]] = defaultdict(list)


async def check_rate_limit(key: str, max_requests: int, window_secs: int) -> bool:
    """Check if a rate limit is exceeded. Returns True if ALLOWED.

    Uses Redis sorted sets for distributed sliding window.
    """
    if _redis:
        now = time.time()
        pipe_key = f"nso:rate:{key}"
        async with _redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(pipe_key, 0, now - window_secs)
            pipe.zcard(pipe_key)
            pipe.zadd(pipe_key, {str(now): now})
            pipe.expire(pipe_key, window_secs)
            results = await pipe.execute()
        count = results[1]
        if count >= max_requests:
            # Remove the one we just added
            await _redis.zrem(pipe_key, str(now))
            return False
        return True

    # In-memory fallback
    now = time.monotonic()
    bucket = _mem_rate[key]
    cutoff = now - window_secs
    _mem_rate[key] = [t for t in bucket if t > cutoff]
    if len(_mem_rate[key]) >= max_requests:
        return False
    _mem_rate[key].append(now)
    return True


# ── Pub/Sub (cross-node events) ──

async def publish(channel: str, data: dict):
    """Publish an event to all nodes."""
    if _redis:
        await _redis.publish(f"nso:ch:{channel}", json.dumps(data))
        return
    # In-memory: call local subscribers directly
    for handler in _subscribers.get(channel, []):
        try:
            await handler(data)
        except Exception as e:
            logger.error("PubSub handler error on %s: %s", channel, e)


def subscribe(channel: str, handler):
    """Subscribe to events from all nodes. Handler: async def(data: dict)."""
    _subscribers[channel].append(handler)


async def start_subscriber():
    """Start background Redis subscriber for cross-node events."""
    global _pubsub_task
    if not _redis:
        return

    async def _listen():
        pubsub = _redis.pubsub()
        await pubsub.psubscribe("nso:ch:*")
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                channel = channel.removeprefix("nso:ch:")
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                for handler in _subscribers.get(channel, []):
                    try:
                        await handler(data)
                    except Exception as e:
                        logger.error("PubSub handler error on %s: %s", channel, e)
        except asyncio.CancelledError:
            await pubsub.unsubscribe()

    _pubsub_task = asyncio.create_task(_listen())
    logger.info("Redis pub/sub subscriber started (node=%s)", NODE_ID)


# ── Cluster Node Registration ──

async def register_node(role: str = "gateway", metadata: dict | None = None):
    """Register this node in the cluster registry."""
    node_data = json.dumps({
        "node_id": NODE_ID,
        "role": role,
        "registered_at": time.time(),
        **(metadata or {}),
    })
    if _redis:
        await _redis.hset("nso:cluster:nodes", NODE_ID, node_data)
        await _redis.set(f"nso:cluster:heartbeat:{NODE_ID}", "1", ex=60)
    logger.info("Node registered: %s (role=%s)", NODE_ID, role)


async def heartbeat():
    """Update heartbeat TTL."""
    if _redis:
        await _redis.set(f"nso:cluster:heartbeat:{NODE_ID}", "1", ex=60)


async def list_nodes() -> list[dict]:
    """List all registered cluster nodes."""
    if not _redis:
        return [{"node_id": NODE_ID, "role": "gateway", "alive": True}]

    nodes = await _redis.hgetall("nso:cluster:nodes")
    result = []
    for node_id, data_str in nodes.items():
        data = json.loads(data_str)
        alive = await _redis.exists(f"nso:cluster:heartbeat:{node_id}")
        data["alive"] = bool(alive)
        result.append(data)
    return result


async def deregister_node():
    """Remove this node from the cluster."""
    if _redis:
        await _redis.hdel("nso:cluster:nodes", NODE_ID)
        await _redis.delete(f"nso:cluster:heartbeat:{NODE_ID}")
    logger.info("Node deregistered: %s", NODE_ID)
