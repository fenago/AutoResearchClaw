"""Admin user management — allowlist CRUD via the caller's own Supabase JWT.

No service-role key: Postgres RLS decides who may manage the allowlist
(is_admin rows in the allowlist table). Non-admin callers get 403 from RLS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _cfg() -> tuple[str, str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    table = os.environ.get("AUTH_ALLOWLIST_TABLE", "e5o_users")
    if not url or not anon:
        raise HTTPException(400, "Auth is not configured on this server")
    return url, anon, table


def _caller_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Missing bearer token")
    return token


def _sb(url: str, anon: str, path: str, token: str, method: str = "GET",
        body: dict | None = None, prefer: str = "") -> tuple[int, Any]:
    headers = {
        "apikey": anon,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "researchclaw",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode()
        except Exception:
            pass
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"message": raw[:300]}


class AddUser(BaseModel):
    email: str
    is_admin: bool = False
    temp_password: str = ""  # if set, also create the login account


@router.get("/api/admin/users")
async def list_users(request: Request) -> dict[str, Any]:
    url, anon, table = _cfg()
    token = _caller_token(request)

    def _go() -> dict[str, Any]:
        st, me = _sb(url, anon, "/auth/v1/user", token)
        my_email = (me or {}).get("email", "") if st == 200 else ""
        st, rows = _sb(
            url, anon,
            f"/rest/v1/{table}?select=email,is_admin,added_at&order=added_at.asc",
            token,
        )
        rows = rows if isinstance(rows, list) else []
        is_admin = any(
            r.get("email", "").lower() == my_email.lower() and r.get("is_admin")
            for r in rows
        )
        usage = {}
        if is_admin:
            import os as _os

            writer = _os.environ.get("E5O_WRITER_SECRET", "")
            limit = int(_os.environ.get("SERPAPI_MONTHLY_LIMIT", "250"))
            if writer:
                st_u, used = _sb(url, anon, "/rest/v1/rpc/e5o_api_usage_now", token,
                                 method="POST", body={"p_secret": writer, "p_provider": "serpapi"})
                if isinstance(used, int):
                    usage = {"serpapi": {"used": used, "limit": limit, "remaining": max(0, limit - used)}}
        return {"me": my_email, "is_admin": is_admin,
                "users": rows if is_admin else [], "usage": usage}

    return await asyncio.to_thread(_go)


@router.post("/api/admin/users")
async def add_user(request: Request, body: AddUser) -> dict[str, Any]:
    url, anon, table = _cfg()
    token = _caller_token(request)
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")

    def _go() -> dict[str, Any]:
        st, res = _sb(
            url, anon, f"/rest/v1/{table}", token, method="POST",
            body={"email": email, "is_admin": body.is_admin},
            prefer="return=representation",
        )
        if st in (401, 403):
            raise HTTPException(403, "Only admins can add users")
        if st == 409:
            raise HTTPException(409, "That email is already on the allowlist")
        if st not in (200, 201):
            raise HTTPException(500, f"Allowlist insert failed: {res}")

        account_note = "User must sign in with an existing account for this Supabase project."
        if body.temp_password:
            st2, res2 = _sb(
                url, anon, "/auth/v1/signup", anon, method="POST",
                body={"email": email, "password": body.temp_password},
            )
            if st2 == 200 and isinstance(res2, dict) and res2.get("confirmation_sent_at"):
                account_note = ("Account created — a confirmation email was sent; "
                                "after confirming, they sign in with the temp password.")
            elif st2 == 200:
                account_note = "Account created — they can sign in with the temp password."
            else:
                msg = (res2 or {}).get("msg") or (res2 or {}).get("error_description") or str(res2)
                account_note = f"Allowlisted, but account creation failed: {msg}"
        return {"ok": True, "email": email, "note": account_note}

    return await asyncio.to_thread(_go)


@router.delete("/api/admin/users")
async def remove_user(request: Request, email: str) -> dict[str, Any]:
    url, anon, table = _cfg()
    token = _caller_token(request)
    email = email.strip().lower()

    def _go() -> dict[str, Any]:
        st, me = _sb(url, anon, "/auth/v1/user", token)
        if st == 200 and (me or {}).get("email", "").lower() == email:
            raise HTTPException(400, "You cannot remove your own access")
        st, rows = _sb(
            url, anon,
            f"/rest/v1/{table}?email=eq.{urllib.parse.quote(email)}",
            token, method="DELETE", prefer="return=representation",
        )
        if st in (401, 403):
            raise HTTPException(403, "Only admins can remove users")
        removed = isinstance(rows, list) and len(rows) > 0
        if not removed:
            raise HTTPException(404, "Email not found (or you lack permission)")
        return {"ok": True, "email": email}

    return await asyncio.to_thread(_go)
