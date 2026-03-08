"""
Compute node management API routes.

All routes are project-scoped: /api/projects/{project_id}/nodes/...
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from nso.engine.compute import nodes
from nso.engine.compute import placement
from nso.shared.errors import NsoError
from nso.shared.deps import require_project

router = APIRouter()


# ── CRUD ──


@router.get("")
async def list_nodes(
    project_id: str = Depends(require_project),
    status: str = "",
    role: str = "",
):
    """List all compute nodes in a project."""
    try:
        result = await nodes.list_nodes(project_id, status=status, role=role)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"nodes": result}


@router.post("")
async def register_node(
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Register a new compute node."""
    label = body.pop("label", "")
    if not label:
        raise HTTPException(422, "label is required")
    try:
        node = await nodes.register_node(project_id, label, **body)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.get("/{node_id}")
async def get_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Get a compute node by ID."""
    try:
        node = await nodes.get_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.patch("/{node_id}")
async def update_node(
    node_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Update a compute node."""
    try:
        node = await nodes.update_node(project_id, node_id, **body)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.delete("/{node_id}")
async def delete_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Delete a compute node."""
    try:
        await nodes.delete_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"deleted": True}


# ── Operations ──


@router.post("/{node_id}/drain")
async def drain_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Mark node as draining — no new services scheduled."""
    try:
        node = await nodes.drain_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.post("/{node_id}/cordon")
async def cordon_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Mark node as maintenance — no new assignments."""
    try:
        node = await nodes.cordon_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.post("/{node_id}/uncordon")
async def uncordon_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Restore node to online status."""
    try:
        node = await nodes.uncordon_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.post("/{node_id}/reserve")
async def reserve_node(
    node_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Reserve a node for a specific service."""
    service_id = body.get("service_id", "")
    if not service_id:
        raise HTTPException(422, "service_id is required")
    try:
        node = await nodes.reserve_node(project_id, node_id, service_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


@router.post("/{node_id}/release")
async def release_node(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Release a node from dedicated reservation."""
    try:
        node = await nodes.release_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"node": node}


# ── Resources ──


@router.get("/{node_id}/resources")
async def get_resources(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Get available resources on a node."""
    try:
        await nodes.get_node(project_id, node_id)
        resources = await nodes.get_available_resources(node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"resources": resources}


@router.post("/{node_id}/recalculate")
async def recalculate_resources(
    node_id: str,
    project_id: str = Depends(require_project),
):
    """Recalculate allocated resources from active replicas."""
    try:
        await nodes.get_node(project_id, node_id)
        await nodes.recalculate_allocated(node_id)
        resources = await nodes.get_available_resources(node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"resources": resources}


# ── Heartbeat (called by agent) ──


@router.post("/{node_id}/heartbeat")
async def heartbeat(
    node_id: str,
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Receive heartbeat from agent on a node."""
    try:
        await nodes.update_node_metrics(
            node_id,
            cpu=body.get("cpu_used_percent", 0),
            mem=body.get("mem_used_percent", 0),
            disk=body.get("disk_used_percent", 0),
            load=body.get("load_1m", 0),
        )
        # Update status to online if it was offline
        node = await nodes.get_node(project_id, node_id)
        if node["status"] == "offline":
            await nodes.update_node(project_id, node_id, status="online")
            node = await nodes.get_node(project_id, node_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ── Placement preview ──


@router.post("/placement/preview")
async def placement_preview(
    body: dict = Body(...),
    project_id: str = Depends(require_project),
):
    """Preview placement decisions for a service without deploying."""
    from nso.shared import db

    service_id = body.get("service_id")
    replicas = body.get("replicas", 1)

    if not service_id:
        raise HTTPException(422, "service_id is required")

    try:
        svc = await db.fetch_one("service_registry", id=service_id)
        if not svc or svc["project_id"] != project_id:
            raise HTTPException(404, "Service not found")

        candidates = await placement.find_placement(project_id, svc, replicas)
        return {
            "service_id": service_id,
            "requested_replicas": replicas,
            "placed_on": [
                {
                    "node_id": n["id"],
                    "label": n.get("label", ""),
                    "provider": n.get("provider", ""),
                    "cpu_cores": n.get("cpu_cores", 0),
                    "mem_total_mb": n.get("mem_total_mb", 0),
                    "cpu_allocated": n.get("cpu_allocated", 0),
                    "mem_allocated_mb": n.get("mem_allocated_mb", 0),
                    "status": n.get("status", ""),
                }
                for n in candidates
            ],
            "deficit": max(0, replicas - len(candidates)),
        }
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


# ── Auto-register existing instances ──


@router.post("/sync-instances")
async def sync_instances(
    project_id: str = Depends(require_project),
):
    """Auto-register all existing VPS instances as compute nodes."""
    from nso.shared import db

    try:
        instances = await db.fetch_all("instances", project_id=project_id)
        registered = []
        skipped = []
        for inst in instances:
            node = await nodes.auto_register_instance(project_id, inst["id"])
            if node:
                existing = await db.fetch_one("compute_nodes", instance_id=inst["id"])
                if existing and existing["id"] == node["id"]:
                    registered.append(node["id"])
                else:
                    skipped.append(inst["id"])
            else:
                skipped.append(inst["id"])
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)

    return {
        "registered": len(registered),
        "skipped": len(skipped),
        "node_ids": registered,
    }
