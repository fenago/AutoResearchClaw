"""LLM provider/model selection endpoints for the dashboard Settings view."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm"])

# Overlay file so a provider/model choice survives a server restart.
SETTINGS_PATH = Path(os.environ.get("RC_LLM_SETTINGS_PATH", "llm_settings.json"))

# Catalog shown in the UI. `models` are suggestions — the UI also allows a
# custom model string. All providers here speak an OpenAI-compatible wire
# except `anthropic`, which the client routes through its Messages adapter.
PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": [
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5",
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [
            "anthropic/claude-sonnet-5",
            "openai/gpt-5.2",
            "google/gemini-2.5-pro",
            "deepseek/deepseek-chat-v3.1",
            "meta-llama/llama-4-maverick",
        ],
    },
    "ollama-cloud": {
        "label": "Ollama Cloud",
        "base_url": "https://ollama.com/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "models": [
            "gpt-oss:120b",
            "gpt-oss:20b",
            "deepseek-v3.1:671b",
            "qwen3-coder:480b",
            "kimi-k2:1t",
        ],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models": [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
    },
    "deepinfra": {
        "label": "DeepInfra",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "api_key_env": "DEEPINFRA_API_KEY",
        "models": [
            "deepseek-ai/DeepSeek-V3.1",
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
            "Qwen/Qwen3-235B-A22B",
        ],
    },
}

# Providers whose id must be mapped onto a provider name the LLM client
# factory understands (everything OpenAI-compatible maps to that preset).
_CLIENT_PROVIDER = {
    "anthropic": "anthropic",
    "openrouter": "openrouter",
    "openai": "openai",
    "ollama-cloud": "openai-compatible",
    "gemini": "openai-compatible",
    "deepinfra": "openai-compatible",
}


class LLMSettingsUpdate(BaseModel):
    provider: str
    model: str
    api_key: str = ""


class LLMModelsRequest(BaseModel):
    provider: str
    api_key: str = ""


def _get_app_state() -> dict[str, Any]:
    from researchclaw.server.app import _app_state

    return _app_state


def _has_key(provider_id: str, config: Any) -> bool:
    info = PROVIDERS[provider_id]
    if os.environ.get(info["api_key_env"], ""):
        return True
    llm = getattr(config, "llm", None)
    return bool(llm and llm.api_key)


def apply_settings(config: Any, provider_id: str, model: str, api_key: str = "") -> Any:
    """Return a new RCConfig with the llm section replaced."""
    info = PROVIDERS[provider_id]
    same_provider = config.llm.api_key_env == info["api_key_env"]
    # Keep a previously stored key when staying on the same provider and no
    # new key was supplied; empty key falls back to the provider's env var.
    effective_key = api_key or (config.llm.api_key if same_provider else "")
    new_llm = dataclasses.replace(
        config.llm,
        provider=_CLIENT_PROVIDER[provider_id],
        base_url=info["base_url"],
        wire_api="chat_completions",
        api_key_env=info["api_key_env"],
        api_key=effective_key,
        primary_model=model,
        fallback_models=(),
    )
    return dataclasses.replace(config, llm=new_llm)


def load_saved_settings() -> dict[str, Any] | None:
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        logger.warning("Could not read %s", SETTINGS_PATH, exc_info=True)
    return None


def _save_settings(data: dict[str, Any]) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data))
    except Exception:
        logger.warning("Could not persist %s", SETTINGS_PATH, exc_info=True)


def _current(config: Any) -> dict[str, Any]:
    saved = load_saved_settings() or {}
    provider_id = saved.get("provider")
    if provider_id not in PROVIDERS:
        # Infer from config
        provider_id = next(
            (
                pid
                for pid, info in PROVIDERS.items()
                if info["api_key_env"] == config.llm.api_key_env
            ),
            "openai",
        )
    return {
        "provider": provider_id,
        "model": config.llm.primary_model,
        "has_api_key": _has_key(provider_id, config),
    }


def _caller_bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""


def _auth_enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))


def _caller_email(request: Request) -> str:
    from researchclaw.server import papers_store

    return papers_store.owner_email(_caller_bearer(request))


def resolve_request_config(config: Any, request: Request) -> Any:
    """Per-user LLM: apply the requesting user's stored provider/model/key."""
    if not _auth_enabled():
        return config
    from researchclaw.server import papers_store

    email = _caller_email(request)
    user_llm = papers_store.get_user_llm(email) if email else None
    if user_llm and user_llm["provider"] in PROVIDERS and user_llm["model"]:
        return apply_settings(
            config, user_llm["provider"], user_llm["model"], user_llm["api_key"]
        )
    return config


