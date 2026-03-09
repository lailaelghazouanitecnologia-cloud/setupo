import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from nso.shared.deps import require_project, require_admin, AuthContext
from nso.shared.errors import NsoError
from nso.engine.infrastructure.database import service

logger = logging.getLogger("nso.infrastructure.database")
router = APIRouter()


class CreateDatabaseRequest(BaseModel):
    name: str
    instance_id: Optional[str] = None  # ignored — DBs run on NSO infra
    engine: str = "postgresql"
    version: str = "16"


class QueryRequest(BaseModel):
    sql: str


# ── CRUD ─────────────────────────────────────────────────────────

@router.post("", status_code=201, summary="Create database")
async def create_database(req: CreateDatabaseRequest, project_id: str = Depends(require_project)):
    try:
        record = await service.create_database(
            project_id, req.name, engine=req.engine, version=req.version,
        )
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return record


@router.get("", summary="List databases")
async def list_databases(project_id: str = Depends(require_project)):
    databases = await service.list_databases(project_id)
    return {"databases": databases, "count": len(databases)}


@router.get("/{database_id}", summary="Get database")
async def get_database(database_id: str, project_id: str = Depends(require_project)):
    try:
        return await service.get_database(project_id, database_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)


@router.delete("/{database_id}", summary="Delete database")
async def delete_database(database_id: str, project_id: str = Depends(require_project)):
    try:
        await service.delete_database(project_id, database_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return {"ok": True}


# ── Query ────────────────────────────────────────────────────────

@router.post("/{database_id}/query", summary="Query database")
async def query_database(database_id: str, req: QueryRequest, project_id: str = Depends(require_project)):
    try:
        result = await service.execute_query(project_id, database_id, req.sql)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
    return result


# ── Status ───────────────────────────────────────────────────────

@router.get("/{database_id}/status", summary="Get database status")
async def database_status(database_id: str, project_id: str = Depends(require_project)):
    try:
        return await service.get_database_status(project_id, database_id)
    except NsoError as e:
        raise HTTPException(e.status_code, e.message)
