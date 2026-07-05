"""Paper library endpoints — each user reads their own saved papers (RLS)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["papers"])


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


@router.get("/api/papers")
async def list_papers(request: Request) -> dict[str, Any]:
    url, anon = _cfg()
    token = _token(request)
    rows = await asyncio.to_thread(
        _get, url, anon,
        "/rest/v1/e5o_papers?select=id,run_id,title,topic,status,error,created_at,updated_at&order=created_at.desc",
        token,
    )
    return {"papers": rows if isinstance(rows, list) else []}


@router.get("/api/papers/{paper_id}")
async def get_paper(request: Request, paper_id: str) -> dict[str, Any]:
    url, anon = _cfg()
    token = _token(request)
    rows = await asyncio.to_thread(
        _get, url, anon,
        f"/rest/v1/e5o_papers?id=eq.{urllib.parse.quote(paper_id)}&select=*",
        token,
    )
    if not isinstance(rows, list) or not rows:
        raise HTTPException(404, "Paper not found")
    return rows[0]
