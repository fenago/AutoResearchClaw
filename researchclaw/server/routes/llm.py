"""LLM provider/model selection endpoints for the dashboard Settings view."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
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


@router.get("/api/llm/settings")
async def get_llm_settings() -> dict[str, Any]:
    state = _get_app_state()
    config = state["config"]
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
async def set_llm_settings(update: LLMSettingsUpdate) -> dict[str, Any]:
    if update.provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {update.provider}")
    if not update.model.strip():
        raise HTTPException(400, "Model is required")

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


@router.post("/api/llm/test")
async def test_llm_settings() -> dict[str, Any]:
    """Fire a one-token test request at the configured provider."""
    import asyncio

    state = _get_app_state()
    config = state["config"]

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
