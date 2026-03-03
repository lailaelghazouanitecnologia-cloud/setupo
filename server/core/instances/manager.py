import asyncio
import logging
import secrets
from datetime import datetime, timezone

from server.core import db
from server.core.errors import NotFoundError, ProviderError
from server.core.models import Instance, InstanceState, CreateInstanceRequest, Provider
from server.core.providers.vultr import VultrProvider
from server.core.instances.types import get_cloud_init
from server.core.instances.provisioner import wait_for_ssh
from server.config import settings

logger = logging.getLogger("nso.instances")

VPS_POLL_INTERVAL = 5
VPS_POLL_MAX_ATTEMPTS = 60
SSH_WAIT_TIMEOUT = 180
AGENT_LOGIN_TIMEOUT = 10


def _gen_id() -> str:
    return f"inst_{secrets.token_hex(8)}"


async def _generate_ssh_key(project_id: str) -> tuple[str, str]:
    keys_dir = settings.keys_dir(project_id)
    priv = keys_dir / "id_ed25519"
    pub = keys_dir / "id_ed25519.pub"

    if not priv.exists():
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", "", "-C", f"nso-{project_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    return str(priv), pub.read_text().strip()


async def create_instance(project_id: str, req: CreateInstanceRequest) -> Instance:
    instance_id = _gen_id()

    # Store source info in metadata
    metadata: dict = {}
    if req.source_type:
        metadata["source_type"] = req.source_type
    if req.git_url:
        metadata["git_url"] = req.git_url
        metadata["git_branch"] = req.git_branch
    if req.zar_name:
        metadata["zar_name"] = req.zar_name
    if req.app_ready_key:
        metadata["app_ready_key"] = req.app_ready_key

    instance = Instance(
        id=instance_id,
        project_id=project_id,
        type=req.type,
        provider=Provider.VULTR,
        label=req.label or f"nso-{instance_id[:8]}",
        region=req.region,
        plan=req.plan,
        domain=req.domain,
        workspace=req.workspace,
        state=InstanceState.CREATING,
        metadata=metadata,
        created_at=datetime.now(timezone.utc),
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
        "metadata": metadata,
        "created_at": instance.created_at,
        "ready_at": None,
    })

    asyncio.create_task(_provision_instance(project_id, instance_id, req))
    logger.info("Created instance %s (source=%s) for project %s", instance_id, req.source_type or "empty", project_id)
    return instance


async def _resolve_app_ready_key(project_id: str, req: CreateInstanceRequest) -> str:
    """Resolve the R2 key for a frozen app, if available."""
    # Explicit ready key in request
    if req.app_ready_key:
        return req.app_ready_key
    # source_type="ready" with a workspace name — look up the frozen .zar
    if req.source_type == "ready" and req.zar_name:
        return f"{project_id}/_ready/{req.zar_name}/latest.zar"
    return ""


