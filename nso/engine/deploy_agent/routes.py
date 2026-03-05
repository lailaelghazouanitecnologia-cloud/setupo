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
from nso.engine.deploy_agent.run import ToolRegistry, run_agent_loop, RunEvent
from nso.engine.deploy_agent.tools import create_tools, DeployContext

logger = logging.getLogger("nso.routes.deploy_agent")
router = APIRouter()

# ── LLM config ──
# Supports any OpenAI-compatible API (Groq, OpenRouter, OpenAI, etc.)
DEPLOY_AGENT_API_KEY = os.environ.get("DEPLOY_AGENT_API_KEY", "")
DEPLOY_AGENT_API_URL = os.environ.get("DEPLOY_AGENT_API_URL", "https://api.groq.com/openai/v1/chat/completions")
DEPLOY_AGENT_MODEL = os.environ.get("DEPLOY_AGENT_MODEL", "llama-3.3-70b-versatile")
DEPLOY_AGENT_MAX_STEPS = int(os.environ.get("DEPLOY_AGENT_MAX_STEPS", "15"))


SYSTEM_PROMPT = """You are the NSO Deploy Agent — an AI assistant that helps users deploy their projects.

You have access to tools that let you:
1. Analyze workspaces to detect stack, framework, dependencies
2. Generate deploy.toml configuration files
3. Read and write workspace files
4. Build projects (with caching — won't rebuild unchanged code)
5. Ship workspaces (pack → push to R2 → deploy to VPS instance)
6. Check deploy status on instances
7. List workspaces and instances

## Your workflow:

When a user wants to deploy, follow this process:
1. **Analyze** — Call `analyze_project` to understand the workspace structure
2. **Configure** — If no deploy.toml exists, generate one with `generate_deploy_config`
3. **Review** — Show the user what will happen and ask for confirmation
4. **Build** — If needed, trigger `run_build`
5. **Ship** — Execute `run_ship` to pack, push, and deploy
6. **Verify** — Check deploy status with `check_deploy_status`

## Important rules:
- Always analyze before deploying if you haven't already
- If deploy.toml doesn't exist, generate one and show it to the user
- When generating deploy.toml, explain what each section does
- If something fails, explain what went wrong and suggest fixes
- Be concise but informative
- The subdomain is auto-claimed during ship — no manual step needed
- After successful deploy, tell the user their domain

## Response style:
- Use markdown for formatting
- Show file contents in code blocks
- Be direct: say what you're doing, then do it
- If you need info from the user, ask specific questions
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
    if not DEPLOY_AGENT_API_KEY:
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

    # Load conversation history
    conn = await db.get_db()
    cursor = await conn.execute(
        "SELECT role, content, tool_calls, tool_results FROM deploy_messages WHERE thread_id = ? ORDER BY created_at ASC",
        (thread_id,),
    )
    rows = await cursor.fetchall()
    messages = []
    for row in rows:
        r = dict(row)
        msg = {"role": r["role"], "content": r.get("content", "") or ""}
        # Reconstruct tool_calls in assistant messages
        if r["role"] == "assistant" and r.get("tool_calls"):
            try:
                tc = json.loads(r["tool_calls"]) if isinstance(r["tool_calls"], str) else r["tool_calls"]
                if tc:
                    msg["tool_calls"] = tc
            except Exception:
                pass
        # Tool result messages
        if r["role"] == "tool" and r.get("tool_results"):
            try:
                tr = json.loads(r["tool_results"]) if isinstance(r["tool_results"], str) else r["tool_results"]
                if tr and isinstance(tr, dict):
                    msg["tool_call_id"] = tr.get("tool_call_id", "")
            except Exception:
                pass
        messages.append(msg)

    # Build tools
    ctx = DeployContext(project_id=project_id, user_id=auth.user_id or "")
    registry = ToolRegistry()
    for func, name, desc in create_tools(ctx):
        registry.register(func, name=name, description=desc)

    run_id = f"drun_{uuid.uuid4().hex[:12]}"

    # Update thread
    await db.update("deploy_threads", thread_id, {"updated_at": "CURRENT_TIMESTAMP"})

    async def event_generator():
        assistant_text = ""
        all_tool_calls = []
        all_tool_results = []

        try:
            async for event in run_agent_loop(
                api_key=DEPLOY_AGENT_API_KEY,
                api_url=DEPLOY_AGENT_API_URL,
                model=DEPLOY_AGENT_MODEL,
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                registry=registry,
                max_steps=DEPLOY_AGENT_MAX_STEPS,
                run_id=run_id,
            ):
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
