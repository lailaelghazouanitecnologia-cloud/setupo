"""Tests for the orchestrator system — pool, scheduler, scaler."""
import pytest
import secrets as _secrets

from server.core import db
from server.core.orchestrator import pool, scheduler, scaler
from server.core.orchestrator.models import (
    NodeRole, NodeStatus, BuildStatus,
    RegisterNodeRequest, UpdateNodeRequest, SubmitBuildRequest,
)


# ── Helpers ────────────────────────────────────────────────

async def _create_project(fresh_db):
    """Create a test project and return its id."""
    from server.auth.keys import generate_api_key
    pid = f"proj_{_secrets.token_hex(8)}"
    key = generate_api_key()
    import hashlib
    await db.insert("projects", {
        "id": pid,
        "name": "test-project",
        "api_key_hash": hashlib.sha256(key.encode()).hexdigest(),
    })
    return pid


async def _create_instance(fresh_db, project_id: str, ip: str = "10.0.0.1"):
    """Create a test instance and return its id."""
    iid = f"inst_{_secrets.token_hex(8)}"
    await db.insert("instances", {
        "id": iid,
        "project_id": project_id,
        "ip": ip,
        "state": "ready",
        "label": f"test-{iid[:8]}",
    })
    return iid


# ── Pool Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_node(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    node = await pool.register_node(RegisterNodeRequest(
        instance_id=iid,
        role=NodeRole.BUILDER,
        ip="10.0.0.1",
    ))

    assert node.id.startswith("node_")
    assert node.instance_id == iid
    assert node.role == NodeRole.BUILDER
    assert node.status == NodeStatus.ACTIVE


