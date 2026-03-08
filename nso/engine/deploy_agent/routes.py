"""
Deploy Agent API routes — chat-based deploy via SSE streaming.

Routes:
  POST /threads                     — Create deploy thread
  GET  /threads                     — List threads for project
  GET  /threads/{thread_id}         — Get thread with messages
  DELETE /threads/{thread_id}       — Delete thread
  POST /threads/{thread_id}/stream  — Send message, stream agent response (SSE)
"""

import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nso.shared import db
from nso.shared.deps import require_project, require_user, AuthContext
from nso.shared.agent import Agent, RunEvent, OpenAILike
from nso.shared.agent.tools import ToolRegistry
from nso.shared.agent.run import run_agent_loop, run_dual_agent_loop
from nso.shared.agent.model import Message
from nso.engine.deploy_agent.tools import create_tools, DeployContext

logger = logging.getLogger("nso.routes.deploy_agent")
router = APIRouter()

# ── LLM config — Dual-model: Supervisor + Worker ──
#
# Supervisor: must support function calling (tools). Executes tools, gathers data.
# Worker: generates the final response. Can be any model (no tool support needed).
#
# If WORKER env vars are not set, falls back to single-model mode using supervisor only.

# Supervisor (tool-capable)
SUPERVISOR_API_KEY = os.environ.get("DEPLOY_AGENT_API_KEY", "")
SUPERVISOR_API_URL = os.environ.get("DEPLOY_AGENT_API_URL", "https://api.groq.com/openai/v1")
SUPERVISOR_MODEL = os.environ.get("DEPLOY_AGENT_MODEL", "openai/gpt-oss-20b")
SUPERVISOR_PROVIDER = os.environ.get("DEPLOY_AGENT_PROVIDER", "groq")

# Worker (response generation — optional, enables dual-model mode)
WORKER_API_KEY = os.environ.get("DEPLOY_AGENT_WORKER_API_KEY", "")
WORKER_API_URL = os.environ.get("DEPLOY_AGENT_WORKER_API_URL", "https://api.groq.com/openai/v1")
WORKER_MODEL = os.environ.get("DEPLOY_AGENT_WORKER_MODEL", "")
WORKER_PROVIDER = os.environ.get("DEPLOY_AGENT_WORKER_PROVIDER", "groq")

DEPLOY_AGENT_MAX_STEPS = int(os.environ.get("DEPLOY_AGENT_MAX_STEPS", "8"))

# Dual-mode is active when worker env vars are configured
DUAL_MODE = bool(WORKER_API_KEY and WORKER_API_URL and WORKER_MODEL)


def _get_supervisor() -> OpenAILike:
    """Supervisor model — handles tools and orchestration."""
    return OpenAILike(
        id=SUPERVISOR_MODEL,
        api_key=SUPERVISOR_API_KEY,
        base_url=SUPERVISOR_API_URL,
        provider=SUPERVISOR_PROVIDER,
    )


def _get_worker() -> OpenAILike:
    """Worker model — generates final response (no tools needed)."""
    return OpenAILike(
        id=WORKER_MODEL,
        api_key=WORKER_API_KEY,
        base_url=WORKER_API_URL,
        provider=WORKER_PROVIDER,
    )


