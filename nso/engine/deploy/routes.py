from fastapi import APIRouter, Depends

from nso.shared.models import DeployRequest
from nso.engine.deploy.service import deploy_to_instance
from nso.engine.compute import service as im
from nso.shared.deps import require_project_admin

router = APIRouter()


@router.post("/{instance_id}/deploy", summary="Deploy to instance")
async def deploy(instance_id: str, req: DeployRequest, project_id: str = Depends(require_project_admin)):
    await im.get_instance(project_id, instance_id)
    result = await deploy_to_instance(
        project_id=project_id,
        instance_id=instance_id,
        workspace_name=req.workspace,
        branch=req.branch,
        command=req.command,
    )
    return result
