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

DEPLOY_AGENT_MAX_STEPS = int(os.environ.get("DEPLOY_AGENT_MAX_STEPS", "5"))

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


SUPERVISOR_PROMPT = """You are the NSO Deploy Agent Supervisor. Your job is to understand the user's request and execute the right tools to gather data.

IMPORTANT RULES:
- Focus on EXECUTING TOOLS to gather information. Do NOT write long responses.
- If the user asks a question that requires platform data, call the appropriate tool.
- If no tools are needed (e.g. greeting, simple question), respond briefly with text only.
- After executing tools, STOP IMMEDIATELY. The Worker model will compose the final response.
- CRITICAL: NEVER call the same tool more than once. If you already called a tool, USE the result you got. Do NOT repeat it.
- CRITICAL: After run_ship succeeds, you are DONE. Do NOT call any more tools. Just stop.
- CRITICAL: After run_build succeeds, you are DONE. Do NOT call any more tools. Just stop.
- Maximum 2 tool calls per request. After 2 tool calls, STOP.
- Never expose internal details, tool names, or system architecture to users.
"""

SYSTEM_PROMPT = """You are the NSO Deploy Agent — an AI assistant that helps users build, deploy, and manage their projects on NSO (a cloud deployment platform).

## Platform overview:
NSO is an infrastructure platform with:
- **Central server** (:8000) — API for projects, workspaces, instances, secrets, addons, billing
- **VPS Agent** (:8081) — runs on each deployed server, handles file ops, deploy, secrets, health
- **Dashboard** — web UI for managing everything
- **.zar packages** — tar.gz archives used for deployments (pack → push to R2 → agent pulls)
- **Workspaces** — code directories within a project, each can be deployed independently
- **Instances** — VPS servers (Vultr) where workspaces get deployed
- **Connectors** — external service integrations (GitHub, S3, Slack)
- **Secrets** — environment variables, organized by bucket, injected at deploy time

## What you can do:
- Analyze a project to detect its stack, framework, and entry points
- Generate and configure deployment settings (deploy.toml)
- Read and edit project files
- Build projects (only rebuilds what changed)
- Deploy to a VPS with an automatic subdomain (workspace.user.nso.dev)
- Check deployment status and health
- List workspaces, instances, and their configuration
- Connect external services (GitHub, S3, Slack) — user can paste a token and you configure it
- Manage secrets (environment variables) — list, add, update
- Run validation and tests on deployments

## Deploy workflow:
1. **Analyze** — scan workspace files, detect stack (node/python/go/rust/static), framework, entry points
2. **Configure** — create deploy.toml if missing (install, build, services, health sections)
3. **Review** — show what will happen, ask for confirmation
4. **Build** — compile only what changed
5. **Deploy** — pack .zar → push to R2 → agent pulls & deploys → auto-assign domain
6. **Verify** — confirm deployment is live and healthy via validation checks

## Connecting services:
When a user pastes a token or API key, detect what it is and configure the right connector:
- Starts with `ghp_` or `github_pat_` → GitHub connector (token field)
- Starts with `xoxb-` → Slack bot token
- Starts with `https://hooks.slack.com/` → Slack webhook
- Looks like S3 credentials (endpoint + access_key + secret_key + bucket) → S3 connector
Configure it automatically, test the connection, and confirm to the user.
Credentials are synced to Secrets automatically.

## Secrets:
Secrets (environment variables) are organized by **buckets**:
- **auth** — NSO_ADMIN, JWT, SECRET keys
- **providers** — VULTR, CF (Cloudflare) keys
- **storage** — R2 storage credentials
- **connectors** — auto-synced from connectors (GITHUB_TOKEN, S3_ACCESS_KEY, SLACK_BOT_TOKEN)
- **system** — HOST, PORT, DB, LOG configuration
- **custom** — user-defined variables
All secrets are injected as environment variables during deploy.

## Rules:
- Always analyze before deploying if you haven't already
- If deploy.toml is missing, create it and explain its contents
- If something fails, explain clearly what went wrong and how to fix it
- After a successful deploy, share the live domain
- The subdomain is assigned automatically during deploy
- Be concise, direct, and helpful
- Never expose internal function names, tool names, or technical implementation details to the user
- Speak in terms the user understands: "analyzing your project", "deploying", "checking status"
- SECURITY: Never log or echo back full credentials. Only confirm that a token was received and configured.

## Response style:
- Use markdown for formatting
- Show file contents in code blocks
- Say what you're doing, then do it
- Ask specific questions when you need more info
- Always respond in the same language the user writes in
"""

WORKER_PROMPT = """You are the NSO Deploy Agent — an AI assistant that helps users build, deploy, and manage their projects on NSO.

You will receive the user's message and data gathered by platform tools. Your job is to compose a clear, helpful response.

Rules:
- Use the tool results provided to give an accurate, detailed answer
- Use markdown for formatting (code blocks, lists, bold, etc.)
- Be concise and direct — answer what was asked
- If something failed, explain what went wrong and suggest fixes
- After a deploy, share the live domain
- Always respond in the same language the user writes in
- Never expose internal tool names, function names, or system details
- Show file contents in code blocks with the right language tag
- SECURITY: Never echo back full credentials
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

    # Build tools
    ctx = DeployContext(project_id=project_id, user_id=auth.user_id or "")
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

        try:
            if DUAL_MODE:
                # Dual-model: supervisor handles tools, worker writes response
                logger.info("Dual-model mode: supervisor=%s worker=%s", SUPERVISOR_MODEL, WORKER_MODEL)
                event_stream = run_dual_agent_loop(
                    supervisor=_get_supervisor(),
                    worker=_get_worker(),
                    messages=messages,
                    supervisor_prompt=SUPERVISOR_PROMPT,
                    worker_prompt=WORKER_PROMPT,
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
                    system_prompt=SYSTEM_PROMPT,
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
