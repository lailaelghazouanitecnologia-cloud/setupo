"""Command execution and SSH routes."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ExecRequest(BaseModel):
    instance_id: str
    command: str


class SSHExecRequest(BaseModel):
    host: str
    command: str
    key_path: str | None = None


class ProtocolExecRequest(BaseModel):
    code: str
    target: str | None = None


@router.post("/exec")
async def exec_command(req: ExecRequest, request: Request):
    """Execute a command on a specific VM/MicroVM."""
    orch = request.app.state.orchestrator
    try:
        result = await orch.exec_on_instance(req.instance_id, req.command)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/ssh")
async def ssh_exec(req: SSHExecRequest, request: Request):
    """Execute a command on an external host via SSH."""
    orch = request.app.state.orchestrator
    result = await orch.ssh_to_external(
        host=req.host,
        command=req.command,
        key_path=req.key_path,
    )
    return {"result": result}


@router.post("/protocol")
async def protocol_exec(req: ProtocolExecRequest, request: Request):
    """Execute setupo protocol commands."""
    from protocol.parser import SetupoParser
    parser = SetupoParser()
    orch = request.app.state.orchestrator

    try:
        instructions = parser.parse(req.code)
        results = []
        for instr in instructions:
            result = await _execute_instruction(orch, instr, req.target)
            results.append(result)
        return {"results": results}
    except Exception as e:
        raise HTTPException(400, f"Protocol error: {e}")


async def _execute_instruction(orch, instruction: dict, default_target: str = None):
    """Execute a single parsed protocol instruction."""
    action = instruction.get("action")
    target = instruction.get("target", default_target)

    if action == "create":
        vm_type = instruction.get("type", "microvm")
        name = instruction.get("name", "unnamed")
        if vm_type == "vm":
            inst = await orch.create_vm(name=name, **instruction.get("params", {}))
        else:
            inst = await orch.create_microvm(name=name, **instruction.get("params", {}))
        return {"action": "created", "instance": inst.to_dict()}

    elif action == "exec":
        if not target:
            return {"error": "No target specified for exec"}
        return await orch.exec_on_instance(target, instruction.get("command", ""))

    elif action == "destroy":
        if not target:
            return {"error": "No target specified for destroy"}
        return await orch.destroy_instance(target)

    elif action == "capsule":
        capsule_name = instruction.get("name")
        if not target:
            return {"error": "No target specified for capsule"}
        result = await orch.exec_on_instance(
            target, f"cd /opt/capsules && ./install.sh {capsule_name}"
        )
        return {"action": "capsule_loaded", "capsule": capsule_name, "result": result}

    return {"error": f"Unknown action: {action}"}
