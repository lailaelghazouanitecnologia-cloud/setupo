"""Instance routes — lifecycle management for VPS/GPU instances."""
from fastapi import APIRouter, Depends

from core.models import CreateInstanceRequest, InstanceExecRequest
from core.instances import manager as im
from server.deps import require_project

router = APIRouter()


@router.post("")
async def create_instance(req: CreateInstanceRequest, project_id: str = Depends(require_project)):
    """Create a new instance. Provisioning happens in the background.

    Poll GET /instances/{id} until state is 'ready'.
    """
    instance = await im.create_instance(project_id, req)
    return {
        "instance": {
            "id": instance.id,
            "type": instance.type.value,
            "state": instance.state.value,
            "region": instance.region,
            "plan": instance.plan,
            "domain": instance.domain,
        },
        "message": "Instance is being provisioned. Poll the instance endpoint until state is 'ready'.",
        "poll_url": f"/api/projects/{project_id}/instances/{instance.id}",
        "next_actions": [
            "Poll status until 'ready'",
            "Then call /deploy to push code from a workspace",
            "Or call /exec to run commands directly",
        ],
    }


@router.get("")
async def list_instances(project_id: str = Depends(require_project)):
    """List all instances for this project."""
    instances = await im.list_instances(project_id)
    return {"instances": instances}


@router.get("/{instance_id}")
async def get_instance(instance_id: str, project_id: str = Depends(require_project)):
    """Get instance details + current state."""
    inst = await im.get_instance(project_id, instance_id)
    return {"instance": inst}


@router.delete("/{instance_id}")
async def delete_instance(instance_id: str, project_id: str = Depends(require_project)):
    """Destroy an instance and clean up all resources."""
    await im.delete_instance(project_id, instance_id)
    return {"deleted": True, "instance_id": instance_id}


@router.post("/{instance_id}/stop")
async def stop_instance(instance_id: str, project_id: str = Depends(require_project)):
    """Stop (halt) a running instance."""
    await im.stop_instance(project_id, instance_id)
    return {"stopped": True}


@router.post("/{instance_id}/start")
async def start_instance(instance_id: str, project_id: str = Depends(require_project)):
    """Start a stopped instance."""
    await im.start_instance(project_id, instance_id)
    return {"started": True}


@router.post("/{instance_id}/exec")
async def exec_on_instance(instance_id: str, req: InstanceExecRequest, project_id: str = Depends(require_project)):
    """Execute a command on the instance via SSH.

    Returns the output and exit code.
    """
    output, exit_code = await im.exec_on_instance(project_id, instance_id, req.command, req.timeout)
    return {
        "output": output,
        "exit_code": exit_code,
    }


@router.get("/{instance_id}/logs")
async def get_instance_logs(instance_id: str, project_id: str = Depends(require_project), tail: int = 100):
    """Get deploy logs for an instance."""
    from core.deploy.pipeline import get_deploy_logs
    # Validate access
    await im.get_instance(project_id, instance_id)
    logs = await get_deploy_logs(instance_id, limit=tail)
    return {"logs": logs}
