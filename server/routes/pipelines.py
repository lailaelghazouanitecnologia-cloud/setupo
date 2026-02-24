"""Pipeline routes - compose capsules into workflows."""
from fastapi import APIRouter, Request, HTTPException, Depends

from core.models import PipelineRequest
from server.auth import require_token

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/")
async def list_pipelines(request: Request):
    engine = request.app.state.engine
    pipelines = await engine.store.list_pipelines()
    return {"pipelines": pipelines, "count": len(pipelines)}


@router.post("/")
async def run_pipeline(req: PipelineRequest, request: Request):
    engine = request.app.state.engine
    try:
        result = await engine.run_pipeline(name=req.name, steps=req.steps)
        return {"pipeline": result}
    except Exception as e:
        raise HTTPException(400, str(e))