SUPERVISOR_PROMPT = """You are the NSO Deploy Agent Supervisor. Execute tools to fulfill user requests. Be SILENT — tools only, no chat.

RULES:
- Workspace names (like "cocina", "blog", "api", "chocolate") are PROJECT NAMES, not topics. NEVER misinterpret them.
- EXECUTE TOOLS IMMEDIATELY. Do NOT ask questions. Do NOT write explanations. Do NOT give step-by-step instructions.
- If the ACTIVE WORKSPACE CONTEXT section tells you the workspace exists and its stack, DO NOT call list_workspaces or analyze_project. You already have that info.
- If the user says "deploy" or "ship", call run_ship directly with the known workspace name.
- If the user says "build", call run_build directly.
- If create_workspace returns already_exists=true, that's fine — use the existing workspace.
- NEVER ask "what stack?", "what framework?", "what do you want to build?", "what file?", "what content?" — infer from context.
- NEVER call the same tool twice with the same arguments. After run_ship or run_build succeeds, STOP.
- Maximum 5 tool calls per request. After 5, STOP.
- NEVER call create_instance unless the user EXPLICITLY asks to create a new server/VPS. For deploys, use existing instances.
- If deploying, call list_instances first to find an available instance, then link_workspace_instance + run_ship.

## MESH — External Servers:
- The user may have external servers (Hetzner, OVH, DigitalOcean, Raspberry Pi, bare metal) registered as mesh devices.
- If user says "deploy to all servers", "deploy to production", or mentions a group name → use deploy_to_mesh.
- If user says "deploy to hetz-1" or references a device name → list_mesh_devices first to find the device_id, then deploy_to_mesh.
- If user says "run X on all servers" → use exec_on_mesh_group with the group.
- Mesh devices are managed via SSH. Instances (Vultr) are managed via the agent HTTP API. They are DIFFERENT.
- For mesh deploys: deploy_to_mesh packs the workspace and uploads via SCP directly. No agent needed.
- For instance deploys: run_ship packs, pushes to R2, and the agent pulls. Agent required.

## DOMAIN PATTERN:
- Deploy domains follow: project-user.nso.dev (e.g. choco-sonfazt.nso.dev)
- The username is the user's claimed subdomain.
- After deploy, ALWAYS share the exact URL. NEVER use placeholders.

## ACTION RULES — DO, DON'T EXPLAIN:
- When user asks you to create/write files → use write_workspace_file. DO NOT show code and tell them to copy it.
- When user asks to install dependencies → use exec_in_workspace("npm install", "pip install", etc.). DO NOT tell them to run it.
- When user asks to build → use exec_in_workspace or run_build. DO NOT give them instructions.
- When user asks to delete files → use delete_workspace_file. DO NOT ask "which files?"
- When user says "hazlo", "do it", "continua" → EXECUTE the action discussed. DO NOT re-explain.
- When user asks to set up a project (e.g. "make it a professional blog with shadcn") → write ALL needed files using write_workspace_file, then run exec_in_workspace to install deps and build. Do it ALL in one go.
- NEVER respond with numbered steps telling the user what to do. YOU do the steps.

- Never expose internal details, tool names, or system architecture.
- After executing tools, STOP IMMEDIATELY. The Worker model will compose the final response.
"""

