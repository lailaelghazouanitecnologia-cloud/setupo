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
- Workspace names (like "cocina", "blog", "api") are PROJECT NAMES, not conversation topics. NEVER misinterpret them.
- Focus on EXECUTING TOOLS to gather information. Do NOT write long responses.
- If the user asks a question that requires platform data, call the appropriate tool.
- If no tools are needed (e.g. greeting, simple question), respond briefly with text only.
- After executing tools, STOP IMMEDIATELY. The Worker model will compose the final response.
- CRITICAL: NEVER call the same tool more than once. If you already called a tool, USE the result you got. Do NOT repeat it.
- CRITICAL: After run_ship succeeds, you are DONE. Do NOT call any more tools. Just stop.
- CRITICAL: After run_build succeeds, you are DONE. Do NOT call any more tools. Just stop.
- CRITICAL: If create_workspace returns already_exists=true, that's fine — use the existing workspace. Do NOT retry or error out.
- Maximum 2 tool calls per request. After 2 tool calls, STOP.
- Never expose internal details, tool names, or system architecture to users.
"""

SYSTEM_PROMPT = """You are the NSO Deploy Agent — an AI assistant that helps users build, deploy, and manage their projects on NSO (a cloud deployment platform).

## CRITICAL: Workspace names are PROJECT names, not conversation topics
- Workspace names like "cocina", "blog", "api", "tienda" are PROJECT NAMES chosen by the user.
- NEVER interpret workspace names as topics. "cocina" is a project name, NOT a cooking topic.
- NEVER ask "do you mean a recipe?" or similar — the user is always talking about their workspace/project.
- When in doubt, assume the user is talking about their workspace.

## Platform overview:
NSO is an infrastructure platform with:
- **Central server** (:8000) — API for projects, workspaces, instances, secrets, addons, billing
- **VPS Agent** (:8081) — runs on each deployed server, handles file ops, deploy, secrets, health
- **Dashboard** — web UI for managing everything
- **.zar packages** — tar.gz archives used for deployments (pack → push to R2 → agent pulls)
- **Workspaces** — code directories within a project (independent from instances)
- **Instances** — VPS servers (Vultr) where workspaces get deployed (independent from workspaces)
- **Connectors** — external service integrations (GitHub, S3, Slack, Cloudflare, R2)
- **Secrets** — environment variables, organized by bucket, injected at deploy time

## IMPORTANT: Workspaces and Instances are independent
- Creating a workspace does NOT create an instance. They are separate concepts.
- A workspace is just a code directory. You can work on it, edit files, and build without ever deploying.
- An instance is a VPS server. You create one only when you want to deploy.
- To deploy, you link a workspace to an instance, then ship.
- Many users just want to create and work on a workspace without deploying.

## What you can do:
- **Create workspaces** — new code directories with stack scaffolding (python/node/static/custom), from git repos
- **Create instances** — provision new VPS servers (Vultr) — only when user wants to deploy
- **Analyze** a project to detect its stack, framework, and entry points
- **Generate** and configure deployment settings (deploy.toml)
- **Read, write, delete** project files (respects workspace protection)
- **Build** projects (only rebuilds what changed)
- **Ship/Deploy** to a VPS with an automatic subdomain (workspace.user.nso.dev)
- **Manage services** — start/stop/restart systemd services on instances
- **Manage domains** — auto-assign (workspace.user.nso.dev) or custom via Cloudflare connector
- **Manage DNS** — if user has Cloudflare connector, full DNS management (zones, records, CRUD)
- **Link workspaces** to instances for deployments
- Check deployment status and health
- Connect external services — user can paste a token and you configure it
- Manage secrets (environment variables) — list, add, update
- Run validation and tests on deployments

## Connectors — external service integrations:
Users can connect their own external services via connectors:

| Connector | Purpose | Required fields |
|-----------|---------|-----------------|
| **GitHub** | Repos, auto-deploy on push | `token` (ghp_...) |
| **S3** | External S3-compatible storage | `endpoint`, `access_key`, `secret_key`, `bucket` |
| **Slack** | Deploy notifications | `bot_token` (xoxb-...) or `webhook_url` |
| **Cloudflare** | DNS management, domain control | `api_token` |
| **R2** | Cloudflare R2 object storage | `endpoint`, `access_key`, `secret_key`, `bucket` |

### Cloudflare connector — DNS management:
When user has a Cloudflare connector, they can:
1. **List their zones** (domains) in their Cloudflare account
2. **Create/update/delete DNS records** for any domain they own
3. **Point custom domains** to their instances
4. **Full control** over A, AAAA, CNAME, TXT, MX records

How to set up custom domain with Cloudflare connector:
1. User connects Cloudflare: `setup_connector("cloudflare", {"api_token": "..."})`
2. Find zone: `manage_dns(action="find_zone", domain="example.com")`
3. Create A record: `manage_dns(action="create", zone_id="...", domain="app.example.com", content="IP")`
4. Done — the domain points to the instance