@pytest.mark.asyncio
async def test_register_duplicate_fails(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    await pool.register_node(RegisterNodeRequest(instance_id=iid))

    from server.core.errors import ConflictError
    with pytest.raises(ConflictError):
        await pool.register_node(RegisterNodeRequest(instance_id=iid))


@pytest.mark.asyncio
async def test_register_nonexistent_instance_fails(fresh_db):
    from server.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        await pool.register_node(RegisterNodeRequest(instance_id="inst_nonexistent"))


@pytest.mark.asyncio
async def test_update_node(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    node = await pool.register_node(RegisterNodeRequest(instance_id=iid))
    updated = await pool.update_node(node.id, UpdateNodeRequest(
        role=NodeRole.RUNNER,
        status=NodeStatus.DRAINING,
    ))

    assert updated.role == NodeRole.RUNNER
    assert updated.status == NodeStatus.DRAINING


@pytest.mark.asyncio
async def test_remove_node(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    node = await pool.register_node(RegisterNodeRequest(instance_id=iid))
    await pool.remove_node(node.id)

    from server.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        await pool.get_node(node.id)


@pytest.mark.asyncio
async def test_list_nodes_filter(fresh_db):
    pid = await _create_project(fresh_db)
    iid1 = await _create_instance(fresh_db, pid, ip="10.0.0.1")
    iid2 = await _create_instance(fresh_db, pid, ip="10.0.0.2")

    await pool.register_node(RegisterNodeRequest(instance_id=iid1, role=NodeRole.BUILDER))
    await pool.register_node(RegisterNodeRequest(instance_id=iid2, role=NodeRole.RUNNER))

    builders = await pool.list_nodes(role="builder")
    assert len(builders) == 1
    assert builders[0].role == NodeRole.BUILDER

    runners = await pool.list_nodes(role="runner")
    assert len(runners) == 1

    all_nodes = await pool.list_nodes()
    assert len(all_nodes) == 2


@pytest.mark.asyncio
async def test_update_node_metrics(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    node = await pool.register_node(RegisterNodeRequest(instance_id=iid))
    await pool.update_node_metrics(node.id, cpu=45.2, mem=60.1, disk=30.0)

    updated = await pool.get_node(node.id)
    assert updated.cpu_percent == 45.2
    assert updated.mem_percent == 60.1
    assert updated.disk_percent == 30.0
    assert updated.last_heartbeat is not None


@pytest.mark.asyncio
async def test_get_available_builders(fresh_db):
    pid = await _create_project(fresh_db)
    iid1 = await _create_instance(fresh_db, pid, ip="10.0.0.1")
    iid2 = await _create_instance(fresh_db, pid, ip="10.0.0.2")
    iid3 = await _create_instance(fresh_db, pid, ip="10.0.0.3")

    # Builder with low load
    await pool.register_node(RegisterNodeRequest(
        instance_id=iid1, role=NodeRole.BUILDER, ip="10.0.0.1",
    ))
    # Hybrid with high load
    n2 = await pool.register_node(RegisterNodeRequest(
        instance_id=iid2, role=NodeRole.HYBRID, ip="10.0.0.2",
    ))
    # Runner (not a builder)
    await pool.register_node(RegisterNodeRequest(
        instance_id=iid3, role=NodeRole.RUNNER, ip="10.0.0.3",
    ))

    builders = await pool.get_available_builders()
    assert len(builders) == 2  # builder + hybrid, not runner
    # Lowest CPU first
    assert builders[0].cpu_percent <= builders[1].cpu_percent


# ── Scheduler Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_build(fresh_db):
    pid = await _create_project(fresh_db)

    job = await scheduler.submit_build(SubmitBuildRequest(
        project_id=pid,
        workspace="frontend",
        branch="main",
        build_command="npm run build",
    ))

    assert job.id.startswith("build_")
    assert job.project_id == pid
    assert job.workspace == "frontend"
    assert job.status == BuildStatus.QUEUED


@pytest.mark.asyncio
async def test_submit_build_invalid_project(fresh_db):
    from server.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        await scheduler.submit_build(SubmitBuildRequest(
            project_id="proj_nonexistent",
            workspace="test",
        ))


@pytest.mark.asyncio
async def test_list_builds(fresh_db):
    pid = await _create_project(fresh_db)

    await scheduler.submit_build(SubmitBuildRequest(project_id=pid, workspace="ws1"))
    await scheduler.submit_build(SubmitBuildRequest(project_id=pid, workspace="ws2"))

    builds = await scheduler.list_builds()
    assert len(builds) == 2

    builds_filtered = await scheduler.list_builds(project_id=pid)
    assert len(builds_filtered) == 2


@pytest.mark.asyncio
async def test_cancel_build(fresh_db):
    pid = await _create_project(fresh_db)

    job = await scheduler.submit_build(SubmitBuildRequest(project_id=pid, workspace="ws1"))
    await scheduler.cancel_build(job.id)

    cancelled = await scheduler.get_build(job.id)
    assert cancelled.status == BuildStatus.FAILED
    assert cancelled.error == "Cancelled by admin"


# ── Scaler Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_pool_overview_empty(fresh_db):
    overview = await scaler.get_pool_overview()
    assert overview.total_nodes == 0
    assert overview.active_nodes == 0
    assert overview.queued_builds == 0


@pytest.mark.asyncio
async def test_pool_overview_with_nodes(fresh_db):
    pid = await _create_project(fresh_db)
    iid1 = await _create_instance(fresh_db, pid, ip="10.0.0.1")
    iid2 = await _create_instance(fresh_db, pid, ip="10.0.0.2")

    await pool.register_node(RegisterNodeRequest(instance_id=iid1, role=NodeRole.BUILDER))
    await pool.register_node(RegisterNodeRequest(instance_id=iid2, role=NodeRole.RUNNER))

    overview = await scaler.get_pool_overview()
    assert overview.total_nodes == 2
    assert overview.active_nodes == 2
    assert overview.builders == 1
    assert overview.runners == 1


@pytest.mark.asyncio
async def test_recommendations_no_builders(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    await pool.register_node(RegisterNodeRequest(instance_id=iid, role=NodeRole.RUNNER))

    recs = await scaler.get_recommendations()
    critical_recs = [r for r in recs if r["type"] == "config" and r["severity"] == "critical"]
    assert len(critical_recs) == 1
    assert "builder" in critical_recs[0]["reason"].lower() or "builder" in critical_recs[0]["action"].lower()


@pytest.mark.asyncio
async def test_recommendations_high_cpu(fresh_db):
    pid = await _create_project(fresh_db)
    iid = await _create_instance(fresh_db, pid)

    node = await pool.register_node(RegisterNodeRequest(instance_id=iid, role=NodeRole.BUILDER))
    await pool.update_node_metrics(node.id, cpu=92.0, mem=50.0, disk=30.0)

    recs = await scaler.get_recommendations()
    cpu_recs = [r for r in recs if r["type"] == "scale_up" and "CPU" in r["reason"]]
    assert len(cpu_recs) == 1
    assert cpu_recs[0]["severity"] == "critical"
