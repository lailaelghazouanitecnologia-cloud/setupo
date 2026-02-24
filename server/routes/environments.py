"""Environment management routes."""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel

from core.models import RuntimeType
from server.auth import require_token

router = APIRouter(dependencies=[Depends(require_token)])


class CreateEnvRequest(BaseModel):
    name: str
    runtime: RuntimeType = RuntimeType.PYTHON
    version: str = ""
    packages: list[str] = []


@router.get("/")
async def list_environments(request: Request):
    engine = request.app.state.engine
    envs = await engine.list_environments()
    return {"environments": envs, "count": len(envs)}


@router.post("/")
async def create_environment(req: CreateEnvRequest, request: Request):
    engine = request.app.state.engine
    env = await engine.create_environment(
        name=req.name,
        runtime=req.runtime,
        version=req.version,
        packages=req.packages,
    )
    return {"environment": env}


@router.delete("/{env_id}")
async def destroy_environment(env_id: str, request: Request):
    engine = request.app.state.engine
    try:
        return await engine.destroy_environment(env_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
