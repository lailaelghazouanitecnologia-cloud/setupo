"""
Placement engine — decides which compute nodes to deploy service replicas on.

The algorithm:
1. Filter nodes by strategy (dedicated/shared/auto)
2. Filter by node_selector (role, capabilities, tags, labels)
3. Filter by affinity/anti-affinity
4. Filter by available resources (cpu/mem request vs capacity)
5. Score remaining candidates (best-fit bin packing)
6. If auto-provision enabled and not enough nodes, create new VPS
"""

import logging
from datetime import datetime, timezone

from nso.shared import db
from nso.shared.errors import ValidationError

logger = logging.getLogger("nso.compute.placement")


async def find_placement(
    project_id: str,
    service: dict,
    needed: int,
    exclude_nodes: set[str] | None = None,
) -> list[dict]:
    """
    Find the best nodes for deploying `needed` replicas of a service.
    Returns list of compute_node dicts, ordered by fitness score.
    """
    if needed <= 0:
        return []

    strategy = service.get("placement_strategy", "shared")
    node_selector = service.get("placement_node_selector") or {}
    affinity = service.get("placement_affinity") or []
    anti_affinity_svcs = service.get("placement_anti_affinity_services") or []
    anti_affinity_nodes = service.get("placement_anti_affinity_nodes") or []
    spread = service.get("placement_spread", "")
    exclude = exclude_nodes or set()

    # ── STEP 1: Base pool ──
    if strategy == "dedicated":
        # Only nodes reserved for this service
        all_nodes = await db.fetch_all("compute_nodes", project_id=project_id)
        candidates = [n for n in all_nodes
                      if n.get("reserved_for") == service["id"]
                      and n.get("status") in ("online",)]
    else:
        # Shared/auto: any online, non-reserved (or reserved for this service) node
        all_nodes = await db.fetch_all("compute_nodes", project_id=project_id)
        candidates = [n for n in all_nodes
                      if n.get("status") in ("online",)
                      and (not n.get("reserved_for") or n.get("reserved_for") == service["id"])]

    # ── STEP 2: Node selector ──
    candidates = _filter_by_selector(candidates, node_selector)

    # ── STEP 3: Affinity / Anti-affinity ──
    # Anti-affinity: exclude specific nodes
    if anti_affinity_nodes:
        anti_set = set(anti_affinity_nodes)
        candidates = [n for n in candidates if n["id"] not in anti_set]

    # Anti-affinity: exclude nodes running conflicting services
    if anti_affinity_svcs:
        candidates = await _filter_anti_affinity_services(candidates, anti_affinity_svcs)

    # ── STEP 4: Exclude nodes already running this service (spread) ──
    if spread != "none":
        # Default: spread replicas across nodes (1 per node)
        candidates = [n for n in candidates if n["id"] not in exclude]

    # ── STEP 5: Resource filtering ──
    cpu_req = service.get("cpu_request") or 0
    mem_req = service.get("mem_request_mb") or 0
    if cpu_req > 0 or mem_req > 0:
        candidates = _filter_by_resources(candidates, cpu_req, mem_req)

    # ── STEP 6: Max services limit ──
    candidates = await _filter_by_service_count(candidates)

    # ── STEP 7: Score and sort ──
    scored = _score_candidates(candidates, service, affinity)
    scored.sort(key=lambda x: x[1], reverse=True)

    selected = [node for node, _ in scored[:needed]]

    # ── STEP 8: Auto-provision if needed ──
    deficit = needed - len(selected)
    if deficit > 0 and strategy == "auto":
        auto_nodes = await _auto_provision(project_id, service, deficit)
        selected.extend(auto_nodes)

    return selected


def _filter_by_selector(nodes: list[dict], selector: dict) -> list[dict]:
    """Filter nodes by node_selector criteria."""
    if not selector:
        return nodes

    result = []
    for node in nodes:
        match = True

        # Role filter
        if "role" in selector and node.get("role") != selector["role"]:
            match = False

        # Capabilities: node must have ALL required
        req_caps = selector.get("capabilities", [])
        if req_caps:
            node_caps = set(node.get("capabilities") or [])
            if not set(req_caps).issubset(node_caps):
                match = False

        # Tags: node must have ANY required
        req_tags = selector.get("tags", [])
        if req_tags:
            node_tags = set(node.get("tags") or [])
            if not node_tags & set(req_tags):
                match = False

        # Labels: node must match ALL key=value pairs
        req_labels = selector.get("labels", {})
        if req_labels:
            node_labels = node.get("labels") or {}
            for k, v in req_labels.items():
                if node_labels.get(k) != v:
                    match = False
                    break

        # Min resource requirements
        if selector.get("min_cpu_cores") and node.get("cpu_cores", 0) < selector["min_cpu_cores"]:
            match = False
        if selector.get("min_mem_mb") and node.get("mem_total_mb", 0) < selector["min_mem_mb"]:
            match = False

        if match:
            result.append(node)

    return result


async def _filter_anti_affinity_services(nodes: list[dict], anti_services: list[str]) -> list[dict]:
    """Remove nodes that run any of the anti-affinity services."""
    anti_set = set(anti_services)
    result = []
    for node in nodes:
        # Check service_replicas on this node
        replicas = await db.fetch_all("service_replicas", instance_id=node["id"])
        active_svc_ids = {r["service_id"] for r in replicas
                          if r.get("status") not in ("stopped", "failed", "destroyed")}
        if not active_svc_ids & anti_set:
            result.append(node)
    return result


