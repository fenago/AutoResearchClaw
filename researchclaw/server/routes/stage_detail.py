"""Stage-detail endpoints — per-stage guide, progress, and stored files for a paper (RLS)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..stage_guide import STAGE_GUIDE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stage-detail"])


def _cfg() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        raise HTTPException(400, "Paper library is not configured on this server")
    return url, anon


def _token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Missing bearer token")
    return token


def _get(url: str, anon: str, path: str, token: str) -> Any:
    req = urllib.request.Request(
        url + path,
        headers={"apikey": anon, "Authorization": f"Bearer {token}",
                 "User-Agent": "researchclaw"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _stage_dir(num: int) -> str:
    return f"stage-{num:02d}"


def _is_reasoning(name: str, reasoning_file: str) -> bool:
    if not reasoning_file:
        return False
    if name == reasoning_file:
        return True
    # Directory-style reasoning files ("cards", "perspectives") have no
    # extension — treat them as a prefix matching any file underneath.
    if "." not in reasoning_file.rsplit("/", 1)[-1]:
        return name.startswith(reasoning_file.rstrip("/") + "/")
    return False


def _file_kind(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "md":
        return "md"
    if ext == "json":
        return "json"
    if ext == "bib":
        return "bib"
    if ext in ("yaml", "yml"):
        return "yaml"
    return "text"


async def _fetch_paper(request: Request, paper_id: str, select: str) -> dict[str, Any]:
    url, anon = _cfg()
    token = _token(request)
    rows = await asyncio.to_thread(
        _get, url, anon,
        f"/rest/v1/e5o_papers?id=eq.{urllib.parse.quote(paper_id)}&select={select}",
        token,
    )
    if not isinstance(rows, list) or not rows:
        raise HTTPException(404, "Paper not found")
    return rows[0]


@router.get("/api/paper/{paper_id}/stages")
async def list_stages(request: Request, paper_id: str) -> dict[str, Any]:
    row = await _fetch_paper(request, paper_id, "run_files,stage_log,status")
    run_files = row.get("run_files") or {}
    stage_log = row.get("stage_log") or []
    completed = (row.get("status") or "") == "completed"

    summaries: dict[str, str] = {}
    for entry in stage_log:
        if isinstance(entry, dict) and entry.get("key") and entry.get("summary"):
            summaries[entry["key"]] = entry["summary"]

    done: set[int] = set()
    for guide in STAGE_GUIDE:
        files = run_files.get(_stage_dir(guide["num"])) or {}
        if guide["key"] in summaries or files:
            done.add(guide["num"])

    highest_done = max(done) if done else 0
    active = 0 if completed else highest_done + 1

    stages: list[dict[str, Any]] = []
    for guide in STAGE_GUIDE:
        num = guide["num"]
        files = run_files.get(_stage_dir(num)) or {}
        if num in done:
            state = "done"
        elif num == active:
            state = "active"
        else:
            state = "pending"
        stages.append({
            **guide,
            "state": state,
            "summary": summaries.get(guide["key"], ""),
            "files": [
                {"name": name, "is_reasoning": _is_reasoning(name, guide["reasoning_file"])}
                for name in sorted(files)
            ],
        })
    return {"stages": stages}


@router.get("/api/paper/{paper_id}/file")
async def get_stage_file(request: Request, paper_id: str, stage: int, name: str) -> dict[str, Any]:
    row = await _fetch_paper(request, paper_id, "run_files")
    run_files = row.get("run_files") or {}
    files = run_files.get(_stage_dir(stage)) or {}
    content = files.get(name)
    if content is None:
        raise HTTPException(404, "File not found")
    return {"name": name, "content": content, "kind": _file_kind(name)}
