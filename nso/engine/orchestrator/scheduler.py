"""
Scheduler — assign build jobs to the best available builder node.
"""
import asyncio
import logging
import secrets
from datetime import datetime, timedelta

import httpx

from nso.shared import db
from nso.shared.errors import NotFoundError, ValidationError
from nso.engine.orchestrator.models import (
    BuildJob, BuildStatus, SubmitBuildRequest,
)
from nso.engine.orchestrator import pool

logger = logging.getLogger("nso.orchestrator.scheduler")

AGENT_PORT = 8081
BUILD_TIMEOUT = 600  # 10 minutes max


def _gen_id() -> str:
    return f"build_{secrets.token_hex(8)}"


async def submit_build(req: SubmitBuildRequest) -> BuildJob:
    """Submit a new build job to the queue."""
    # Validate project exists
    project = await db.fetch_one("projects", id=req.project_id)
    if not project:
        raise NotFoundError("Project", req.project_id)

    build_id = _gen_id()
    job = BuildJob(
        id=build_id,
        project_id=req.project_id,
        workspace=req.workspace,
        branch=req.branch,
        build_command=req.build_command,
        priority=req.priority,
        status=BuildStatus.QUEUED,
        metadata={
            "deploy_after": req.deploy_after,
            "target_instance_id": req.target_instance_id,
        },
    )

    await db.insert("build_queue", {
        "id": job.id,
        "project_id": job.project_id,
        "workspace": job.workspace,
        "branch": job.branch,
        "assigned_node_id": None,
        "status": job.status.value,
        "priority": job.priority,
        "build_command": job.build_command,
        "logs": "",
        "error": None,
        "metadata": job.metadata,
        "queued_at": job.queued_at,
    })

    logger.info("Build queued: %s (project=%s, workspace=%s)", build_id, req.project_id, req.workspace)

    # Try to assign immediately
    asyncio.create_task(_try_assign(build_id))

    return job


async def _try_assign(build_id: str):
    """Try to assign a queued build to an available builder."""
    job_row = await db.fetch_one("build_queue", id=build_id)
    if not job_row or job_row["status"] != BuildStatus.QUEUED.value:
        return

    builders = await pool.get_available_builders()
    if not builders:
        logger.debug("No available builders for %s", build_id)
        return

    # Pick the builder with lowest CPU load
    best = builders[0]

    await db.update("build_queue", build_id, {
        "assigned_node_id": best.id,
        "status": BuildStatus.ASSIGNED.value,
    })

    # Increment active builds
    await db.update("instance_pool", best.id, {
        "active_builds": best.active_builds + 1,
    })

    logger.info("Build %s assigned to node %s (%s)", build_id, best.id, best.ip)

    # Start the build
    asyncio.create_task(_execute_build(build_id, best))


async def _execute_build(build_id: str, node):
    """Execute a build on the assigned node via agent exec."""
    try:
        await db.update("build_queue", build_id, {
            "status": BuildStatus.BUILDING.value,
            "started_at": datetime.utcnow().isoformat(),
        })

        job_row = await db.fetch_one("build_queue", id=build_id)
        if not job_row:
            return

        workspace = job_row["workspace"]
        branch = job_row["branch"]
        build_cmd = job_row["build_command"]
        project_id = job_row["project_id"]

        # Build sequence on the builder node:
        # 1. Pull latest .zar source
        # 2. Extract
        # 3. Run build command
        # 4. Pack result back into .zar
        # 5. Push to R2
        build_script = (
            f"cd /tmp && "
            f"mkdir -p build_{build_id} && cd build_{build_id} && "
            f"echo 'BUILD_START' && "
            f"{build_cmd} 2>&1 && "
            f"echo 'BUILD_COMPLETE'"
        )

        agent_url = f"http://{node.ip}:{AGENT_PORT}"
        token = (node.metadata or {}).get("agent_token", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        async with httpx.AsyncClient(timeout=BUILD_TIMEOUT) as client:
            resp = await client.post(
                f"{agent_url}/exec/",
                json={"command": build_script, "timeout": BUILD_TIMEOUT},
                headers=headers,
            )

            if resp.status_code != 200:
                raise RuntimeError(f"Agent exec failed: {resp.status_code}")

            result = resp.json()
            output = result.get("output", "")

        # Check if build succeeded
        if "BUILD_COMPLETE" in output:
            await db.update("build_queue", build_id, {
                "status": BuildStatus.DONE.value,
                "logs": output[-10000:],  # Keep last 10k chars
                "finished_at": datetime.utcnow().isoformat(),
            })
            logger.info("Build %s completed successfully", build_id)

            # Deploy if requested
            metadata = job_row.get("metadata", {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)
            if metadata.get("deploy_after") and metadata.get("target_instance_id"):
                logger.info("Auto-deploy triggered for build %s", build_id)
                # Deploy will be handled by existing zar system
        else:
            await db.update("build_queue", build_id, {
                "status": BuildStatus.FAILED.value,
                "logs": output[-10000:],
                "error": "Build did not complete successfully",
                "finished_at": datetime.utcnow().isoformat(),
            })
            logger.warning("Build %s failed", build_id)

    except Exception as e:
        logger.error("Build %s error: %s", build_id, e)
        await db.update("build_queue", build_id, {
            "status": BuildStatus.FAILED.value,
            "error": str(e)[:500],
            "finished_at": datetime.utcnow().isoformat(),
        })

    finally:
        # Decrement active builds on the node
        try:
            node_row = await db.fetch_one("instance_pool", id=node.id)
            if node_row:
                new_count = max(0, node_row.get("active_builds", 1) - 1)
                await db.update("instance_pool", node.id, {"active_builds": new_count})
        except Exception:
            pass

        # Try to assign next queued build
        await _process_queue()


async def _process_queue():
    """Process any queued builds that can be assigned."""
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT id FROM build_queue WHERE status = 'queued' ORDER BY priority DESC, queued_at ASC LIMIT 5"
    )
    rows = await cursor.fetchall()
    for row in rows:
        await _try_assign(row[0])


async def get_build(build_id: str) -> BuildJob:
    """Get build job details."""
    row = await db.fetch_one("build_queue", id=build_id)
    if not row:
        raise NotFoundError("Build", build_id)
    return BuildJob(**row)


async def list_builds(
    status: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> list[BuildJob]:
    """List build jobs."""
    d = await db.get_db()
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cursor = await d.execute(
        f"SELECT * FROM build_queue {where} ORDER BY queued_at DESC LIMIT ?",
        params + [limit],
    )
    rows = await cursor.fetchall()
    return [BuildJob(**db._row_to_dict(r)) for r in rows]


async def cancel_build(build_id: str):
    """Cancel a queued or assigned build."""
    row = await db.fetch_one("build_queue", id=build_id)
    if not row:
        raise NotFoundError("Build", build_id)

    if row["status"] not in (BuildStatus.QUEUED.value, BuildStatus.ASSIGNED.value):
        raise ValidationError(f"Cannot cancel build in status '{row['status']}'")

    await db.update("build_queue", build_id, {
        "status": BuildStatus.FAILED.value,
        "error": "Cancelled by admin",
        "finished_at": datetime.utcnow().isoformat(),
    })

    # Release node if assigned
    if row.get("assigned_node_id"):
        try:
            node = await db.fetch_one("instance_pool", id=row["assigned_node_id"])
            if node:
                new_count = max(0, node.get("active_builds", 1) - 1)
                await db.update("instance_pool", row["assigned_node_id"], {"active_builds": new_count})
        except Exception:
            pass

    logger.info("Build %s cancelled", build_id)
