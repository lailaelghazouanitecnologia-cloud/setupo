from fastapi import APIRouter, Depends

from core.models import DeployRequest
from core.deploy.pipeline import deploy_to_instance
from core.instances import manager as im
from server.deps import require_project

router = APIRouter()


@router.post("/{instance_id}/deploy")
async def deploy(instance_id: str, req: DeployRequest, project_id: str = Depends(require_project)):
    await im.get_instance(project_id, instance_id)
    result = await deploy_to_instance(
        project_id=project_id,
        instance_id=instance_id,
        workspace_name=req.workspace,
        branch=req.branch,
        command=req.command,
    )
    return result
