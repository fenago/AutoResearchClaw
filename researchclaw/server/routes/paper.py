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
