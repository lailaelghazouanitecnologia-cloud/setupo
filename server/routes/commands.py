"""Command execution routes."""
from fastapi import APIRouter, Request, HTTPException, Depends

from core.models import ExecRequest, ProtocolRequest
from server.auth import require_token

router = APIRouter(dependencies=[Depends(require_token)])


@router.post("/exec")
async def exec_command(req: ExecRequest, request: Request):
    engine = request.app.state.engine
    try:
        result = await engine.exec_in_capsule(req.capsule_id, req.command, req.timeout)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/protocol")
async def protocol_exec(req: ProtocolRequest, request: Request):
    """Execute MMS protocol code."""
    from protocol.parser import MMSParser
    parser = MMSParser()
    engine = request.app.state.engine

    try:
        instructions = parser.parse(req.code)
        results = []
        for instr in instructions:
            result = await _execute_instruction(engine, instr)
            results.append(result)
        return {"results": results}
    except SyntaxError as e:
        raise HTTPException(400, f"Parse error: {e}")
    except Exception as e:
        raise HTTPException(400, f"Execution error: {e}")


async def _execute_instruction(engine, instr: dict) -> dict:
    action = instr.get("action")

    if action == "capsule.create":
        from core.models import CreateCapsuleRequest, RuntimeType
        req = CreateCapsuleRequest(
            name=instr["name"],
            runtime=RuntimeType(instr.get("runtime", "python")),
            code=instr.get("code"),
            dependencies=instr.get("deps", []),
        )
        return await engine.create_capsule(req)

    elif action == "capsule.start":
        cap = await engine.store.get_capsule_by_name(instr["target"])
        if not cap:
            return {"error": f"Capsule '{instr['target']}' not found"}
        return await engine.start_capsule(cap["id"])

    elif action == "capsule.stop":
        cap = await engine.store.get_capsule_by_name(instr["target"])
        if not cap:
            return {"error": f"Capsule '{instr['target']}' not found"}
        return await engine.stop_capsule(cap["id"])

    elif action == "capsule.exec":
        cap = await engine.store.get_capsule_by_name(instr["target"])
        if not cap:
            return {"error": f"Capsule '{instr['target']}' not found"}
        return await engine.exec_in_capsule(cap["id"], instr["command"])

    elif action == "capsule.destroy":
        cap = await engine.store.get_capsule_by_name(instr["target"])
        if not cap:
            return {"error": f"Capsule '{instr['target']}' not found"}
        return await engine.destroy_capsule(cap["id"])

    elif action == "capsule.list":
        return {"capsules": await engine.store.list_capsules()}

    elif action == "pipeline.run":
        return await engine.run_pipeline(instr["name"], instr["steps"])

    elif action == "env.create":
        from core.models import RuntimeType
        return await engine.create_environment(
            name=instr["name"],
            runtime=RuntimeType(instr.get("runtime", "python")),
            packages=instr.get("packages", []),
        )

    return {"error": f"Unknown action: {action}"}