def _filter_by_resources(nodes: list[dict], cpu_req: float, mem_req: int) -> list[dict]:
    """Filter nodes that have enough available resources."""
    result = []
    for node in nodes:
        buffer_cpu = node["cpu_cores"] * (node.get("buffer_cpu_percent", 10) / 100)
        buffer_mem = node["mem_total_mb"] * (node.get("buffer_mem_percent", 10) / 100)

        cpu_avail = node["cpu_cores"] - buffer_cpu - (node.get("cpu_allocated", 0) or 0)
        mem_avail = node["mem_total_mb"] - buffer_mem - (node.get("mem_allocated_mb", 0) or 0)

        if cpu_avail >= cpu_req and mem_avail >= mem_req:
            result.append(node)
    return result


async def _filter_by_service_count(nodes: list[dict]) -> list[dict]:
    """Filter nodes that haven't hit their max_services limit."""
    result = []
    for node in nodes:
        max_svcs = node.get("max_services", 50)
        replicas = await db.fetch_all("service_replicas", instance_id=node["id"])
        active = sum(1 for r in replicas if r.get("status") not in ("stopped", "failed", "destroyed"))
        if active < max_svcs:
            result.append(node)
    return result


def _score_candidates(
    nodes: list[dict],
    service: dict,
    affinity: list[str],
) -> list[tuple[dict, float]]:
    """Score candidates. Higher = better fit."""
    cpu_req = service.get("cpu_request") or 0
    mem_req = service.get("mem_request_mb") or 0
    affinity_set = set(affinity) if affinity else set()

    scored = []
    for node in nodes:
        score = 0.0

        # Best-fit: prefer nodes where the service fits tightly (less waste)
        if cpu_req > 0 and node["cpu_cores"] > 0:
            buffer_cpu = node["cpu_cores"] * (node.get("buffer_cpu_percent", 10) / 100)
            cpu_avail = node["cpu_cores"] - buffer_cpu - (node.get("cpu_allocated", 0) or 0)
            if cpu_avail > 0:
                cpu_fit = 1 - ((cpu_avail - cpu_req) / node["cpu_cores"])
                score += max(0, cpu_fit) * 40  # 40% weight

        if mem_req > 0 and node["mem_total_mb"] > 0:
            buffer_mem = node["mem_total_mb"] * (node.get("buffer_mem_percent", 10) / 100)
            mem_avail = node["mem_total_mb"] - buffer_mem - (node.get("mem_allocated_mb", 0) or 0)
            if mem_avail > 0:
                mem_fit = 1 - ((mem_avail - mem_req) / node["mem_total_mb"])
                score += max(0, mem_fit) * 30  # 30% weight

        # Prefer less loaded nodes (real metrics)
        cpu_used = node.get("cpu_used_percent", 0) or 0
        score += (1 - cpu_used / 100) * 20  # 20% weight

        # Affinity bonus
        if node["id"] in affinity_set:
            score += 10  # 10% bonus

        scored.append((node, round(score, 2)))

    return scored


async def _auto_provision(project_id: str, service: dict, deficit: int) -> list[dict]:
    """Create new VPS instances for auto-provisioned services."""
    from nso.engine.compute.nodes import register_node, PLAN_RESOURCES

    auto_cfg = service.get("auto_provision") or {}
    if not auto_cfg:
        return []

    plan = auto_cfg.get("plan", "vc2-1c-1gb")
    region = auto_cfg.get("region", "ewr")
    max_nodes = auto_cfg.get("max_nodes", 5)

    # Count existing auto-provisioned nodes for this service
    all_nodes = await db.fetch_all("compute_nodes", project_id=project_id)
    auto_count = sum(1 for n in all_nodes
                     if (n.get("metadata") or {}).get("auto_provisioned_for") == service["id"])

    can_create = min(deficit, max_nodes - auto_count)
    if can_create <= 0:
        logger.warning("Auto-provision limit reached for service %s (%d/%d)",
                       service["id"], auto_count, max_nodes)
        return []

    created = []
    cpu, mem, disk = PLAN_RESOURCES.get(plan, (1, 1024, 25))

    for i in range(can_create):
        try:
            # Create the VPS via compute service
            from nso.shared.models import CreateInstanceRequest
            from nso.engine.compute.service import create_instance

            req = CreateInstanceRequest(
                type="setup",
                label=f"auto-{service.get('name', 'svc')}-{i}",
                region=region,
                plan=plan,
            )
            instance = await create_instance(project_id, req)

            # Register as compute node
            node = await register_node(
                project_id,
                label=f"auto-{service.get('name', 'svc')}-{i}",
                provider="vultr",
                instance_id=instance.id,
                ip="",  # Will be updated when VPS is ready
                role="compute",
                status="provisioning",
                cpu_cores=cpu,
                mem_total_mb=mem,
                disk_total_gb=disk,
                metadata={"auto_provisioned_for": service["id"]},
            )
            created.append(node)
            logger.info("Auto-provisioned node %s for service %s", node["id"], service["id"])
        except Exception as e:
            logger.error("Auto-provision failed: %s", e)

    return created
