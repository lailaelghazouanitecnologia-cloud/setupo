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
from nso.shared.events import emit
from nso.engine.orchestrator.state import (
    ConditionStatus,
    InstancePhase,
    InstanceResource,
    InstanceSpec,
    InstanceStatus,
    ScalingPolicy,
    SystemSpec,
    WorkspaceResource,
    WorkspaceDeployStatus,
    WorkspaceStatus,
    apply_instance_spec,
    apply_system_spec,
    get_instance_resource,
    get_system_spec,
    list_all_instance_resources,
    log_reconcile_action,
    request_instance_deletion,
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
        elif existing:
            # Instance row exists but no provider_id — provisioning in progress
            state = existing.get("state", "")
            if state == "error":
                status.phase = InstancePhase.ERROR
                status.error = existing.get("error", "Provisioning failed")
                changed = True
            # else: still creating, wait
        else:
            # No instance row at all — trigger provisioning
            try:
                from nso.shared.models import CreateInstanceRequest, InstanceType
                from nso.engine.compute.service import create_instance

                create_req = CreateInstanceRequest(
                    type=InstanceType(spec.metadata.get("type", "app")),
                    region=spec.region,
                    plan=spec.plan,
                    label=inst.name or f"nso-{inst.id[:12]}",
                    workspace=spec.workspace,
                    domain=spec.domain,
                )
                await create_instance(inst.project_id, create_req)

                status.phase = InstancePhase.PROVISIONING
                set_condition(conditions, "Provisioned", ConditionStatus.FALSE,
                              "Creating", f"Provisioning {spec.plan} in {spec.region}", inst.spec_generation)
                changed = True

                await emit("instance.provisioning", {
                    "instance_id": inst.id,
                    "project_id": inst.project_id,
                    "plan": spec.plan,
                    "region": spec.region,
                }, source="reconciler")

            except Exception as e:
                status.phase = InstancePhase.ERROR
                status.error = f"Failed to create instance: {e}"
                set_condition(conditions, "Provisioned", ConditionStatus.FALSE,
                              "CreateFailed", str(e)[:200], inst.spec_generation)
                changed = True
                await emit("instance.error", {
                    "instance_id": inst.id,
                    "error": str(e)[:200],
                }, source="reconciler")

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
                await emit("instance.ready", {
                    "instance_id": inst.id,
                    "ip": status.ip,
                    "project_id": inst.project_id,
                }, source="reconciler")
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
            applied = await _apply_supervisor_specs(status.ip, spec.processes, "", inst=inst)
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
                    await _apply_supervisor_specs(status.ip, spec.processes, "", inst=inst)

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
                await emit("instance.recovered", {
                    "instance_id": inst.id,
                    "project_id": inst.project_id,
                    "ip": status.ip,
                }, source="reconciler")

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

    # Destroy the VPS via compute service
    existing = await db.fetch_one("instances", id=inst.id)
    if existing:
        provider_id = existing.get("provider_id", "")
        if provider_id and existing.get("state") != "destroying":
            try:
                from nso.engine.compute.service import delete_instance
                await delete_instance(inst.project_id, inst.id)
            except Exception as e:
                logger.error("Failed to destroy VPS for %s: %s", inst.id, e)
                # Mark as orphaned, don't delete the spec record
                await db.update("instances", inst.id, {"state": "orphaned", "error": str(e)[:200]})
                await emit("instance.orphaned", {
                    "instance_id": inst.id,
                    "provider_id": provider_id,
                    "error": str(e)[:200],
                }, source="reconciler")
                return
        elif not provider_id:
            # Never provisioned — just clean up DB
            await db.delete("instances", inst.id)

    status.phase = InstancePhase.TERMINATED
    await update_instance_status(inst.id, status)
    await log_reconcile_action("instance", inst.id, "delete", result="ok")
    await emit("instance.deleted", {
        "instance_id": inst.id,
        "project_id": inst.project_id,
    }, source="reconciler")


# ── Auto-scaling ──

async def _check_scaling(project_id: str, instances: list[InstanceResource]):
    """
    Check if project needs to scale up or down based on its scaling policy.

    Scale up: creates a new instance spec (reconciler will provision it next sweep).
    Scale down: marks the least-loaded instance for deletion.
    Respects cooldown periods to avoid thrashing.
    """
    sys_spec = await get_system_spec(project_id)
    if not sys_spec:
        return

    policy = sys_spec.scaling
    active = [i for i in instances if i.status.phase in (
        InstancePhase.RUNNING, InstancePhase.READY, InstancePhase.PROVISIONING, InstancePhase.INSTALLING,
    )]
    running = [i for i in instances if i.status.phase == InstancePhase.RUNNING]
    current_count = len(active)

    # Enforce minimum instances
    if current_count < policy.min_instances:
        deficit = policy.min_instances - current_count
        for i in range(deficit):
            await _scale_up(project_id, sys_spec, instances, reason=f"Below minimum ({current_count}/{policy.min_instances})")
        return

    # Need running instances with metrics to make scaling decisions
    if not running:
        return

    avg_cpu = 0.0
    avg_mem = 0.0
    metric_count = 0

    for inst in running:
        metrics = inst.status.system_metrics
        if metrics:
            cpu = metrics.get("mem_percent", 0)
            # Handle load array vs direct cpu_percent
            if isinstance(metrics.get("load"), list) and metrics["load"]:
                cpu = metrics["load"][0] * 100  # normalize load average
            elif metrics.get("cpu_percent"):
                cpu = metrics["cpu_percent"]
            avg_cpu += cpu
            avg_mem += metrics.get("mem_percent", 0)
            metric_count += 1

    if metric_count == 0:
        return

    avg_cpu /= metric_count
    avg_mem /= metric_count

    # Check cooldown — don't scale if we recently scaled
    last_scale = await _get_last_scale_time(project_id)
    now = time.time()

    # Scale up check
    if current_count < policy.max_instances:
        if avg_cpu > policy.target_cpu_percent or avg_mem > policy.target_mem_percent:
            if now - last_scale > policy.scale_up_cooldown:
                await _scale_up(
                    project_id, sys_spec, instances,
                    reason=f"High load: cpu={avg_cpu:.1f}%, mem={avg_mem:.1f}%",
                )
                await _set_last_scale_time(project_id, now)

    # Scale down check — only if metrics are well below target
    elif current_count > policy.min_instances:
        if avg_cpu < policy.target_cpu_percent * 0.3 and avg_mem < policy.target_mem_percent * 0.3:
            if now - last_scale > policy.scale_down_cooldown:
                await _scale_down(
                    project_id, running,
                    reason=f"Low load: cpu={avg_cpu:.1f}%, mem={avg_mem:.1f}%",
                )
                await _set_last_scale_time(project_id, now)


async def _scale_up(project_id: str, sys_spec: SystemSpec, existing: list[InstanceResource], reason: str):
    """Create a new instance spec — the reconciler will provision it on next sweep."""
    import secrets as _secrets

    new_id = f"inst_{_secrets.token_hex(8)}"

    # Copy spec from an existing running instance, or use defaults
    template_spec = None
    for inst in existing:
        if inst.status.phase == InstancePhase.RUNNING and inst.spec.processes:
            template_spec = inst.spec
            break

    new_spec = InstanceSpec(
        provider="vultr",
        plan=sys_spec.default_plan,
        region=sys_spec.default_region,
        workspace=template_spec.workspace if template_spec else "",
        processes=template_spec.processes if template_spec else [],
        metadata={"scaled_from": "auto", "reason": reason},
    )

    await apply_instance_spec(project_id, new_id, new_spec, name=f"auto-{new_id[:8]}")

    await log_reconcile_action(
        "scaling", project_id, "scale_up",
        result="ok", detail=f"Created {new_id}: {reason}",
    )
    await emit("scaling.up", {
        "project_id": project_id,
        "instance_id": new_id,
        "reason": reason,
        "plan": new_spec.plan,
    }, source="reconciler")

    logger.info("Scale UP for project %s: %s (%s)", project_id, new_id, reason)


async def _scale_down(project_id: str, running: list[InstanceResource], reason: str):
    """Mark the least-loaded instance for deletion."""
    if not running:
        return

    # Find the instance with lowest load
    lowest = running[0]
    lowest_load = float("inf")

    for inst in running:
        metrics = inst.status.system_metrics
        if metrics:
            load = metrics.get("mem_percent", 0) + (
                metrics.get("cpu_percent", 0) or
                (metrics.get("load", [0])[0] * 100 if isinstance(metrics.get("load"), list) else 0)
            )
            if load < lowest_load:
                lowest_load = load
                lowest = inst

    # Don't delete auto-scaled instances that were just created (extra safety)
    if lowest.status.last_reconciled:
        try:
            created = datetime.fromisoformat(lowest.created_at)
            age = (datetime.now(timezone.utc) - created).total_seconds()
            if age < 600:  # Don't kill instances younger than 10 minutes
                return
        except Exception:
            pass

    await request_instance_deletion(lowest.id)

    await log_reconcile_action(
        "scaling", project_id, "scale_down",
        result="ok", detail=f"Marked {lowest.id} for deletion: {reason}",
    )
    await emit("scaling.down", {
        "project_id": project_id,
        "instance_id": lowest.id,
        "reason": reason,
    }, source="reconciler")

    logger.info("Scale DOWN for project %s: removing %s (%s)", project_id, lowest.id, reason)


# ── Scaling state helpers ──

_last_scale_times: dict[str, float] = {}


async def _get_last_scale_time(project_id: str) -> float:
    """Get the last time a scaling action was taken for a project."""
    return _last_scale_times.get(project_id, 0)


async def _set_last_scale_time(project_id: str, t: float):
    """Record when a scaling action was taken."""
    _last_scale_times[project_id] = t


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


def _agent_auth(inst: InstanceResource) -> dict:
    """Build auth headers for agent."""
    token = inst.spec.metadata.get("agent_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _apply_supervisor_specs(ip: str, processes: list[dict], version: str,
                                  inst: InstanceResource | None = None) -> bool:
    """Push process specs to agent's supervisor."""
    headers = _agent_auth(inst) if inst else {}
    try:
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            resp = await client.post(
                f"http://{ip}:{AGENT_PORT}/supervisor/apply",
                json={"processes": processes, "version": version},
                headers=headers,
            )
            if resp.status_code == 401:
                logger.warning("Agent auth rejected for %s — check agent_token in instance metadata", ip)
            return resp.status_code == 200
    except Exception as e:
        logger.warning("Failed to apply supervisor specs to %s: %s", ip, e)
        return False
