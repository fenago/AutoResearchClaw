"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

# WebSocket must be importable at module level: with `from __future__ import
# annotations`, FastAPI resolves the endpoint's string annotations against
# module globals — a function-local import makes it misparse the websocket
# param as a required query field and reject every connection (403/1008).
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from researchclaw.config import RCConfig
from researchclaw.server.middleware.auth import TokenAuthMiddleware
from researchclaw.server.websocket.manager import ConnectionManager
from researchclaw.server.websocket.events import Event, EventType

logger = logging.getLogger(__name__)

# Shared application state accessible by routes
_app_state: dict[str, Any] = {}


def create_app(
    config: RCConfig,
    *,
    dashboard_only: bool = False,
    monitor_dir: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: ResearchClaw configuration.
        dashboard_only: If True, only mount dashboard routes.
        monitor_dir: Specific run directory to monitor.
    """
    app = FastAPI(
        title="ResearchClaw",
        description="Autonomous Research Pipeline — Web Interface",
        version="0.5.0",
    )

    # Store config in shared state
    _app_state["config"] = config
    _app_state["monitor_dir"] = monitor_dir

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.server.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Token auth ---
    if config.server.auth_token:
        app.add_middleware(TokenAuthMiddleware, token=config.server.auth_token)

    # --- Supabase multi-user auth (enabled via env) ---
    import os as _os

    _supabase_url = _os.environ.get("SUPABASE_URL", "")
    _supabase_anon = _os.environ.get("SUPABASE_ANON_KEY", "")
    if _supabase_url and _supabase_anon:
        from researchclaw.server.middleware.supabase_auth import SupabaseAuthMiddleware

        app.add_middleware(
            SupabaseAuthMiddleware,
            supabase_url=_supabase_url,
            anon_key=_supabase_anon,
            allowlist_table=_os.environ.get("AUTH_ALLOWLIST_TABLE", "e5o_users"),
        )
        logger.info("Supabase auth enabled (allowlist: %s)",
                    _os.environ.get("AUTH_ALLOWLIST_TABLE", "e5o_users"))

    @app.get("/api/auth/config")
    async def auth_config() -> dict[str, Any]:
        """Public endpoint the frontend uses to decide whether to show login."""
        return {
            "enabled": bool(_supabase_url and _supabase_anon),
            "url": _supabase_url,
            "anon_key": _supabase_anon,
        }

    # --- WebSocket manager ---
    event_manager = ConnectionManager()
    _app_state["event_manager"] = event_manager

    # --- Health endpoint ---
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.5.0",
            "active_connections": event_manager.active_count,
        }

    @app.get("/api/config")
    async def config_summary() -> dict[str, Any]:
        return {
            "project": config.project.name,
            "topic": config.research.topic,
            "mode": config.experiment.mode,
            "server": {
                "voice_enabled": config.server.voice_enabled,
                "dashboard_enabled": config.dashboard.enabled,
            },
        }

    # --- Routes ---
    from researchclaw.server.routes.pipeline import router as pipeline_router
    from researchclaw.server.routes.projects import router as projects_router
    from researchclaw.server.routes.llm import (
        PROVIDERS,
        apply_settings,
        load_saved_settings,
        router as llm_router,
    )

    from researchclaw.server.routes.admin import router as admin_router
    from researchclaw.server.routes.paper import router as paper_router

    app.include_router(pipeline_router)
    app.include_router(projects_router)
    app.include_router(llm_router)
    app.include_router(admin_router)
    app.include_router(paper_router)

    # Optional env override for the experiment mode (e.g. "simulated" for
    # lightweight web deployments without Docker/GPU).
    _exp_mode = _os.environ.get("RC_EXPERIMENT_MODE", "")
    if _exp_mode:
        import dataclasses as _dc

        _app_state["config"] = _dc.replace(
            _app_state["config"],
            experiment=_dc.replace(_app_state["config"].experiment, mode=_exp_mode),
        )
        logger.info("Experiment mode overridden via env: %s", _exp_mode)

    # Re-apply a previously saved LLM provider/model choice
    saved_llm = load_saved_settings()
    if saved_llm and saved_llm.get("provider") in PROVIDERS and saved_llm.get("model"):
        _app_state["config"] = apply_settings(
            _app_state["config"],
            saved_llm["provider"],
            saved_llm["model"],
            saved_llm.get("api_key", ""),
        )
        logger.info(
            "Applied saved LLM settings: %s / %s",
            saved_llm["provider"],
            saved_llm["model"],
        )

    if not dashboard_only:
        from researchclaw.server.routes.chat import router as chat_router, set_chat_manager

        set_chat_manager(event_manager)
        app.include_router(chat_router)

        if config.server.voice_enabled:
            from researchclaw.server.routes.voice import router as voice_router

            app.include_router(voice_router)

    # --- WebSocket events endpoint ---
    import uuid

    @app.websocket("/ws/events")
    async def events_ws(websocket: WebSocket) -> None:
        """Real-time event stream for dashboard."""
        client_id = f"evt-{uuid.uuid4().hex[:8]}"
        await event_manager.connect(websocket, client_id)
        try:
            while True:
                # Keep connection alive; client can send pings
                await websocket.receive_text()
        except WebSocketDisconnect:
            event_manager.disconnect(client_id)

    # --- Static marketing/docs website (public) ---
    website_dir = Path(__file__).resolve().parent.parent.parent / "website"
    if website_dir.is_dir():
        app.mount("/site", StaticFiles(directory=str(website_dir), html=True), name="site")

    # --- Static files (frontend) ---
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        # Serve the dashboard at / and /app. With ROOT_REDIRECT set (e.g.
        # "/site/" to lead with the public website), / redirects instead.
        from fastapi.responses import FileResponse, RedirectResponse

        root_redirect = _os.environ.get("ROOT_REDIRECT", "")

        @app.get("/")
        async def index() -> Any:
            if root_redirect:
                return RedirectResponse(root_redirect)
            return FileResponse(str(frontend_dir / "index.html"))

        @app.get("/app")
        async def app_index() -> FileResponse:
            return FileResponse(str(frontend_dir / "index.html"))

    # --- Background tasks ---
    @app.on_event("startup")
    async def startup() -> None:
        asyncio.create_task(event_manager.heartbeat_loop(interval=15.0))

        if config.dashboard.enabled:
            from researchclaw.dashboard.broadcaster import start_dashboard_loop

            asyncio.create_task(
                start_dashboard_loop(
                    event_manager,
                    interval=config.dashboard.refresh_interval_sec,
                    monitor_dir=monitor_dir,
                )
            )
        logger.info("ResearchClaw Web server started")

    return app