SYSTEM_PROMPT = """You are the NSO Deploy Agent — an AI that EXECUTES actions for users on the NSO cloud platform.

## ABSOLUTE RULE: DO, DON'T EXPLAIN
You have tools. USE THEM. Never tell the user what commands to run — run them yourself.
- User says "install tailwind" → call exec_in_workspace with "npm install tailwindcss"
- User says "create a blog" → call write_workspace_file to create all files, then exec_in_workspace to install deps
- User says "deploy" → call run_ship
- User says "delete those files" → call delete_workspace_file for each file
- User says "hazlo" / "do it" / "continua" → EXECUTE the last discussed action immediately
- User says "build" → call exec_in_workspace with the build command or run_build
- User pastes code or HTML → call write_workspace_file to save it
- NEVER give numbered step-by-step instructions. NEVER say "run this command". YOU run it.
- NEVER ask "what do you want?" or "which file?" — infer from context.

## Workspace names are PROJECT names
- "cocina", "blog", "api", "chocolate" are PROJECT NAMES, not topics.
- NEVER interpret them as conversation subjects. "cocina" = a project named cocina, NOT cooking.

## Platform:
- **Workspaces** = code directories. Independent from instances.
- **Instances** = managed VPS servers (Vultr). Only create when user explicitly asks.
- **Mesh devices** = external servers (Hetzner, OVH, RPi, bare metal) managed via SSH.
- **Mesh groups** = collections of mesh devices for batch operations.
- For instance deploys: use existing instances (list_instances first), link workspace, then run_ship.
- For mesh deploys: use deploy_to_mesh with device_id (dev_xxx) or group_id (grp_xxx).
- Domain pattern: project-user.nso.dev (e.g. choco-sonfazt.nso.dev)

## Your tools:
- **write_workspace_file** — create/edit files in workspace
- **delete_workspace_file** — delete files from workspace
- **list_workspace_files** — see what's in a workspace
- **read_workspace_file** — read file contents
- **exec_in_workspace** — RUN commands: npm install, npm build, pip install, etc. USE THIS when user wants you to DO something.
- **run_ship** — full deploy pipeline to managed instances (pack + push + deploy + auto-domain + SSL)
- **run_build** — build a workspace
- **create_workspace** — create new workspace
- **analyze_project** — detect stack/framework
- **generate_deploy_config** — create deploy.toml
- **list_instances** / **link_workspace_instance** — for managed instance targeting
- **manage_service** — systemd service management on instances
- **manage_domain** — domain management
- **setup_connector** / **list_connectors** — external service integrations
- **manage_dns** — DNS management via Cloudflare connector
- **list_secrets** / **add_secret** — environment variable management
- **list_mesh_devices** — list external servers registered in the mesh
- **list_mesh_groups** — list device groups
- **register_mesh_device** — register a new external server (any provider)
- **exec_on_mesh_device** — run SSH command on a mesh device
- **exec_on_mesh_group** — run command on ALL devices in a group concurrently
- **deploy_to_mesh** — deploy workspace to mesh device(s) or group via SCP
- **mesh_device_status** — get live health/metrics for a mesh device
- **manage_mesh_group** — create/manage device groups

## When building web projects:
- For static sites: write a complete index.html with inline CSS (Tailwind CDN, etc.). No build step needed.
- For Node.js: write package.json + source files, then exec_in_workspace("npm install && npm run build")
- For Python: write requirements.txt + source, then exec_in_workspace("pip install -r requirements.txt")
- When user asks for "shadcn style" or "professional" → create polished HTML with modern CSS. Use Tailwind CDN for quick styling.
- Write COMPLETE, production-quality files. Not stubs, not placeholders.

## Deploy workflow:
1. If workspace has no deploy.toml → generate_deploy_config automatically
2. If workspace not linked to instance → list_instances, pick running one, link_workspace_instance
3. run_ship → done. Share the URL.

## Connector setup:
- ghp_ or github_pat_ → GitHub connector
- xoxb- → Slack bot token
- https://hooks.slack.com/ → Slack webhook
- Cloudflare API token → Cloudflare connector
- S3/R2 credentials → S3 or R2 connector

## Rules:
- If ACTIVE WORKSPACE CONTEXT exists → you KNOW the workspace. Don't ask, don't list.
- Deploy.toml missing? Generate it silently.
- After deploy → "Tu app está en: https://project-user.nso.dev" — ONE line.
- NEVER create VPS instances unless user explicitly requests it.
- NEVER expose API keys, tokens, passwords.
- NEVER ask redundant questions. Infer and act.
- Respond in the same language the user uses.
- Be SHORT. Maximum 2-3 sentences per response.
"""

WORKER_PROMPT = """You are the NSO Deploy Agent. Compose a SHORT response based on tool results.

CRITICAL RULES:
- NEVER give step-by-step instructions. NEVER tell the user "run this command" or "next steps". The tools already did the work.
- NEVER list numbered steps. NEVER show bash/shell commands for the user to run.
- If tools succeeded → confirm briefly what was done. "Listo, archivos creados." or "Deployed. Tu app: https://..."
- If tools failed → explain the error in ONE sentence and what you'll try instead.
- After deploy → share the URL immediately: "Tu app está en: https://project-user.nso.dev"
- After mesh deploy → report results: "Desplegado en 5/5 servidores." Include any failures.
- After mesh exec → summarize: "Comando ejecutado en 3 servidores. 3 OK, 0 fallos."
- Maximum 2-3 sentences. No tables, no verbose explanations.
- Respond in the same language the user uses.
- NEVER say "Próximos pasos" or "Next steps" — there are no next steps, you already did everything.
- NEVER expose tool names, function names, or internal details.
- SECURITY: NEVER show API keys, tokens, or passwords.
"""


