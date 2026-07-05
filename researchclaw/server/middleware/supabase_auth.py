"""Supabase-backed multi-user auth (pure ASGI — covers HTTP and WebSockets).

Enabled when SUPABASE_URL and SUPABASE_ANON_KEY are set. A request is allowed
when it carries a valid Supabase access token (Authorization: Bearer for HTTP,
?token= query param for WebSockets) AND the token's email is present in the
allowlist table (default: e5o_users). The allowlist check runs with the user's
own token through RLS, so no service-role key is ever needed server-side.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0  # seconds a verified token stays trusted without re-checking


class SupabaseAuthMiddleware:
    """Reject unauthenticated/unauthorized requests before they reach the app."""

    EXEMPT_PATHS = frozenset(
        {"/", "/app", "/api/health", "/api/auth/config", "/docs", "/openapi.json", "/favicon.ico"}
    )
    EXEMPT_PREFIXES = ("/static", "/site")

    def __init__(
        self,
        app: Any,
        supabase_url: str,
        anon_key: str,
        allowlist_table: str = "e5o_users",
    ) -> None:
        self.app = app
        self.supabase_url = supabase_url.rstrip("/")
        self.anon_key = anon_key
        self.allowlist_table = allowlist_table
        self._cache: dict[str, tuple[float, bool]] = {}

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if scope["type"] == "http" and (
            path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        token = self._extract_token(scope)
        if token and await self._authorized(token):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
        else:
            body = json.dumps({"detail": "Unauthorized"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _extract_token(scope: dict) -> str:
        if scope["type"] == "websocket":
            query = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
            return (query.get("token") or [""])[0]
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""

    async def _authorized(self, token: str) -> bool:
        now = time.monotonic()
        cached = self._cache.get(token)
        if cached and cached[0] > now:
            return cached[1]

        ok = await asyncio.to_thread(self._verify, token)
        # Keep the cache from growing without bound
        if len(self._cache) > 1000:
            self._cache.clear()
        self._cache[token] = (now + _CACHE_TTL, ok)
        return ok

    def _verify(self, token: str) -> bool:
        """Valid Supabase session AND email present in the allowlist table."""
        try:
            user = self._get_json(
                f"{self.supabase_url}/auth/v1/user",
                token,
            )
            email = (user or {}).get("email", "")
            if not email:
                return False
            rows = self._get_json(
                f"{self.supabase_url}/rest/v1/{self.allowlist_table}?select=email&limit=1",
                token,
            )
            allowed = isinstance(rows, list) and len(rows) > 0
            if not allowed:
                logger.warning("Auth: %s is not in %s", email, self.allowlist_table)
            return allowed
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return False
            logger.warning("Supabase auth check failed: HTTP %s", exc.code)
            return False
        except Exception:
            logger.warning("Supabase auth check errored", exc_info=True)
            return False

    def _get_json(self, url: str, token: str) -> Any:
        req = urllib.request.Request(
            url,
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {token}",
                "User-Agent": "researchclaw",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
