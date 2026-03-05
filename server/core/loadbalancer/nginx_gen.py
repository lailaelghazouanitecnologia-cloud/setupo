"""
Nginx config generator — produces upstream blocks from LB pool state.
Can be called via admin API to regenerate and reload nginx.
"""
import logging
from textwrap import dedent

from server.core.loadbalancer.models import LBAlgorithm, BackendStatus
from server.core.loadbalancer import pool_manager

logger = logging.getLogger("nso.lb.nginx")


async def generate_upstream_config() -> str:
    """
    Generate nginx upstream blocks for all active pools.

    Example output:
        upstream lbpool_abc123 {
            least_conn;
            server 1.2.3.4:8000 weight=1;
            server 5.6.7.8:8000 weight=2;
        }
    """
    pools = await pool_manager.list_pools()
    blocks = []

    for pool in pools:
        if not pool.active:
            continue

        healthy = [b for b in pool.backends if b.status == BackendStatus.HEALTHY]
        if not healthy:
            blocks.append(f"# Pool {pool.name} ({pool.id}) — no healthy backends")
            continue

        # Algorithm directive
        algo_directive = ""
        if pool.algorithm == LBAlgorithm.LEAST_CONNECTIONS:
            algo_directive = "    least_conn;"
        elif pool.algorithm == LBAlgorithm.IP_HASH:
            algo_directive = "    ip_hash;"

        # Server lines
        servers = []
        for b in healthy:
            line = f"    server {b.ip}:{b.port}"
            if pool.algorithm == LBAlgorithm.WEIGHTED:
                line += f" weight={b.weight}"
            line += ";"
            servers.append(line)

        # Draining servers (marked as backup)
        draining = [b for b in pool.backends if b.status == BackendStatus.DRAINING]
        for b in draining:
            servers.append(f"    server {b.ip}:{b.port} backup;")

        block = f"upstream {pool.id} {{\n"
        if algo_directive:
            block += algo_directive + "\n"
        block += "\n".join(servers)
        block += "\n}\n"

        blocks.append(block)

    return "\n".join(blocks)


async def generate_location_blocks() -> str:
    """
    Generate nginx location blocks from LB rules.

    Example output:
        location /api/ {
            proxy_pass http://lbpool_abc123;
            proxy_set_header Host $host;
        }
    """
    rules = await pool_manager.list_rules()
    active_rules = [r for r in rules if r.active]

    blocks = []
    for rule in active_rules:
        pool = await pool_manager.get_pool(rule.pool_id)
        if not pool.active:
            continue

        # Location match
        if rule.match_type.value == "exact":
            loc = f"location = {rule.match_value}"
        elif rule.match_type.value == "prefix":
            loc = f"location {rule.match_value}"
        else:
            # Host-based routing handled via server blocks, skip here
            continue

        extra_headers = ""
        for k, v in (rule.headers or {}).items():
            extra_headers += f"        proxy_set_header {k} {v};\n"

        block = dedent(f"""\
        {loc} {{
            proxy_pass http://{pool.id};
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        {extra_headers}    proxy_connect_timeout 5s;
            proxy_read_timeout 60s;
        }}
        """)
        blocks.append(block)

    return "\n".join(blocks)


async def generate_full_config() -> str:
    """Generate complete nginx LB config snippet (upstreams + locations)."""
    upstreams = await generate_upstream_config()
    locations = await generate_location_blocks()

    return f"""\
# ── NSO Load Balancer — auto-generated ──
# Do not edit manually. Regenerate via: POST /api/admin/lb/nginx/generate

# Upstreams
{upstreams}

# Location blocks (include in server {{ }} block)
{locations}
"""
