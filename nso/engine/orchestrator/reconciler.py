"""
Reconciler — the central control loop.

Runs every RECONCILE_INTERVAL seconds. For each resource:
1. Read desired spec from DB
2. Observe actual state (via agent /health or provider API)
3. Compare spec vs status
4. If drift detected → take idempotent action to converge
5. Update status in DB

No LLM. No AI. Pure deterministic logic.

Actions are idempotent — running the same reconcile twice
with the same state produces the same result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from nso.shared import db
from nso.engine.orchestrator.state import (
    ConditionStatus,
    InstancePhase,
    InstanceResource,
    InstanceStatus,
    ScalingPolicy,
    SystemSpec,
    WorkspaceResource,
    WorkspaceDeployStatus,
    WorkspaceStatus,
    apply_system_spec,
    get_instance_resource,
    get_system_spec,
    list_all_instance_resources,
    log_reconcile_action,
    set_condition,
    update_instance_status,
)

logger = logging.getLogger("nso.orchestrator.reconciler")

RECONCILE_INTERVAL = 10         # seconds between full sweeps
AGENT_PORT = 8081
AGENT_TIMEOUT = 10
PROVISION_TIMEOUT = 600         # max seconds to wait for VPS creation
SSH_TIMEOUT = 300               # max seconds to wait for SSH

_reconciler_task: asyncio.Task | None = None


# ── Lifecycle ──

async def start_reconciler():
    """Start the reconciler background loop."""
    global _reconciler_task
    if _reconciler_task and not _reconciler_task.done():
        return
    _reconciler_task = asyncio.create_task(_reconcile_loop())
    logger.info("Reconciler started (interval=%ds)", RECONCILE_INTERVAL)


async def stop_reconciler():
    """Stop the reconciler loop."""
    global _reconciler_task
    if _reconciler_task and not _reconciler_task.done():
        _reconciler_task.cancel()
        try:
            await _reconciler_task
        except asyncio.CancelledError:
            pass
    _reconciler_task = None
    logger.info("Reconciler stopped")


# ── Main loop ──

async def _reconcile_loop():
    """Main reconciliation loop."""
    while True:
        try:
            await _reconcile_all()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Reconciler sweep error: %s", e, exc_info=True)
        await asyncio.sleep(RECONCILE_INTERVAL)


async def _reconcile_all():
    """Single reconciliation sweep across all resources."""
    # 1. Reconcile all instances
    instances = await list_all_instance_resources()
    for inst in instances:
        try:
            await _reconcile_instance(inst)
        except Exception as e:
            logger.error("Error reconciling instance %s: %s", inst.id, e)

    # 2. Auto-scaling checks
    projects = set(inst.project_id for inst in instances)
    for pid in projects:
        try:
            await _check_scaling(pid, [i for i in instances if i.project_id == pid])
        except Exception as e:
            logger.error("Error checking scaling for project %s: %s", pid, e)


# ── Instance reconciliation ──

async def _reconcile_instance(inst: InstanceResource):
    """
    Converge a single instance toward its desired spec.

    State machine:
      PENDING → PROVISIONING → INSTALLING → READY → RUNNING
                                                     ↕
                                                   UPDATING
                                                     ↓
      ← ← ← ← ← ← ← ← ERROR ← ← ← ← ← ← ← ← ←

    Each transition is idempotent.
    """
    status = inst.status
    spec = inst.spec
    conditions = status.conditions

    # Deletion requested — destroy
    if inst.deletion_requested:
        await _handle_deletion(inst)
        return

    now = datetime.now(timezone.utc).isoformat()
    changed = False

    # Phase: PENDING — need to provision in cloud provider
    if status.phase == InstancePhase.PENDING:
        # Check if already exists in our instances table
        existing = await db.fetch_one("instances", id=inst.id)
        if existing and existing.get("provider_id"):
            # Already provisioned, advance
            status.provider_id = existing["provider_id"]
            status.ip = existing.get("ip", "")
            status.phase = InstancePhase.INSTALLING if not status.ip else InstancePhase.READY
            set_condition(conditions, "Provisioned", ConditionStatus.TRUE,
                          "AlreadyExists", f"Provider ID: {status.provider_id}", inst.spec_generation)
            changed = True
        else:
            # Need to create — this is handled by compute service
            # We just mark the condition so the API layer can trigger creation
            set_condition(conditions, "Provisioned", ConditionStatus.FALSE,
                          "AwaitingCreation", "Instance needs to be created", inst.spec_generation)

    # Phase: PROVISIONING — waiting for IP from provider
    elif status.phase == InstancePhase.PROVISIONING:
        existing = await db.fetch_one("instances", id=inst.id)
        if existing:
            ip = existing.get("ip", "")
            if ip:
                status.ip = ip
                status.provider_id = existing.get("provider_id", "")
                status.phase = InstancePhase.INSTALLING
                set_condition(conditions, "Provisioned", ConditionStatus.TRUE,
                              "IPAssigned", f"IP: {ip}", inst.spec_generation)
                changed = True
            elif existing.get("state") == "error":
                status.phase = InstancePhase.ERROR
                status.error = existing.get("error", "Provisioning failed")
                set_condition(conditions, "Provisioned", ConditionStatus.FALSE,
                              "ProvisionFailed", status.error, inst.spec_generation)
                changed = True

    # Phase: INSTALLING — waiting for agent to come online
    elif status.phase == InstancePhase.INSTALLING:
        if status.ip:
            agent_up = await _check_agent(status.ip)
            if agent_up:
                status.phase = InstancePhase.READY
                set_condition(conditions, "AgentReady", ConditionStatus.TRUE,
                              "AgentResponding", f"Agent at {status.ip}:{AGENT_PORT}", inst.spec_generation)
                changed = True
            else:
                set_condition(conditions, "AgentReady", ConditionStatus.FALSE,
                              "AgentNotReady", "Waiting for agent to come online", inst.spec_generation)

    # Phase: READY — agent is up, need to deploy workspace + apply process specs
    elif status.phase == InstancePhase.READY:
        if spec.workspace and spec.workspace != status.deployed_workspace:
            # Need to deploy workspace — the deploy engine handles this
            set_condition(conditions, "Deployed", ConditionStatus.FALSE,
                          "DeployNeeded", f"Workspace {spec.workspace} not deployed", inst.spec_generation)

        if spec.processes:
            # Apply process specs to supervisor
            applied = await _apply_supervisor_specs(status.ip, spec.processes, "")
            if applied:
                status.phase = InstancePhase.RUNNING
                set_condition(conditions, "SupervisorReady", ConditionStatus.TRUE,
                              "SpecsApplied", f"{len(spec.processes)} processes", inst.spec_generation)
                changed = True
            else:
                set_condition(conditions, "SupervisorReady", ConditionStatus.FALSE,
                              "ApplyFailed", "Failed to apply process specs", inst.spec_generation)
        elif not spec.workspace:
            # No workspace and no processes — just mark running
            status.phase = InstancePhase.RUNNING
            changed = True

    # Phase: RUNNING — healthy state, check for drift
    elif status.phase == InstancePhase.RUNNING:
        if status.ip:
            health = await _get_agent_health(status.ip)
            if health:
                status.agent_version = health.get("agent_version", "")
                status.system_metrics = health.get("system", {})
                status.process_states = health.get("supervisor", {}).get("processes", {})
                status.converged = health.get("converged", False)
                status.last_reconciled = now

                set_condition(conditions, "Healthy", ConditionStatus.TRUE,
                              "HealthCheckPassed", "Agent responsive", inst.spec_generation)

                # Check version drift — if spec has processes with new version
                sup = health.get("supervisor", {})
                if spec.processes and not sup.get("converged", True):
                    # Supervisor hasn't converged yet, re-apply specs
                    await _apply_supervisor_specs(status.ip, spec.processes, "")

                changed = True
            else:
                set_condition(conditions, "Healthy", ConditionStatus.FALSE,
                              "AgentUnreachable", f"Agent at {status.ip} not responding", inst.spec_generation)
                # Don't immediately transition to ERROR — could be transient
                # Count consecutive failures via condition transitions
                changed = True

    # Phase: ERROR — check if recoverable
    elif status.phase == InstancePhase.ERROR:
        if status.ip:
            agent_up = await _check_agent(status.ip)
            if agent_up:
                logger.info("Instance %s recovered from ERROR", inst.id)
                status.phase = InstancePhase.READY
                status.error = ""
                set_condition(conditions, "Recovered", ConditionStatus.TRUE,
                              "AgentRecovered", "Agent back online", inst.spec_generation)
                changed = True

    # Update DB if anything changed
    if changed:
        status.conditions = conditions
        await update_instance_status(inst.id, status, gen=inst.spec_generation)
        await log_reconcile_action(
            "instance", inst.id, f"phase={status.phase.value}",
            result="ok", detail=f"conditions={len(conditions)}", gen=inst.spec_generation,
        )


# ── Deletion ──

async def _handle_deletion(inst: InstanceResource):
    """Handle instance deletion — destroy provider resources, clean DB."""
    status = inst.status

    if status.phase == InstancePhase.TERMINATED:
        return

    status.phase = InstancePhase.TERMINATING
    await update_instance_status(inst.id, status)

    # Stop supervisor processes first
    if status.ip:
        try:
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                # Tell supervisor to stop all processes
                await client.post(
                    f"http://{status.ip}:{AGENT_PORT}/supervisor/apply",
                    json={"processes": [], "version": ""},
                    headers=_agent_auth(inst),
                )
        except Exception:
            pass

    # The actual VPS destruction is handled by compute service
    # We just mark for deletion and let the existing flow handle it
    existing = await db.fetch_one("instances", id=inst.id)
    if existing and existing.get("state") != "destroying":
        await db.update("instances", inst.id, {"state": "destroying"})

    status.phase = InstancePhase.TERMINATED
    await update_instance_status(inst.id, status)
    await log_reconcile_action("instance", inst.id, "delete", result="ok")


# ── Auto-scaling ──

async def _check_scaling(project_id: str, instances: list[InstanceResource]):
    """Check if project needs to scale up or down based on its scaling policy."""
    sys_spec = await get_system_spec(project_id)
    if not sys_spec:
        return

    policy = sys_spec.scaling
    running = [i for i in instances if i.status.phase == InstancePhase.RUNNING]

    if not running:
        # No running instances — can't scale based on metrics
        if len(instances) < policy.min_instances:
            await log_reconcile_action(
                "scaling", project_id, "scale_up_needed",
                detail=f"Running: 0, min: {policy.min_instances}",
            )
        return

    # Compute average metrics
    avg_cpu = 0.0
    avg_mem = 0.0
    metric_count = 0

    for inst in running:
        metrics = inst.status.system_metrics
        if metrics:
            avg_cpu += metrics.get("cpu_percent", metrics.get("load", [0])[0] if isinstance(metrics.get("load"), list) else 0)
            avg_mem += metrics.get("mem_percent", 0)
            metric_count += 1

    if metric_count > 0:
        avg_cpu /= metric_count
        avg_mem /= metric_count

    current_count = len(running)

    # Scale up check
    if current_count < policy.max_instances:
        if avg_cpu > policy.target_cpu_percent or avg_mem > policy.target_mem_percent:
            await log_reconcile_action(
                "scaling", project_id, "scale_up_recommended",
                detail=f"avg_cpu={avg_cpu:.1f}%, avg_mem={avg_mem:.1f}%, current={current_count}, max={policy.max_instances}",
            )

    # Scale down check
    if current_count > policy.min_instances:
        if avg_cpu < policy.target_cpu_percent * 0.5 and avg_mem < policy.target_mem_percent * 0.5:
            await log_reconcile_action(
                "scaling", project_id, "scale_down_recommended",
                detail=f"avg_cpu={avg_cpu:.1f}%, avg_mem={avg_mem:.1f}%, current={current_count}, min={policy.min_instances}",
            )


# ── Agent communication ──

async def _check_agent(ip: str) -> bool:
    """Quick check if agent is responding."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"http://{ip}:{AGENT_PORT}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _get_agent_health(ip: str) -> dict | None:
    """Get full health status from agent."""
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.get(f"http://{ip}:{AGENT_PORT}/health")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


async def _apply_supervisor_specs(ip: str, processes: list[dict], version: str) -> bool:
    """Push process specs to agent's supervisor."""
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(
                f"http://{ip}:{AGENT_PORT}/supervisor/apply",
                json={"processes": processes, "version": version},
                headers={},  # TODO: agent auth from instance metadata
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Failed to apply supervisor specs to %s: %s", ip, e)
        return False


def _agent_auth(inst: InstanceResource) -> dict:
    """Build auth headers for agent."""
    token = inst.spec.metadata.get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
