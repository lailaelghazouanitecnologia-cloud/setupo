"""Instance manager — full lifecycle: create -> provision -> ready -> deploy -> destroy."""
import asyncio
import logging
import secrets
from datetime import datetime
from pathlib import Path

import httpx

from core import db
from core.errors import NotFoundError, ProviderError
from core.models import Instance, InstanceState, InstanceType, CreateInstanceRequest, Provider
from core.providers.vultr import VultrProvider
from core.instances.types import get_cloud_init
from core.instances.provisioner import wait_for_ssh
from server.config import settings

logger = logging.getLogger("mms.instances")


def _gen_id() -> str:
    return f"inst_{secrets.token_hex(8)}"


def _gen_provision_token() -> str:
    """Generate a one-time token for the VPS to report metrics."""
    return f"prov_{secrets.token_urlsafe(32)}"


async def _register_metrics(instance_id: str, provision_token: str):
    """Register instance with mms-metrics service for tracking."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.METRICS_URL}/register",
                json={"instance_id": instance_id, "token": provision_token},
            )
        logger.info("Registered instance %s with mms-metrics", instance_id)
    except Exception as e:
        logger.warning("Could not register with mms-metrics: %s", e)


async def _generate_ssh_key(project_id: str) -> tuple[str, str]:
    """Generate an Ed25519 SSH key pair for this project. Returns (private_path, public_key)."""
    keys_dir = settings.keys_dir(project_id)
    priv = keys_dir / "id_ed25519"
    pub = keys_dir / "id_ed25519.pub"

    if not priv.exists():
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", "", "-C", f"mms-{project_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    public_key = pub.read_text().strip()
    return str(priv), public_key


async def create_instance(project_id: str, req: CreateInstanceRequest) -> Instance:
    """Create a new instance -- provisions VPS and starts background setup."""
    instance_id = _gen_id()
    provision_token = _gen_provision_token()

    instance = Instance(
        id=instance_id,
        project_id=project_id,
        type=req.type,
        provider=Provider.VULTR,
        label=req.label or f"mms-{req.type.value}",
        region=req.region,
        plan=req.plan,
        domain=req.domain,
        workspace=req.workspace,
        state=InstanceState.CREATING,
        created_at=datetime.utcnow(),
    )

    await db.insert("instances", {
        "id": instance.id,
        "project_id": instance.project_id,
        "type": instance.type.value,
        "provider": instance.provider.value,
        "provider_id": "",
        "label": instance.label,
        "region": instance.region,
        "plan": instance.plan,
        "os_id": instance.os_id,
        "ip": None,
        "domain": instance.domain,
        "state": instance.state.value,
        "ssh_key_id": None,
        "workspace": instance.workspace,
        "error": None,
        "metadata": {"provision_token": provision_token},
        "created_at": instance.created_at,
        "ready_at": None,
    })

    # Register with mms-metrics for progress tracking
    await _register_metrics(instance_id, provision_token)

    # Start provisioning in background
    asyncio.create_task(_provision_instance(project_id, instance_id, req, provision_token))

    logger.info("Created instance %s (type=%s) for project %s", instance_id, req.type.value, project_id)
    return instance


async def _provision_instance(project_id: str, instance_id: str, req: CreateInstanceRequest, provision_token: str):
    """Background task: create VPS on Vultr, wait for SSH, mark ready."""
    vultr = VultrProvider()
    try:
        # Generate SSH key
        priv_path, pub_key = await _generate_ssh_key(project_id)

        # Register SSH key with Vultr
        ssh_key = await vultr.create_ssh_key(f"mms-{project_id}", pub_key)
        ssh_key_id = ssh_key.get("id", "")

        await db.update("instances", instance_id, {
            "ssh_key_id": ssh_key_id,
            "state": InstanceState.PROVISIONING.value,
        })

        # Get cloud-init script (now includes metrics callbacks)
        user_data = get_cloud_init(
            req.type.value,
            domain=req.domain,
            instance_id=instance_id,
            provision_token=provision_token,
        )

        # Create the VPS
        vps = await vultr.create_instance(
            region=req.region,
            plan=req.plan,
            os_id=settings.VULTR_DEFAULT_OS,
            label=req.label or f"mms-{req.type.value}-{instance_id[:8]}",
            ssh_key_ids=[ssh_key_id],
            user_data=user_data,
            tag="mms",
        )

        provider_id = vps.get("id", "")
        await db.update("instances", instance_id, {
            "provider_id": provider_id,
        })

        # Poll Vultr until instance has IP and is active
        ip = None
        for _ in range(60):  # Max 5 min
            await asyncio.sleep(5)
            data = await vultr.get_instance(provider_id)
            if not data:
                continue
            status = data.get("status", "")
            power = data.get("power_status", "")
            main_ip = data.get("main_ip", "")
            if status == "active" and power == "running" and main_ip and main_ip != "0.0.0.0":
                ip = main_ip
                break

        if not ip:
            raise ProviderError("vultr", "Instance did not become active within timeout")

        await db.update("instances", instance_id, {"ip": ip})

        # Wait for SSH to be reachable
        ssh_ok = await wait_for_ssh(ip, timeout=180)
        if not ssh_ok:
            raise ProviderError("vultr", f"SSH not reachable at {ip}")

        # Mark as ready
        await db.update("instances", instance_id, {
            "state": InstanceState.READY.value,
            "ready_at": datetime.utcnow().isoformat(),
        })

        logger.info("Instance %s is READY at %s", instance_id, ip)

    except Exception as e:
        logger.error("Provisioning failed for %s: %s", instance_id, e)
        await db.update("instances", instance_id, {
            "state": InstanceState.ERROR.value,
            "error": str(e),
        })
    finally:
        await vultr.close()


async def get_instance(project_id: str, instance_id: str) -> dict:
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst["project_id"] != project_id:
        raise NotFoundError("Instance", instance_id)
    return inst


async def list_instances(project_id: str) -> list[dict]:
    return await db.fetch_all("instances", project_id=project_id)


async def delete_instance(project_id: str, instance_id: str):
    inst = await db.fetch_one("instances", id=instance_id)
    if not inst or inst["project_id"] != project_id:
        raise NotFoundError("Instance", instance_id)

    # Mark as destroying
    await db.update("instances", instance_id, {"state": InstanceState.DESTROYING.value})

    # Destroy on Vultr
    if inst.get("provider_id"):
        vultr = VultrProvider()
        try:
            await vultr.delete_instance(inst["provider_id"])
        except Exception as e:
            logger.error("Failed to destroy VPS %s: %s", inst["provider_id"], e)
        finally:
            await vultr.close()

    # Clean up SSH key on Vultr
    if inst.get("ssh_key_id"):
        vultr = VultrProvider()
        try:
            await vultr.delete_ssh_key(inst["ssh_key_id"])
        except Exception:
            pass
        finally:
            await vultr.close()

    # Clean up metrics
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.delete(f"{settings.METRICS_URL}/status/{instance_id}")
    except Exception:
        pass

    # Delete domain records
    await db.delete_where("domains", instance_id=instance_id)
    await db.delete_where("deploy_logs", instance_id=instance_id)
    await db.delete("instances", instance_id)
    logger.info("Deleted instance %s", instance_id)


async def stop_instance(project_id: str, instance_id: str):
    inst = await get_instance(project_id, instance_id)
    if inst.get("provider_id"):
        vultr = VultrProvider()
        try:
            await vultr.stop_instance(inst["provider_id"])
            await db.update("instances", instance_id, {"state": InstanceState.STOPPED.value})
        finally:
            await vultr.close()


async def start_instance(project_id: str, instance_id: str):
    inst = await get_instance(project_id, instance_id)
    if inst.get("provider_id"):
        vultr = VultrProvider()
        try:
            await vultr.start_instance(inst["provider_id"])
            await db.update("instances", instance_id, {"state": InstanceState.READY.value})
        finally:
            await vultr.close()


async def exec_on_instance(project_id: str, instance_id: str, command: str, timeout: int = 60) -> tuple[str, int]:
    """Execute a command on the instance via SSH."""
    from core.instances.provisioner import run_ssh_command

    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("vultr", "Instance has no IP address")

    keys_dir = settings.keys_dir(project_id)
    priv_key = str(keys_dir / "id_ed25519")

    return await run_ssh_command(ip, command, priv_key, timeout=timeout)