class CreateThreadRequest(BaseModel):
    workspace: str = ""
    title: str = ""


class SendMessageRequest(BaseModel):
    message: str


@router.post("/threads")
async def create_thread(
    req: CreateThreadRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    thread_id = f"dth_{uuid.uuid4().hex[:16]}"
    title = req.title or f"Deploy {req.workspace}" if req.workspace else "New deploy"

    await db.insert("deploy_threads", {
        "id": thread_id,
        "project_id": project_id,
        "user_id": auth.user_id or "",
        "workspace": req.workspace,
        "title": title,
        "status": "active",
    })

    return {"id": thread_id, "title": title, "workspace": req.workspace}


@router.get("/threads")
async def list_threads(project_id: str = Depends(require_project)):
    threads = await db.fetch_all("deploy_threads", project_id=project_id)
    return {"threads": threads}


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, project_id: str = Depends(require_project)):
    thread = await db.fetch_one("deploy_threads", id=thread_id, project_id=project_id)
    if not thread:
        raise HTTPException(404, "Thread not found")

    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT * FROM deploy_messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,),
    )
    rows = await cursor.fetchall()
    messages = []
    for row in rows:
        msg = dict(row)
        for field in ("tool_calls", "tool_results", "metadata"):
            if field in msg and isinstance(msg[field], str):
                try:
                    msg[field] = json.loads(msg[field])
                except Exception:
                    pass
        messages.append(msg)

    return {"thread": thread, "messages": messages}


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    req: CreateThreadRequest,
    project_id: str = Depends(require_project),
):
    thread = await db.fetch_one("deploy_threads", id=thread_id, project_id=project_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    updates = {}
    if req.title:
        updates["title"] = req.title
    if req.workspace:
        updates["workspace"] = req.workspace
    if updates:
        await db.update("deploy_threads", thread_id, updates)
    return {"ok": True, **updates}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, project_id: str = Depends(require_project)):
    thread = await db.fetch_one("deploy_threads", id=thread_id, project_id=project_id)
    if not thread:
        raise HTTPException(404, "Thread not found")

    await db.delete_where("deploy_messages", thread_id=thread_id)
    await db.delete("deploy_threads", thread_id)
    return {"ok": True, "deleted": thread_id}