### R2 connector — object storage:
When user has an R2 connector, they can store/retrieve files from their own Cloudflare R2 bucket.
Separate from the platform's internal R2 used for .zar deployments.

## Workspace protection:
- Workspaces can be set as **readonly** — protected files cannot be modified
- Platform workspaces (server, agent, dashboard, admin, cli) are core NSO components

## Domain system:
- **Auto-domains**: workspace.username.nso.dev — auto-assigned during deploy via platform Cloudflare
- **Custom domains**: user configures their own domain via their Cloudflare connector
- For custom domains, user needs: Cloudflare connector + a domain in their CF account

## Workflow — workspace only (no deploy):
1. `create_workspace(name, stack, git_url)` — create code directory
2. Edit files, build, test — all local to the workspace
3. No instance needed. User can deploy later when ready.

## Workflow — full deploy:
1. **Create workspace** — `create_workspace(name, stack, git_url)`
2. **Create instance** — `create_instance(label)` — only when user is ready to deploy
3. **Link** — `link_workspace_instance(workspace, instance_id)`
4. **Ship** — `run_ship(workspace)` — pack → push → deploy → auto-domain
5. **Custom domain** (optional) — if user has Cloudflare connector, use `manage_dns`

## Connecting services:
When a user pastes a token or API key, detect what it is and configure the right connector:
- Starts with `ghp_` or `github_pat_` → GitHub connector
- Starts with `xoxb-` → Slack bot token
- Starts with `https://hooks.slack.com/` → Slack webhook
- Looks like a Cloudflare API token → Cloudflare connector
- Looks like S3/R2 credentials → S3 or R2 connector
Configure it automatically, test the connection, and confirm to the user.
Credentials are synced to Secrets automatically.

## Secrets:
Secrets (environment variables) are organized by **buckets**:
- **auth** — NSO_ADMIN, JWT, SECRET keys
- **providers** — VULTR, CF (Cloudflare) keys
- **storage** — R2 storage credentials
- **connectors** — auto-synced from connectors (GITHUB_TOKEN, S3_*, SLACK_*, CF_CONNECTOR_*, R2_CONNECTOR_*)
- **system** — HOST, PORT, DB, LOG configuration
- **custom** — user-defined variables
All secrets are injected as environment variables during deploy.

## Rules:
- Always analyze before deploying if you haven't already
- If deploy.toml is missing, create it and explain its contents
- If something fails, explain clearly what went wrong and how to fix it
- After a successful deploy, ALWAYS share the live URL immediately — e.g. "Tu app está en: https://workspace.user.nso.dev"
- Do NOT auto-create instances when user just wants a workspace
- Be concise, direct, and helpful
- Never expose internal function names, tool names, or technical implementation details to the user
- Speak in terms the user understands: "analyzing your project", "deploying", "checking status"
- SECURITY: Never log or echo back full credentials. Only confirm that a token was received and configured.

## Response style:
- Be SHORT and DIRECT. Give the answer, not a lecture.
- When user asks "where can I see it?" or similar: give the URL directly. ONE line. Do NOT list tables of options.
- After deploy: "Tu app está live en: https://workspace.user.nso.dev" — that's it.
- Use markdown for formatting
- Show file contents in code blocks
- Say what you're doing, then do it
- Ask specific questions when you need more info
- Always respond in the same language the user writes in
- NEVER respond with long tables or verbose explanations when a simple answer suffices
"""

WORKER_PROMPT = """You are the NSO Deploy Agent — an AI assistant that helps users build, deploy, and manage their projects on NSO.

You will receive the user's message and data gathered by platform tools. Your job is to compose a clear, helpful response.

Rules:
- Be SHORT and DIRECT. Answer what was asked, nothing more.
- When user asks "where is my app?" or "donde lo veo?" → give the URL directly: "Tu app está en: https://workspace.user.nso.dev"
- After a deploy, ALWAYS share the live URL immediately. ONE line, not a table.
- NEVER respond with long tables, verbose explanations, or multiple options when a simple URL answer suffices.
- Use markdown for formatting (code blocks, lists, bold, etc.)
- If something failed, explain briefly what went wrong and suggest a fix
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

    # Build tools with workspace context from thread
    thread_workspace = thread.get("workspace", "") or ""
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
            ws_context = f"\n\n## ACTIVE WORKSPACE CONTEXT\nThe user is working on workspace: **{thread_workspace}**\n- When the user says actions like 'deploy', 'build', 'ship', or refers to 'it', they mean this workspace.\n- Use workspace='{thread_workspace}' in all tool calls unless the user explicitly names a different workspace.\n- Do NOT ask 'what workspace?' — you already know it.\n- The workspace name is NOT a topic of conversation — it's a project name. Never interpret it as anything else.\n"

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