async def _provision_instance(project_id: str, instance_id: str, req: CreateInstanceRequest):
    vultr = VultrProvider()
    try:
        priv_path, pub_key = await _generate_ssh_key(project_id)
        ssh_key = await vultr.create_ssh_key(f"nso-{project_id}", pub_key)
        ssh_key_id = ssh_key.get("id", "")

        await db.update("instances", instance_id, {
            "ssh_key_id": ssh_key_id,
            "state": InstanceState.INSTALLING.value,
        })

        app_ready_key = await _resolve_app_ready_key(project_id, req)

        user_data = get_cloud_init(
            req.type.value,
            domain=req.domain,
            git_url=req.git_url,
            git_branch=req.git_branch,
            app_ready_key=app_ready_key,
        )

        vps = await vultr.create_instance(
            region=req.region,
            plan=req.plan,
            os_id=settings.VULTR_DEFAULT_OS,
            label=req.label or f"nso-{req.type.value}-{instance_id[:8]}",
            ssh_key_ids=[ssh_key_id],
            user_data=user_data,
            tag="nso",
        )

        provider_id = vps.get("id", "")
        await db.update("instances", instance_id, {"provider_id": provider_id})

        ip = None
        for _ in range(VPS_POLL_MAX_ATTEMPTS):
            await asyncio.sleep(VPS_POLL_INTERVAL)
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

        ssh_ok = await wait_for_ssh(ip, timeout=SSH_WAIT_TIMEOUT)
        if not ssh_ok:
            raise ProviderError("vultr", f"SSH not reachable at {ip}")

        await db.update("instances", instance_id, {
            "state": InstanceState.READY.value,
            "ready_at": datetime.now(timezone.utc).isoformat(),
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

    await db.update("instances", instance_id, {"state": InstanceState.DESTROYING.value})

    if inst.get("provider_id"):
        vultr = VultrProvider()
        try:
            await vultr.delete_instance(inst["provider_id"])
        except Exception as e:
            logger.error("Failed to destroy VPS %s: %s", inst["provider_id"], e)
        finally:
            await vultr.close()

    if inst.get("ssh_key_id"):
        vultr = VultrProvider()
        try:
            await vultr.delete_ssh_key(inst["ssh_key_id"])
        except Exception:
            pass
        finally:
            await vultr.close()

    await db.delete_where("domains", instance_id=instance_id)
    await db.delete_where("deploy_logs", instance_id=instance_id)
    await db.delete("instances", instance_id)
    logger.info("Deleted instance %s", instance_id)


async def stop_instance(project_id: str, instance_id: str):
    inst = await get_instance(project_id, instance_id)
    if not inst.get("provider_id"):
        return
    vultr = VultrProvider()
    try:
        await vultr.stop_instance(inst["provider_id"])
        await db.update("instances", instance_id, {"state": InstanceState.STOPPED.value})
    finally:
        await vultr.close()


async def start_instance(project_id: str, instance_id: str):
    inst = await get_instance(project_id, instance_id)
    if not inst.get("provider_id"):
        return
    vultr = VultrProvider()
    try:
        await vultr.start_instance(inst["provider_id"])
        await db.update("instances", instance_id, {"state": InstanceState.READY.value})
    finally:
        await vultr.close()


def _ipv4_client(timeout: float):
    """Create httpx client forced to IPv4 (IPv6 may not be routable between VPSes)."""
    import httpx
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(timeout=timeout, transport=transport)


async def _agent_login(ip: str) -> str:
    import httpx

    email = settings.ADMIN_EMAIL
    password = settings.AGENT_ADMIN_PASSWORD or settings.ADMIN_PASSWORD
    if not password:
        raise ProviderError("agent", "AGENT_ADMIN_PASSWORD not configured")

    async with _ipv4_client(AGENT_LOGIN_TIMEOUT) as client:
        resp = await client.post(
            f"http://{ip}:8081/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code != 200:
            raise ProviderError("agent", f"Agent login failed ({resp.status_code}): {resp.text}")
        return resp.json()["token"]


async def exec_on_instance(project_id: str, instance_id: str, command: str, timeout: int = 60) -> tuple[str, int]:
    import httpx

    inst = await get_instance(project_id, instance_id)
    ip = inst.get("ip")
    if not ip:
        raise ProviderError("vultr", "Instance has no IP address")

    try:
        token = await _agent_login(ip)
        async with _ipv4_client(timeout + 10) as client:
            resp = await client.post(
                f"http://{ip}:8081/exec",
                headers={"Authorization": f"Bearer {token}"},
                json={"command": command, "timeout": timeout},
            )
            if resp.status_code != 200:
                return f"Agent exec error ({resp.status_code}): {resp.text}", 1
            data = resp.json()
            output = data.get("stdout", "") + data.get("stderr", "")
            return output, data.get("exit_code", 0)
    except httpx.ConnectError:
        return f"Cannot connect to agent at {ip}:8081", 1
    except httpx.TimeoutException:
        return "Agent exec timed out", 1
    except Exception as e:
        logger.error("Agent exec error on %s: %s", ip, e)
        return str(e), 1