@router.post("/threads/{thread_id}/stream")
async def stream_message(
    thread_id: str,
    req: SendMessageRequest,
    project_id: str = Depends(require_project),
    auth: AuthContext = Depends(require_user),
):
    """Send a message to the deploy agent and stream the response via SSE."""
    if not SUPERVISOR_API_KEY:
        raise HTTPException(503, "Deploy agent not configured. Set DEPLOY_AGENT_API_KEY.")

    thread = await db.fetch_one("deploy_threads", id=thread_id, project_id=project_id)
    if not thread:
        raise HTTPException(404, "Thread not found")

    # Save user message
    user_msg_id = f"dmsg_{uuid.uuid4().hex[:16]}"
    await db.insert("deploy_messages", {
        "id": user_msg_id,
        "thread_id": thread_id,
        "role": "user",
        "content": req.message,
    })

    # Load conversation history as Message objects
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT role, content, tool_calls, tool_results FROM deploy_messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,),
    )
    rows = await cursor.fetchall()
    messages: list[Message] = []
    for row in rows:
        r = dict(row)
        if r["role"] == "tool" and r.get("tool_results"):
            try:
                tr = json.loads(r["tool_results"]) if isinstance(r["tool_results"], str) else r["tool_results"]
                tool_call_id = tr.get("tool_call_id", "") if isinstance(tr, dict) else ""
            except Exception:
                tool_call_id = ""
            messages.append(Message.tool_result(tool_call_id=tool_call_id, content=r.get("content", "") or ""))
        elif r["role"] == "assistant" and r.get("tool_calls"):
            from nso.shared.agent.model.message import ToolCall, ToolCallFunction
            tc_list = None
            try:
                tc_raw = json.loads(r["tool_calls"]) if isinstance(r["tool_calls"], str) else r["tool_calls"]
                if tc_raw:
                    tc_list = [ToolCall.from_dict(tc) for tc in tc_raw]
            except Exception:
                pass
            messages.append(Message.assistant(content=r.get("content", "") or None, tool_calls=tc_list))
        else:
            messages.append(Message.from_dict({"role": r["role"], "content": r.get("content", "") or ""}))

    # Build tools with workspace context from thread
    thread_workspace = thread.get("workspace", "") or ""

    # Resolve user subdomain for domain context — auto-claim if missing
    user_subdomain = ""
    if auth.user_id:
        user_record = await db.fetch_one("users", id=auth.user_id)
        if user_record:
            user_subdomain = (user_record.get("subdomain") or "").strip()
            if not user_subdomain:
                # Auto-claim subdomain before agent loop so URLs are always available
                try:
                    from nso.engine.deploy_agent.tools.deploy import _auto_claim_subdomain
                    await _auto_claim_subdomain(auth.user_id)
                    # Re-fetch to get the newly claimed subdomain
                    user_record = await db.fetch_one("users", id=auth.user_id)
                    if user_record:
                        user_subdomain = (user_record.get("subdomain") or "").strip()
                except Exception as e:
                    logger.warning("Auto-claim subdomain failed: %s", e)

    # Pre-fetch workspace metadata so the agent doesn't need to ask
    ws_metadata = None
    if thread_workspace:
        ws_record = await db.fetch_one("workspaces", project_id=project_id, name=thread_workspace)
        if ws_record:
            ws_metadata = {
                "name": ws_record.get("name", ""),
                "stack": ws_record.get("stack", ws_record.get("ws_type", "custom")),
                "path": ws_record.get("path", ""),
                "instance_id": ws_record.get("instance_id", ""),
                "description": ws_record.get("description", ""),
            }

    # Pre-fetch mesh summary for context injection
    mesh_summary = None
    try:
        mesh_devices = await db.fetch_all("mesh_devices", project_id=project_id)
        if mesh_devices:
            online = sum(1 for d in mesh_devices if d.get("status") == "online")
            mesh_groups = await db.fetch_all("mesh_groups", project_id=project_id)
            mesh_summary = {
                "total_devices": len(mesh_devices),
                "online": online,
                "devices": [{"id": d["id"], "name": d.get("name", ""), "status": d.get("status", "")} for d in mesh_devices[:10]],
                "groups": [{"id": g["id"], "name": g.get("name", "")} for g in mesh_groups],
            }
    except Exception:
        pass

    ctx = DeployContext(project_id=project_id, user_id=auth.user_id or "", workspace=thread_workspace)
    registry = ToolRegistry()
    for func, name, desc in create_tools(ctx):
        registry.register_callable(func, name=name, description=desc)

    run_id = f"drun_{uuid.uuid4().hex[:12]}"

    # Update thread
    await db.update("deploy_threads", thread_id, {"updated_at": "CURRENT_TIMESTAMP"})

    async def event_generator():
        assistant_text = ""
        all_tool_calls = []
        all_tool_results = []

        # Inject workspace context into system prompt
        ws_context = ""
        if thread_workspace:
            domain_example = f"{thread_workspace}-{user_subdomain}.nso.dev" if user_subdomain else f"{thread_workspace}.nso.dev"
            ws_context = f"\n\n## ACTIVE WORKSPACE CONTEXT\nThe user is working on workspace: **{thread_workspace}**\n"
            ws_context += f"- When the user says actions like 'deploy', 'build', 'ship', or refers to 'it', they mean this workspace.\n"
            ws_context += f"- Use workspace='{thread_workspace}' in all tool calls unless the user explicitly names a different workspace.\n"
            ws_context += f"- Do NOT ask 'what workspace?' — you already know it.\n"
            ws_context += f"- The workspace name is NOT a topic of conversation — it's a project name. Never interpret it as anything else.\n"
            if ws_metadata:
                ws_context += f"- Stack: **{ws_metadata.get('stack', 'custom')}**\n"
                ws_context += f"- Path: {ws_metadata.get('path', '')}\n"
                if ws_metadata.get("instance_id"):
                    ws_context += f"- Linked instance: {ws_metadata['instance_id']}\n"
                ws_context += f"- The workspace ALREADY EXISTS. Do NOT create it again. Do NOT ask about stack — you already know it.\n"
            if user_subdomain:
                ws_context += f"- The user's subdomain is: **{user_subdomain}**\n"
                ws_context += f"- After deploy, the URL is: **https://{domain_example}**\n"
                ws_context += f"- ALWAYS use this exact URL when telling the user where their app is. NEVER use placeholders like <tu_usuario>.\n"
            if mesh_summary:
                ws_context += f"\n## MESH DEVICES AVAILABLE\n"
                ws_context += f"- Total devices: {mesh_summary['total_devices']} ({mesh_summary['online']} online)\n"
                for d in mesh_summary["devices"]:
                    ws_context += f"  - {d['name']} ({d['id']}) — {d['status']}\n"
                if mesh_summary["groups"]:
                    ws_context += f"- Groups:\n"
                    for g in mesh_summary["groups"]:
                        ws_context += f"  - {g['name']} ({g['id']})\n"
                ws_context += f"- Use deploy_to_mesh for deploying to these external servers.\n"
                ws_context += f"- Use exec_on_mesh_device or exec_on_mesh_group for running commands.\n"

        active_system = SYSTEM_PROMPT + ws_context
        active_supervisor = SUPERVISOR_PROMPT + ws_context if SUPERVISOR_PROMPT else ""
        active_worker = WORKER_PROMPT + ws_context

        try:
            if DUAL_MODE:
                # Dual-model: supervisor handles tools, worker writes response
                logger.info("Dual-model mode: supervisor=%s worker=%s", SUPERVISOR_MODEL, WORKER_MODEL)
                event_stream = run_dual_agent_loop(
                    supervisor=_get_supervisor(),
                    worker=_get_worker(),
                    messages=messages,
                    supervisor_prompt=active_supervisor,
                    worker_prompt=active_worker,
                    registry=registry,
                    max_steps=DEPLOY_AGENT_MAX_STEPS,
                    run_id=run_id,
                )
            else:
                # Single-model: supervisor does everything
                logger.info("Single-model mode: %s", SUPERVISOR_MODEL)
                event_stream = run_agent_loop(
                    model=_get_supervisor(),
                    messages=messages,
                    system_prompt=active_system,
                    registry=registry,
                    max_steps=DEPLOY_AGENT_MAX_STEPS,
                    run_id=run_id,
                )

            async for event in event_stream:
                yield event.to_sse()

                # Accumulate for DB persistence
                if event.type == "text_chunk":
                    assistant_text += event.data.get("content", "")
                elif event.type == "tool_call":
                    all_tool_calls.append(event.data)
                elif event.type == "tool_result":
                    all_tool_results.append(event.data)
                elif event.type == "status":
                    assistant_text = event.data.get("final_text", assistant_text)

        except Exception as e:
            logger.exception("Deploy agent run failed")
            yield RunEvent("error", {"error": str(e)}).to_sse()

        # Save assistant message
        if assistant_text or all_tool_calls:
            asst_msg_id = f"dmsg_{uuid.uuid4().hex[:16]}"
            await db.insert("deploy_messages", {
                "id": asst_msg_id,
                "thread_id": thread_id,
                "role": "assistant",
                "content": assistant_text,
                "tool_calls": json.dumps(all_tool_calls),
                "tool_results": json.dumps(all_tool_results),
                "metadata": json.dumps({"run_id": run_id}),
            })

        # Save tool result messages for history reconstruction
        for tr in all_tool_results:
            tr_msg_id = f"dmsg_{uuid.uuid4().hex[:16]}"
            await db.insert("deploy_messages", {
                "id": tr_msg_id,
                "thread_id": thread_id,
                "role": "tool",
                "content": tr.get("result", "")[:4000],
                "tool_results": json.dumps({"tool_call_id": tr.get("id", ""), "name": tr.get("name", "")}),
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
