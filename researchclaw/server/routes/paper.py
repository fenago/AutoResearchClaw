"""Turn a plain-English paper idea into a confirmable research plan."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["paper"])

_PLAN_PROMPT = """You help everyday users start an autonomous research pipeline.
The user describes, in plain English, an idea for a research paper and what they
want to get done. Turn it into a concrete research plan.

Respond with ONLY a JSON object with these keys:
- "title": a working paper title (concise, specific)
- "topic": one sentence stating the research topic for the pipeline to pursue
- "goal": one or two sentences describing what the finished paper will show
- "approach": an array of 3-5 short bullet strings describing how the research
  will proceed (literature review, hypothesis, experiments, analysis, writing)

User's idea:
{idea}"""


class PlanRequest(BaseModel):
    idea: str


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


@router.post("/api/paper/plan")
async def plan_paper(req: PlanRequest, request: Request) -> dict[str, Any]:
    idea = req.idea.strip()
    if not idea:
        return {"ok": False, "error": "Describe your idea first."}

    from researchclaw.server.app import _app_state
    from researchclaw.server.routes.llm import resolve_request_config

    config = await asyncio.to_thread(resolve_request_config, _app_state["config"], request)

    def _go() -> dict[str, Any]:
        from researchclaw.llm.client import LLMClient

        client = LLMClient.from_rc_config(config)
        resp = client.chat(
            [{"role": "user", "content": _PLAN_PROMPT.format(idea=idea)}],
            json_mode=True,
            max_tokens=1500,
            strip_thinking=True,
        )
        plan = _parse_json(resp.content)
        for key in ("title", "topic", "goal"):
            if not isinstance(plan.get(key), str) or not plan[key].strip():
                raise ValueError(f"Model response missing '{key}'")
        if not isinstance(plan.get("approach"), list):
            plan["approach"] = []
        return {"ok": True, "plan": plan, "model": resp.model}

    try:
        return await asyncio.to_thread(_go)
    except Exception as exc:
        logger.warning("paper plan failed", exc_info=True)
        return {"ok": False, "error": str(exc)[:300]}


_CHAT_PROMPT = """You are the research assistant writing a paper for its owner.
Answer their message helpfully and concisely (2-5 sentences, plain English).

Paper context:
{context}

If the owner is giving direction (preferences, constraints, changes), acknowledge
it clearly and note it will be applied at the next stage of the run. If they ask
a question, answer from the context; say so plainly if the context doesn't cover it.

Recent conversation:
{history}

Owner's message: {message}"""


class PaperChatRequest(BaseModel):
    message: str
    run_id: str | None = None


# Per-run steering notes + short chat history (in-memory)
_chat_state: dict[str, dict[str, list]] = {}


def _run_context() -> tuple[str, str]:
    """Build context from the active run's plan + stage narration."""
    from researchclaw.server.routes.pipeline import _active_run

    if not _active_run:
        return "", "No paper is currently being written."
    run_id = _active_run.get("run_id", "")
    parts = [f"Topic: {_active_run.get('topic', '')}", f"Status: {_active_run.get('status')}"]
    watcher = _active_run.get("watcher")
    if watcher:
        snap = watcher.snapshot()
        if snap.get("current"):
            parts.append(f"Current stage: {snap['current']}")
        for entry in snap.get("log", []):
            parts.append(f"[{entry['index']}. {entry['label']}] {entry.get('summary') or ''}")
    notes = _chat_state.get(run_id, {}).get("steering", [])
    if notes:
        parts.append("Owner directions so far: " + " | ".join(notes))
    return run_id, "\n".join(parts)


@router.post("/api/paper/chat")
async def paper_chat(req: PaperChatRequest, request: Request) -> dict[str, Any]:
    message = req.message.strip()
    if not message:
        return {"ok": False, "error": "Say something first."}

    from researchclaw.server.app import _app_state
    from researchclaw.server.routes.llm import resolve_request_config

    config = await asyncio.to_thread(resolve_request_config, _app_state["config"], request)
    run_id, context = _run_context()

    state = _chat_state.setdefault(run_id or "idle", {"history": [], "steering": []})
    history = "\n".join(state["history"][-6:]) or "(none)"

    def _go() -> str:
        from researchclaw.llm.client import LLMClient

        client = LLMClient.from_rc_config(config)
        resp = client.chat(
            [{"role": "user", "content": _CHAT_PROMPT.format(
                context=context, history=history, message=message)}],
            max_tokens=1200,
            strip_thinking=True,
        )
        return (resp.content or "").strip()

    try:
        reply = await asyncio.to_thread(_go)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}

    state["history"].append(f"Owner: {message}")
    state["history"].append(f"Assistant: {reply}")
    # Heuristic: treat imperative-looking messages as steering notes
    if run_id and not message.rstrip().endswith("?"):
        state["steering"].append(message[:300])

    return {"ok": True, "reply": reply}
