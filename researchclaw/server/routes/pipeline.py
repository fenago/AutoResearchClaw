"""Pipeline control API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

import re as _re
_RUN_ID_RE = _re.compile(r"^rc-\d{8}-\d{6}-[a-f0-9]+$")


def _validated_run_dir(run_id: str) -> Path:
    """Validate run_id format and return the run directory path."""
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail=f"Invalid run_id format: {run_id}")
    run_dir = Path("artifacts") / run_id
    # Ensure resolved path is under artifacts/
    if not run_dir.resolve().is_relative_to(Path("artifacts").resolve()):
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {run_id}")
    return run_dir

router = APIRouter(prefix="/api", tags=["pipeline"])


class PipelineStartRequest(BaseModel):
    """Request body for starting a pipeline run."""

    topic: str | None = None
    config_overrides: dict[str, Any] | None = None
    auto_approve: bool = True
    title: str | None = None
    plan: dict[str, Any] | None = None


class PipelineStartResponse(BaseModel):
    """Response after starting a pipeline."""

    run_id: str
    status: str
    output_dir: str


# In-memory tracking of the active run (single-tenant MVP)
_active_run: dict[str, Any] | None = None
_run_task: asyncio.Task[Any] | None = None
_run_lock = asyncio.Lock()


def _get_app_state() -> dict[str, Any]:
    """Get shared application state (set by app.py)."""
    from researchclaw.server.app import _app_state
    return _app_state


def _new_run_id(topic: str) -> str:
    import hashlib
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"rc-{ts}-{hashlib.sha256(topic.encode()).hexdigest()[:6]}"


def _apply_topic(config: Any, topic: str | None) -> Any:
    if not topic:
        return config
    import dataclasses

    new_research = dataclasses.replace(config.research, topic=topic)
    return dataclasses.replace(config, research=new_research)


async def _launch_run(
    run_id: str,
    config: Any,
    *,
    owner_email: str = "",
    title: str | None = None,
    plan: dict | None = None,
    from_stage: Any = None,
    preload_log: list | None = None,
    preload_files: dict | None = None,
    persist_start: bool = True,
) -> None:
    """Start (or resume) a pipeline run in the background. Caller holds _run_lock."""
    global _active_run, _run_task

    state = _get_app_state()
    run_dir = _validated_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    _active_run = {
        "run_id": run_id,
        "status": "running",
        "output_dir": str(run_dir),
        "topic": config.research.topic,
        "owner": owner_email,
    }

    from researchclaw.server import papers_store

    if papers_store.enabled() and persist_start:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: papers_store.upsert_paper(
                run_id,
                owner_email=owner_email or "unknown",
                title=title or config.research.topic,
                topic=config.research.topic,
                plan=plan,
                status="running",
            ),
        )

    from researchclaw.server.run_watcher import RunWatcher
    from researchclaw.server.websocket.events import Event, EventType

    event_manager = state.get("event_manager")

    def _broadcast_stage(data: dict) -> None:
        if event_manager:
            event_manager.publish(Event(type=EventType.STAGE_COMPLETE, data=data))

    watcher = RunWatcher(run_id, run_dir, config, broadcast=_broadcast_stage)
    if preload_log or preload_files:
        watcher.preload(preload_log, preload_files)
    watcher.start()
    _active_run["watcher"] = watcher

    async def _run_in_background() -> None:
        global _active_run
        final_status = "failed"
        try:
            from researchclaw.adapters import AdapterBundle
            from researchclaw.pipeline.runner import Stage, execute_pipeline

            kb_root = Path(config.knowledge_base.root) if config.knowledge_base.root else None
            if kb_root:
                kb_root.mkdir(parents=True, exist_ok=True)

            kwargs: dict[str, Any] = {}
            if from_stage is not None:
                kwargs["from_stage"] = from_stage

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: execute_pipeline(
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=AdapterBundle(),
                    auto_approve_gates=True,
                    skip_noncritical=True,
                    kb_root=kb_root,
                    **kwargs,
                ),
            )
            done = sum(1 for r in results if r.status.value == "done")
            failed = sum(1 for r in results if r.status.value == "failed")
            final_status = "completed" if failed == 0 else "failed"
            if _active_run:
                _active_run["status"] = final_status
                _active_run["stages_done"] = done
                _active_run["stages_failed"] = failed
            watcher.stop()
            try:
                await watcher.finalize()
            except Exception:
                logger.debug("watcher finalize failed", exc_info=True)
            if papers_store.enabled():
                deliverables = papers_store.collect_deliverables(run_dir)
                papers_store.upsert_paper(run_id, status=final_status, **deliverables)
        except Exception as exc:
            logger.exception("Pipeline run failed")
            if _active_run:
                _active_run["status"] = "failed"
                _active_run["error"] = str(exc)
            watcher.stop()
            if papers_store.enabled():
                papers_store.upsert_paper(run_id, status="failed", error=str(exc)[:500])

        # Completion email (no-op unless RESEND_API_KEY is configured)
        try:
            from researchclaw.server import notify

            notify.paper_finished(owner_email, title or config.research.topic, run_id, final_status)
        except Exception:
            logger.debug("completion notification failed", exc_info=True)

        # Start the next queued paper, if any
        try:
            await _drain_queue()
        except Exception:
            logger.warning("queue drain failed", exc_info=True)

    _run_task = asyncio.create_task(_run_in_background())


def _owner_config(owner_email: str) -> Any:
    """Build the run config for a user by email (their model + key, env fallback)."""
    state = _get_app_state()
    config = state["config"]
    try:
        from researchclaw.server import papers_store
        from researchclaw.server.routes.llm import PROVIDERS, apply_settings

        user_llm = papers_store.get_user_llm(owner_email) if owner_email else None
        if user_llm and user_llm["provider"] in PROVIDERS and user_llm["model"]:
            return apply_settings(config, user_llm["provider"], user_llm["model"], user_llm["api_key"])
    except Exception:
        logger.warning("could not resolve owner LLM config", exc_info=True)
    return config


async def _drain_queue() -> None:
    """If idle, start the oldest queued paper."""
    from researchclaw.server import papers_store

    if not papers_store.enabled():
        return
    async with _run_lock:
        if _active_run and _active_run.get("status") == "running":
            return
        work = await asyncio.get_event_loop().run_in_executor(None, papers_store.get_active_work)
        queued = [w for w in work if w.get("status") == "queued"]
        if not queued:
            return
        nxt = queued[0]
        owner = nxt.get("owner_email") or ""
        config = _apply_topic(_owner_config(owner), nxt.get("topic"))
        logger.info("Starting queued paper %s for %s", nxt["run_id"], owner)
        await _launch_run(
            nxt["run_id"], config,
            owner_email=owner, title=nxt.get("title"), plan=nxt.get("plan"),
        )


async def resume_and_drain() -> None:
    """At startup: resume runs interrupted by the previous container, then drain."""
    from researchclaw.server import papers_store

    if not papers_store.enabled():
        return
    work = await asyncio.get_event_loop().run_in_executor(None, papers_store.get_active_work)
    running = [w for w in work if w.get("status") == "running"]

    async with _run_lock:
        for row in running:
            run_id = row["run_id"]
            run_files = row.get("run_files") or {}
            if _active_run is None and run_files:
                try:
                    run_dir = _validated_run_dir(run_id)
                    run_dir.mkdir(parents=True, exist_ok=True)
                    restored = papers_store.restore_run_dir(run_dir, run_files)
                    from researchclaw.pipeline.runner import read_checkpoint

                    next_stage = read_checkpoint(run_dir)
                    owner = row.get("owner_email") or ""
                    config = _apply_topic(_owner_config(owner), row.get("topic"))
                    logger.info(
                        "Resuming run %s from %s (%d files restored)",
                        run_id, next_stage, restored,
                    )
                    await _launch_run(
                        run_id, config,
                        owner_email=owner, title=row.get("title"), plan=row.get("plan"),
                        from_stage=next_stage,
                        preload_log=row.get("stage_log"), preload_files=run_files,
                        persist_start=False,
                    )
                    continue
                except Exception:
                    logger.exception("Resume failed for %s", run_id)
            # Could not resume (no snapshot, resume error, or a run already active)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda rid=run_id: papers_store.upsert_paper(
                    rid, status="failed",
                    error='This run was interrupted by a server update and could not be resumed. Click "Try again" to restart it.',
                ),
            )

    await _drain_queue()


@router.post("/pipeline/start", response_model=PipelineStartResponse)
async def start_pipeline(req: PipelineStartRequest, request: Request) -> PipelineStartResponse:
    """Start a new pipeline run — or queue it if one is already running."""
    state = _get_app_state()
    from researchclaw.server import papers_store
    from researchclaw.server.routes.llm import resolve_request_config

    config = await asyncio.get_event_loop().run_in_executor(
        None, resolve_request_config, state["config"], request
    )
    config = _apply_topic(config, req.topic)

    owner = ""
    if papers_store.enabled():
        auth_header = request.headers.get("authorization", "")
        bearer = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
        owner = await asyncio.get_event_loop().run_in_executor(
            None, papers_store.owner_email, bearer
        )

    run_id = _new_run_id(config.research.topic)

    async with _run_lock:
        if _active_run and _active_run.get("status") == "running":
            # Queue it (needs the paper library; without it, keep the old 409)
            if not papers_store.enabled():
                raise HTTPException(status_code=409, detail="A pipeline is already running")
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: papers_store.upsert_paper(
                    run_id,
                    owner_email=owner or "unknown",
                    title=req.title or config.research.topic,
                    topic=config.research.topic,
                    plan=req.plan,
                    status="queued",
                ),
            )
            return PipelineStartResponse(run_id=run_id, status="queued", output_dir="")

        await _launch_run(
            run_id, config,
            owner_email=owner, title=req.title, plan=req.plan,
        )

    return PipelineStartResponse(
        run_id=run_id,
        status="running",
        output_dir=str(_validated_run_dir(run_id)),
    )


@router.post("/pipeline/stop")
async def stop_pipeline() -> dict[str, str]:
    """Stop the currently running pipeline."""
    global _active_run, _run_task

    if not _run_task or not _active_run:
        raise HTTPException(status_code=404, detail="No pipeline is running")

    _run_task.cancel()
    _active_run["status"] = "stopped"
    return {"status": "stopped"}


@router.get("/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    """Get current pipeline run status (with live stage progress)."""
    if not _active_run:
        return {"status": "idle"}
    out = {k: v for k, v in _active_run.items() if k != "watcher"}
    watcher = _active_run.get("watcher")
    if watcher:
        out["progress"] = watcher.snapshot()
    return out


@router.get("/pipeline/stages")
async def pipeline_stages() -> dict[str, Any]:
    """Get the 23-stage pipeline definition."""
    from researchclaw.pipeline.stages import Stage

    stages = []
    for s in Stage:
        stages.append({
            "number": int(s),
            "name": s.name,
            "label": getattr(s, "label", s.name.replace("_", " ").title()),
            "phase": getattr(s, "phase", ""),
        })
    return {"stages": stages}


@router.get("/runs")
async def list_runs() -> dict[str, Any]:
    """List historical pipeline runs from artifacts/ directory."""
    artifacts = Path("artifacts")
    runs: list[dict[str, Any]] = []
    if artifacts.exists():
        for d in sorted(artifacts.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("rc-"):
                info: dict[str, Any] = {"run_id": d.name, "path": str(d)}
                # Try reading checkpoint
                ckpt = d / "checkpoint.json"
                if ckpt.exists():
                    try:
                        with ckpt.open() as f:
                            info["checkpoint"] = json.load(f)
                    except Exception:
                        pass
                runs.append(info)
    return {"runs": runs[:50]}  # limit to 50 most recent


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    """Get details for a specific run."""
    run_dir = _validated_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    info: dict[str, Any] = {"run_id": run_id, "path": str(run_dir)}

    ckpt = run_dir / "checkpoint.json"
    if ckpt.exists():
        try:
            with ckpt.open() as f:
                info["checkpoint"] = json.load(f)
        except Exception:
            pass

    # List stage directories
    stage_dirs = sorted(
        [d.name for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("stage-")]
    )
    info["stages_completed"] = stage_dirs

    # Check for paper
    for pattern in ["paper.md", "paper.tex", "paper.pdf"]:
        found = list(run_dir.rglob(pattern))
        if found:
            info[f"has_{pattern.split('.')[1]}"] = True

    return info


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(run_id: str) -> dict[str, Any]:
    """Get experiment metrics for a run."""
    run_dir = _validated_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    metrics: dict[str, Any] = {}
    results_file = run_dir / "results.json"
    if results_file.exists():
        try:
            with results_file.open() as f:
                metrics = json.load(f)
        except Exception:
            pass

    return {"run_id": run_id, "metrics": metrics}
