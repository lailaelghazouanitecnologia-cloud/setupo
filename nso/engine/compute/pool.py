"""
Compute Pool — shared infrastructure for multi-tenant virtualization.

Instead of creating a Vultr VPS per user ($$$), buy large machines
and subdivide them into VMs/containers:

    Vultr Bare Metal (16 vCPU, 64GB, $100/mo)
      ├── VM user_A (2 vCPU, 4GB)  → plan "starter"
      ├── VM user_B (2 vCPU, 4GB)  → plan "starter"
      ├── VM user_C (4 vCPU, 8GB)  → plan "pro"
      └── [free: 8 vCPU, 48GB]

Key concepts:
    Host      — a big machine (Vultr VPS or bare metal) that runs VMs
    VM        — a user's virtual environment inside a host
    Plan      — resource limits (vCPU, RAM, disk, bandwidth)
    Allocator — assigns VMs to hosts based on available capacity
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from nso.shared import db
from nso.shared.events import emit

logger = logging.getLogger("nso.compute.pool")


# ── Migrations ──

POOL_MIGRATIONS = [
    # Hosts — the big machines
    """
    CREATE TABLE IF NOT EXISTS compute_hosts (
        id TEXT PRIMARY KEY,
        provider TEXT DEFAULT 'vultr',
        provider_id TEXT DEFAULT '',
        label TEXT DEFAULT '',
        region TEXT DEFAULT 'ewr',
        plan TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        status TEXT DEFAULT 'provisioning',

        -- Total capacity
        vcpus_total INTEGER DEFAULT 0,
        ram_mb_total INTEGER DEFAULT 0,
        disk_gb_total INTEGER DEFAULT 0,
        bandwidth_gb_total INTEGER DEFAULT 0,

        -- Used (sum of all VMs on this host)
        vcpus_used INTEGER DEFAULT 0,
        ram_mb_used INTEGER DEFAULT 0,
        disk_gb_used INTEGER DEFAULT 0,

        -- Observed metrics
        cpu_percent REAL DEFAULT 0,
        ram_percent REAL DEFAULT 0,
        disk_percent REAL DEFAULT 0,
        last_heartbeat TEXT,

        -- Overcommit ratios (1.0 = no overcommit, 2.0 = 2x overcommit)
        cpu_overcommit REAL DEFAULT 1.5,
        ram_overcommit REAL DEFAULT 1.0,

        agent_token TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        cost_cents_monthly INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_compute_hosts_status ON compute_hosts(status)",
    "CREATE INDEX IF NOT EXISTS idx_compute_hosts_region ON compute_hosts(region)",

    # VMs — user environments inside hosts
    """
    CREATE TABLE IF NOT EXISTS compute_vms (
        id TEXT PRIMARY KEY,
        host_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        instance_id TEXT DEFAULT '',
        plan_id TEXT DEFAULT '',
        label TEXT DEFAULT '',
        status TEXT DEFAULT 'creating',

        -- Allocated resources
        vcpus INTEGER DEFAULT 1,
        ram_mb INTEGER DEFAULT 512,
        disk_gb INTEGER DEFAULT 10,
        bandwidth_gb INTEGER DEFAULT 100,

        -- Network
        ip_internal TEXT DEFAULT '',
        ip_external TEXT DEFAULT '',
        port_start INTEGER DEFAULT 0,
        port_end INTEGER DEFAULT 0,

        -- Runtime
        container_id TEXT DEFAULT '',
        pid INTEGER DEFAULT 0,

        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        started_at TEXT,
        stopped_at TEXT,
        FOREIGN KEY (host_id) REFERENCES compute_hosts(id),
        FOREIGN KEY (project_id) REFERENCES projects(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_compute_vms_host ON compute_vms(host_id)",
    "CREATE INDEX IF NOT EXISTS idx_compute_vms_project ON compute_vms(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_compute_vms_status ON compute_vms(status)",

    # Plans — resource packages
    """
    CREATE TABLE IF NOT EXISTS compute_plans (
        id TEXT PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',

        -- Resources
        vcpus INTEGER DEFAULT 1,
        ram_mb INTEGER DEFAULT 512,
        disk_gb INTEGER DEFAULT 10,
        bandwidth_gb INTEGER DEFAULT 100,

        -- Pricing
        price_cents_monthly INTEGER DEFAULT 0,
        price_cents_hourly INTEGER DEFAULT 0,

        -- Limits
        max_processes INTEGER DEFAULT 5,
        max_domains INTEGER DEFAULT 1,
        max_deployments_day INTEGER DEFAULT 10,

        -- Availability
        available INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_compute_plans_code ON compute_plans(code)",
]

# Default plans to seed
DEFAULT_PLANS = [
    {
        "id": "plan_free",
        "code": "free",
        "name": "Free",
        "description": "For testing and small projects",
        "vcpus": 1, "ram_mb": 512, "disk_gb": 5, "bandwidth_gb": 50,
        "price_cents_monthly": 0, "price_cents_hourly": 0,
        "max_processes": 2, "max_domains": 1, "max_deployments_day": 5,
        "sort_order": 0,
    },
    {
        "id": "plan_starter",
        "code": "starter",
        "name": "Starter",
        "description": "For small apps and APIs",
        "vcpus": 1, "ram_mb": 1024, "disk_gb": 10, "bandwidth_gb": 100,
        "price_cents_monthly": 500, "price_cents_hourly": 1,
        "max_processes": 5, "max_domains": 2, "max_deployments_day": 20,
        "sort_order": 1,
    },
    {
        "id": "plan_pro",
        "code": "pro",
        "name": "Pro",
        "description": "For production workloads",
        "vcpus": 2, "ram_mb": 4096, "disk_gb": 40, "bandwidth_gb": 500,
        "price_cents_monthly": 1500, "price_cents_hourly": 3,
        "max_processes": 10, "max_domains": 5, "max_deployments_day": 50,
        "sort_order": 2,
    },
    {
        "id": "plan_business",
        "code": "business",
        "name": "Business",
        "description": "For high-traffic apps",
        "vcpus": 4, "ram_mb": 8192, "disk_gb": 80, "bandwidth_gb": 1000,
        "price_cents_monthly": 3000, "price_cents_hourly": 5,
        "max_processes": 20, "max_domains": 10, "max_deployments_day": 100,
        "sort_order": 3,
    },
]


# ── Host management ──

async def register_host(
    provider: str,
    provider_id: str,
    ip: str,
    region: str,
    plan: str,
    vcpus: int,
    ram_mb: int,
    disk_gb: int,
    bandwidth_gb: int = 0,
    cost_cents: int = 0,
    label: str = "",
    cpu_overcommit: float = 1.5,
    ram_overcommit: float = 1.0,
    metadata: dict | None = None,
) -> dict:
    """Register a host machine in the pool."""
    host_id = f"host_{secrets.token_hex(8)}"
    agent_token = secrets.token_hex(32)

    row = {
        "id": host_id,
        "provider": provider,
        "provider_id": provider_id,
        "label": label or f"host-{host_id[:8]}",
        "region": region,
        "plan": plan,
        "ip": ip,
        "status": "active",
        "vcpus_total": vcpus,
        "ram_mb_total": ram_mb,
        "disk_gb_total": disk_gb,
        "bandwidth_gb_total": bandwidth_gb,
        "vcpus_used": 0,
        "ram_mb_used": 0,
        "disk_gb_used": 0,
        "cpu_overcommit": cpu_overcommit,
        "ram_overcommit": ram_overcommit,
        "agent_token": agent_token,
        "cost_cents_monthly": cost_cents,
        "metadata": json.dumps(metadata or {}),
    }

    await db.insert("compute_hosts", row)

    await emit("host.registered", {
        "host_id": host_id,
        "ip": ip,
        "vcpus": vcpus,
        "ram_mb": ram_mb,
        "region": region,
    }, source="compute.pool")

    logger.info("Host registered: %s (%s, %d vCPU, %dMB RAM)", host_id, ip, vcpus, ram_mb)
    return {**row, "agent_token": agent_token}


async def list_hosts(status: str = "") -> list[dict]:
    """List all hosts, optionally filtered by status."""
    if status:
        rows = await db.fetch_all("compute_hosts", status=status)
    else:
        conn = await db.get_db()
        cursor = await conn.execute("SELECT * FROM compute_hosts ORDER BY created_at")
        rows = await cursor.fetchall()
    return [_parse_json_row(r) for r in rows]


async def get_host(host_id: str) -> dict | None:
    """Get host details with VM count."""
    row = await db.fetch_one("compute_hosts", id=host_id)
    if not row:
        return None
    host = _parse_json_row(row)

    # Get VMs on this host
    vms = await db.fetch_all("compute_vms", host_id=host_id)
    host["vms"] = [_parse_json_row(v) for v in vms]
    host["vm_count"] = len(vms)

    return host


async def update_host_metrics(host_id: str, cpu: float, ram: float, disk: float):
    """Update observed metrics from host agent."""
    await db.update("compute_hosts", host_id, {
        "cpu_percent": round(cpu, 1),
        "ram_percent": round(ram, 1),
        "disk_percent": round(disk, 1),
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    })


async def set_host_status(host_id: str, status: str):
    """Change host status (active, draining, maintenance, offline)."""
    await db.update("compute_hosts", host_id, {"status": status})
    await emit("host.status_changed", {
        "host_id": host_id,
        "status": status,
    }, source="compute.pool")


# ── VM allocation ──

async def allocate_vm(
    project_id: str,
    plan_code: str,
    region: str = "",
    label: str = "",
    metadata: dict | None = None,
) -> dict:
    """
    Allocate a VM on the best available host.

    1. Look up plan resources
    2. Find host with enough capacity in the requested region
    3. Reserve resources on that host
    4. Create VM record
    """
    # Get plan
    plan = await get_plan(plan_code)
    if not plan:
        raise ValueError(f"Plan '{plan_code}' not found")

    vcpus = plan["vcpus"]
    ram_mb = plan["ram_mb"]
    disk_gb = plan["disk_gb"]
    bandwidth_gb = plan["bandwidth_gb"]

    # Find best host
    host = await _find_best_host(vcpus, ram_mb, disk_gb, region)
    if not host:
        raise ValueError(
            f"No host available with capacity: {vcpus} vCPU, {ram_mb}MB RAM, {disk_gb}GB disk"
            + (f" in region '{region}'" if region else "")
        )

    # Allocate port range for this VM (each VM gets 100 ports)
    port_start = 10000 + (await _count_vms_on_host(host["id"])) * 100
    port_end = port_start + 99

    vm_id = f"vm_{secrets.token_hex(8)}"

    vm = {
        "id": vm_id,
        "host_id": host["id"],
        "project_id": project_id,
        "plan_id": plan["id"],
        "label": label or f"vm-{vm_id[:8]}",
        "status": "creating",
        "vcpus": vcpus,
        "ram_mb": ram_mb,
        "disk_gb": disk_gb,
        "bandwidth_gb": bandwidth_gb,
        "ip_internal": "",
        "ip_external": host["ip"],  # shares host IP, uses port range
        "port_start": port_start,
        "port_end": port_end,
        "metadata": json.dumps(metadata or {}),
    }

    await db.insert("compute_vms", vm)

    # Update host resource usage
    await db.update("compute_hosts", host["id"], {
        "vcpus_used": host["vcpus_used"] + vcpus,
        "ram_mb_used": host["ram_mb_used"] + ram_mb,
        "disk_gb_used": host["disk_gb_used"] + disk_gb,
    })

    await emit("vm.allocated", {
        "vm_id": vm_id,
        "host_id": host["id"],
        "project_id": project_id,
        "plan": plan_code,
        "vcpus": vcpus,
        "ram_mb": ram_mb,
    }, source="compute.pool")

    logger.info(
        "VM %s allocated on host %s (%s): %d vCPU, %dMB RAM, ports %d-%d",
        vm_id, host["id"], host["ip"], vcpus, ram_mb, port_start, port_end,
    )

    return {**vm, "host_ip": host["ip"], "plan_code": plan_code}


async def release_vm(vm_id: str) -> bool:
    """Release a VM and free its resources on the host."""
    vm = await db.fetch_one("compute_vms", id=vm_id)
    if not vm:
        return False

    vm = dict(vm)
    host_id = vm["host_id"]

    # Free resources on host
    host = await db.fetch_one("compute_hosts", id=host_id)
    if host:
        host = dict(host)
        await db.update("compute_hosts", host_id, {
            "vcpus_used": max(0, host["vcpus_used"] - vm["vcpus"]),
            "ram_mb_used": max(0, host["ram_mb_used"] - vm["ram_mb"]),
            "disk_gb_used": max(0, host["disk_gb_used"] - vm["disk_gb"]),
        })

    await db.update("compute_vms", vm_id, {
        "status": "destroyed",
        "stopped_at": datetime.now(timezone.utc).isoformat(),
    })

    await emit("vm.released", {
        "vm_id": vm_id,
        "host_id": host_id,
        "project_id": vm["project_id"],
        "vcpus": vm["vcpus"],
        "ram_mb": vm["ram_mb"],
    }, source="compute.pool")

    logger.info("VM %s released from host %s", vm_id, host_id)
    return True


async def get_vm(vm_id: str) -> dict | None:
    """Get VM details."""
    row = await db.fetch_one("compute_vms", id=vm_id)
    if not row:
        return None
    return _parse_json_row(row)


async def list_vms(project_id: str = "", host_id: str = "") -> list[dict]:
    """List VMs filtered by project or host."""
    if project_id:
        rows = await db.fetch_all("compute_vms", project_id=project_id)
    elif host_id:
        rows = await db.fetch_all("compute_vms", host_id=host_id)
    else:
        conn = await db.get_db()
        cursor = await conn.execute("SELECT * FROM compute_vms WHERE status != 'destroyed' ORDER BY created_at")
        rows = await cursor.fetchall()
    return [_parse_json_row(r) for r in rows]


async def set_vm_status(vm_id: str, status: str):
    """Update VM status."""
    updates: dict[str, Any] = {"status": status}
    if status == "running":
        updates["started_at"] = datetime.now(timezone.utc).isoformat()
    elif status == "stopped":
        updates["stopped_at"] = datetime.now(timezone.utc).isoformat()
    await db.update("compute_vms", vm_id, updates)


# ── Plans ──

async def seed_plans():
    """Insert default plans if they don't exist."""
    for plan in DEFAULT_PLANS:
        existing = await db.fetch_one("compute_plans", code=plan["code"])
        if not existing:
            await db.insert("compute_plans", plan)
    logger.info("Seeded %d compute plans", len(DEFAULT_PLANS))


async def list_plans(available_only: bool = True) -> list[dict]:
    """List compute plans."""
    if available_only:
        rows = await db.fetch_all("compute_plans", available=1)
    else:
        conn = await db.get_db()
        cursor = await conn.execute("SELECT * FROM compute_plans ORDER BY sort_order")
        rows = await cursor.fetchall()
    results = [_parse_json_row(r) for r in rows]
    results.sort(key=lambda x: x.get("sort_order", 0))
    return results


async def get_plan(code: str) -> dict | None:
    """Get a plan by code."""
    row = await db.fetch_one("compute_plans", code=code)
    if not row:
        return None
    return _parse_json_row(row)


async def create_plan(
    code: str,
    name: str,
    vcpus: int,
    ram_mb: int,
    disk_gb: int,
    bandwidth_gb: int = 100,
    price_cents_monthly: int = 0,
    price_cents_hourly: int = 0,
    max_processes: int = 5,
    max_domains: int = 1,
    max_deployments_day: int = 10,
    description: str = "",
) -> dict:
    """Create a custom compute plan."""
    plan_id = f"plan_{secrets.token_hex(6)}"
    row = {
        "id": plan_id,
        "code": code,
        "name": name,
        "description": description,
        "vcpus": vcpus,
        "ram_mb": ram_mb,
        "disk_gb": disk_gb,
        "bandwidth_gb": bandwidth_gb,
        "price_cents_monthly": price_cents_monthly,
        "price_cents_hourly": price_cents_hourly,
        "max_processes": max_processes,
        "max_domains": max_domains,
        "max_deployments_day": max_deployments_day,
        "available": 1,
        "sort_order": 99,
    }
    await db.insert("compute_plans", row)
    return row


# ── Pool overview ──

async def pool_overview() -> dict:
    """Get aggregate pool stats."""
    hosts = await list_hosts()
    vms = await list_vms()

    active_hosts = [h for h in hosts if h.get("status") == "active"]
    active_vms = [v for v in vms if v.get("status") not in ("destroyed", "creating")]

    total_vcpus = sum(h.get("vcpus_total", 0) for h in active_hosts)
    total_ram = sum(h.get("ram_mb_total", 0) for h in active_hosts)
    total_disk = sum(h.get("disk_gb_total", 0) for h in active_hosts)

    used_vcpus = sum(h.get("vcpus_used", 0) for h in active_hosts)
    used_ram = sum(h.get("ram_mb_used", 0) for h in active_hosts)
    used_disk = sum(h.get("disk_gb_used", 0) for h in active_hosts)

    total_cost = sum(h.get("cost_cents_monthly", 0) for h in active_hosts)
    total_revenue = 0
    for vm in active_vms:
        plan = await get_plan(vm.get("plan_id", ""))
        if plan:
            total_revenue += plan.get("price_cents_monthly", 0)

    return {
        "hosts": {
            "total": len(hosts),
            "active": len(active_hosts),
            "regions": list(set(h.get("region", "") for h in active_hosts)),
        },
        "capacity": {
            "vcpus_total": total_vcpus,
            "vcpus_used": used_vcpus,
            "vcpus_free": total_vcpus - used_vcpus,
            "vcpus_utilization": round(used_vcpus / total_vcpus * 100, 1) if total_vcpus else 0,
            "ram_mb_total": total_ram,
            "ram_mb_used": used_ram,
            "ram_mb_free": total_ram - used_ram,
            "ram_utilization": round(used_ram / total_ram * 100, 1) if total_ram else 0,
            "disk_gb_total": total_disk,
            "disk_gb_used": used_disk,
            "disk_gb_free": total_disk - used_disk,
        },
        "vms": {
            "total": len(vms),
            "active": len(active_vms),
            "by_status": _count_by(vms, "status"),
        },
        "economics": {
            "cost_cents_monthly": total_cost,
            "revenue_cents_monthly": total_revenue,
            "margin_cents": total_revenue - total_cost,
            "margin_percent": round((total_revenue - total_cost) / total_cost * 100, 1) if total_cost else 0,
        },
    }


# ── Allocator ──

async def _find_best_host(vcpus: int, ram_mb: int, disk_gb: int, region: str = "") -> dict | None:
    """
    Find the best host for a VM allocation.

    Strategy: bin-packing (best-fit decreasing)
    Pick the host with the LEAST free resources that still fits.
    This maximizes density and delays buying new hosts.
    """
    conn = await db.get_db()

    query = """
        SELECT * FROM compute_hosts
        WHERE status = 'active'
        AND (vcpus_total * cpu_overcommit - vcpus_used) >= ?
        AND (ram_mb_total * ram_overcommit - ram_mb_used) >= ?
        AND (disk_gb_total - disk_gb_used) >= ?
    """
    params: list = [vcpus, ram_mb, disk_gb]

    if region:
        query += " AND region = ?"
        params.append(region)

    query += " ORDER BY (vcpus_total - vcpus_used) ASC, (ram_mb_total - ram_mb_used) ASC"
    query += " LIMIT 1"

    cursor = await conn.execute(query, params)
    row = await cursor.fetchone()

    if row:
        return _parse_json_row(row)
    return None


async def _count_vms_on_host(host_id: str) -> int:
    """Count active VMs on a host."""
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT COUNT(*) as c FROM compute_vms WHERE host_id = ? AND status != 'destroyed'",
        (host_id,),
    )
    row = await cursor.fetchone()
    return row["c"] if row else 0


def _count_by(rows: list[dict], field: str) -> dict[str, int]:
    """Count rows by field value."""
    counts: dict[str, int] = {}
    for row in rows:
        val = str(row.get(field, "unknown"))
        counts[val] = counts.get(val, 0) + 1
    return counts


def _parse_json_row(row) -> dict:
    """Convert DB row to dict, parsing JSON fields."""
    d = dict(row)
    if isinstance(d.get("metadata"), str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass
    return d