@router.get("/api/llm/settings")
async def get_llm_settings(request: Request) -> dict[str, Any]:
    state = _get_app_state()
    config = state["config"]

    if _auth_enabled():
        import asyncio as _aio

        def _user_row() -> dict | None:
            import urllib.parse as _up
            import urllib.request as _ur

            token = _caller_bearer(request)
            if not token:
                return None
            from researchclaw.server import papers_store

            email = papers_store.owner_email(token)
            if not email:
                return None
            url = os.environ["SUPABASE_URL"].rstrip("/")
            req2 = _ur.Request(
                f"{url}/rest/v1/e5o_users?select=llm_provider,llm_model,llm_key_secret&email=eq.{_up.quote(email)}&limit=1",
                headers={"apikey": os.environ["SUPABASE_ANON_KEY"],
                         "Authorization": f"Bearer {token}", "User-Agent": "researchclaw"},
            )
            with _ur.urlopen(req2, timeout=15) as resp:
                rows = json.loads(resp.read().decode())
            return rows[0] if isinstance(rows, list) and rows else None

        try:
            row = await _aio.to_thread(_user_row)
        except Exception:
            row = None
        if row and row.get("llm_provider") in PROVIDERS:
            provider_id = row["llm_provider"]
            return {
                "current": {
                    "provider": provider_id,
                    "model": row.get("llm_model") or "",
                    "has_api_key": bool(row.get("llm_key_secret")) or _has_key(provider_id, config),
                },
                "providers": [
                    {
                        "id": pid,
                        "label": info["label"],
                        "models": info["models"],
                        "api_key_env": info["api_key_env"],
                        "has_api_key": (pid == provider_id and bool(row.get("llm_key_secret"))) or _has_key(pid, config),
                    }
                    for pid, info in PROVIDERS.items()
                ],
            }

    return {
        "current": _current(config),
        "providers": [
            {
                "id": pid,
                "label": info["label"],
                "models": info["models"],
                "api_key_env": info["api_key_env"],
                "has_api_key": _has_key(pid, config),
            }
            for pid, info in PROVIDERS.items()
        ],
    }


@router.post("/api/llm/settings")
async def set_llm_settings(update: LLMSettingsUpdate, request: Request) -> dict[str, Any]:
    if update.provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {update.provider}")
    if not update.model.strip():
        raise HTTPException(400, "Model is required")

    if _auth_enabled():
        # Per-user: store choice (and key, in Vault) on the caller's own row
        import asyncio as _aio
        import urllib.request as _ur

        token = _caller_bearer(request)

        def _save() -> None:
            url = os.environ["SUPABASE_URL"].rstrip("/")
            body = json.dumps({
                "p_provider": update.provider,
                "p_model": update.model.strip(),
                "p_api_key": update.api_key.strip() or None,
            }).encode()
            req2 = _ur.Request(
                f"{url}/rest/v1/rpc/e5o_save_my_llm",
                data=body, method="POST",
                headers={"apikey": os.environ["SUPABASE_ANON_KEY"],
                         "Authorization": f"Bearer {token}",
                         "Content-Type": "application/json", "User-Agent": "researchclaw"},
            )
            _ur.urlopen(req2, timeout=20).read()

        try:
            await _aio.to_thread(_save)
        except Exception as exc:
            raise HTTPException(500, f"Could not save settings: {exc}")
        return {"ok": True, "current": {"provider": update.provider,
                                        "model": update.model.strip(), "has_api_key": True}}

    state = _get_app_state()
    config = state["config"]
    new_config = apply_settings(config, update.provider, update.model.strip(), update.api_key.strip())
    state["config"] = new_config

    # Persist so a restart keeps the choice (key stored only if user provided one).
    _save_settings(
        {
            "provider": update.provider,
            "model": update.model.strip(),
            **({"api_key": update.api_key.strip()} if update.api_key.strip() else {}),
        }
    )
    return {"ok": True, "current": _current(new_config)}


def _resolve_key(provider_id: str, api_key: str, config: Any) -> str:
    """Explicit key > stored key (same provider) > provider env var."""
    if api_key:
        return api_key
    info = PROVIDERS[provider_id]
    if config.llm.api_key_env == info["api_key_env"] and config.llm.api_key:
        return config.llm.api_key
    return os.environ.get(info["api_key_env"], "")


def _fetch_provider_models(provider_id: str, api_key: str) -> list[str]:
    """List every model the provider account can use (live API call)."""
    import urllib.request

    info = PROVIDERS[provider_id]
    if provider_id == "anthropic":
        url = "https://api.anthropic.com/v1/models?limit=1000"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        url = info["base_url"].rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    headers["User-Agent"] = "researchclaw"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())

    models: list[str] = []
    for item in payload.get("data", []):
        mid = item.get("id") or item.get("name") or ""
        if mid.startswith("models/"):  # Gemini prefixes ids
            mid = mid[len("models/"):]
        if mid:
            models.append(mid)
    return sorted(set(models), key=str.lower)


@router.post("/api/llm/models")
async def list_llm_models(req: LLMModelsRequest, request: Request) -> dict[str, Any]:
    """Validate the key by fetching the provider's full model list."""
    import asyncio
    import urllib.error

    if req.provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {req.provider}")

    state = _get_app_state()
    config_for_keys = await asyncio.to_thread(resolve_request_config, state["config"], request)
    key = _resolve_key(req.provider, req.api_key.strip(), config_for_keys)
    if not key:
        return {
            "ok": False,
            "error": f"No API key — enter one or set {PROVIDERS[req.provider]['api_key_env']} on the server.",
        }

    try:
        models = await asyncio.to_thread(_fetch_provider_models, req.provider, key)
        return {"ok": True, "models": models, "count": len(models)}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()[:300]
        except Exception:
            pass
        if exc.code in (401, 403):
            return {"ok": False, "error": f"Key rejected by provider (HTTP {exc.code}). {detail}"}
        return {"ok": False, "error": f"Provider returned HTTP {exc.code}. {detail}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


@router.post("/api/llm/test")
async def test_llm_settings(request: Request) -> dict[str, Any]:
    """Fire a one-token test request at the configured provider."""
    import asyncio

    state = _get_app_state()
    config = await asyncio.to_thread(resolve_request_config, state["config"], request)

    def _probe() -> dict[str, Any]:
        from researchclaw.llm.client import LLMClient

        client = LLMClient.from_rc_config(config)
        resp = client.chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=20,
        )
        return {"ok": True, "model": resp.model, "reply": resp.content[:100]}

    try:
        return await asyncio.to_thread(_probe)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}
