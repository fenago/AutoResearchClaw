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
    mode: str = "autopilot"  # "autopilot" | "copilot"


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
    copilot: bool = False,
) -> None:
    """Start (or resume) a pipeline run in the background. Caller holds _run_lock."""
    global _active_run, _run_task
    import threading

    state = _get_app_state()
    run_dir = _validated_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = threading.Event()
    _active_run = {
        "run_id": run_id,
        "status": "running",
        "output_dir": str(run_dir),
        "topic": config.research.topic,
        "owner": owner_email,
        "copilot": copilot,
        "cancel_event": cancel_event,
        "pausing": False,
        "title": title or config.research.topic,
        "plan": plan,
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

            # Co-pilot: pause at decision gates (stages 5, 9, 20) and wait for
            # the owner's approve/reject/adjust via run_dir/hitl/response.json.
            adapters = AdapterBundle()
            if copilot:
                try:
                    from researchclaw.hitl.presets import get_preset
                    from researchclaw.hitl.session import HITLSession

                    hitl_cfg = get_preset("gate-only")
                    session = HITLSession(run_id=run_id, config=hitl_cfg, run_dir=run_dir)
                    adapters = AdapterBundle(hitl=session)
                except Exception:
                    logger.warning("co-pilot HITL wiring failed; running autopilot", exc_info=True)

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: execute_pipeline(
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=adapters,
                    auto_approve_gates=not copilot,
                    skip_noncritical=True,
                    kb_root=kb_root,
                    cancel_event=cancel_event,
                    **kwargs,
                ),
            )
            done = sum(1 for r in results if r.status.value == "done")
            failed = sum(1 for r in results if r.status.value == "failed")
            statuses = [r.status.value for r in results]
            last = results[-1] if results else None
            block_msg = ""
            if _active_run and _active_run.get("pausing"):
                final_status = "paused"
            elif "rejected" in statuses:
                final_status = "stopped"
            elif failed > 0:
                final_status = "failed"
            elif last is not None and last.status.value == "paused":
                # Engine hard-block (e.g. a stage refused to proceed) — surface it
                final_status = "failed"
                block_msg = getattr(last, "error", "") or "The run stopped before finishing."
            elif last is not None and last.status.value == "done" and int(last.stage) >= 23:
                final_status = "completed"
            else:
                final_status = "stopped"
            if _active_run:
                _active_run["status"] = final_status
                _active_run["stages_done"] = done
                _active_run["stages_failed"] = failed
                if block_msg:
                    _active_run["error"] = block_msg
            watcher.stop()
            try:
                await watcher.finalize()
            except Exception:
                logger.debug("watcher finalize failed", exc_info=True)
            if papers_store.enabled():
                deliverables = papers_store.collect_deliverables(run_dir)
                extra = {"error": block_msg[:500]} if block_msg else {}
                papers_store.upsert_paper(run_id, status=final_status, **deliverables, **extra)
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
            copilot=bool((nxt.get("plan") or {}).get("copilot")),
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
        # Per-user monthly run limit (admins exempt). Consume one unit up front.
        if owner:
            remaining = await asyncio.get_event_loop().run_in_executor(
                None, papers_store.consume_run, owner
            )
            if remaining == -1:
                raise HTTPException(
                    status_code=429,
                    detail=(f"You've reached your monthly limit of "
                            f"{papers_store._monthly_run_limit()} papers. It resets on the 1st."),
                )

    run_id = _new_run_id(config.research.topic)
    copilot = req.mode == "copilot"
    # Persist co-pilot choice inside the plan so resume/redo/queue honor it.
    plan = dict(req.plan or {})
    plan["copilot"] = copilot

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
                    plan=plan,
                    status="queued",
                ),
            )
            return PipelineStartResponse(run_id=run_id, status="queued", output_dir="")

        await _launch_run(
            run_id, config,
            owner_email=owner, title=req.title, plan=plan, copilot=copilot,
        )

    return PipelineStartResponse(
        run_id=run_id,
        status="running",
        output_dir=str(_validated_run_dir(run_id)),
    )


_NONSERIALIZABLE = {"watcher", "cancel_event"}


def _waiting_state(run_dir: Path) -> dict | None:
    """Read run_dir/hitl/waiting.json if the run is paused at a gate."""
    wpath = run_dir / "hitl" / "waiting.json"
    if wpath.is_file():
        try:
            return json.loads(wpath.read_text())
        except Exception:
            return None
    return None


@router.post("/pipeline/stop")
async def stop_pipeline() -> dict[str, str]:
    """Stop the currently running pipeline (after the current stage finishes)."""
    global _active_run

    if not _active_run or _active_run.get("status") != "running":
        raise HTTPException(status_code=404, detail="No pipeline is running")

    _active_run["pausing"] = True
    ev = _active_run.get("cancel_event")
    if ev:
        ev.set()
    return {"status": "stopping"}


@router.get("/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    """Get current pipeline run status (with live stage progress)."""
    if not _active_run:
        return {"status": "idle"}
    out = {k: v for k, v in _active_run.items() if k not in _NONSERIALIZABLE}
    watcher = _active_run.get("watcher")
    if watcher:
        out["progress"] = watcher.snapshot()
    run_dir = _validated_run_dir(_active_run["run_id"])
    waiting = _waiting_state(run_dir)
    if waiting:
        out["waiting"] = waiting
    return out


class GateDecision(BaseModel):
    run_id: str
    decision: str  # "approve" | "reject" | "adjust"
    guidance: str = ""


class ResumeRequest(BaseModel):
    run_id: str


class RedoRequest(BaseModel):
    run_id: str
    stage: int
    guidance: str = ""


def _user_bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""


def _fetch_paper_row(request: Request, run_id: str) -> dict:
    """Fetch a paper row via the caller's own token (RLS enforces ownership)."""
    import os
    import urllib.parse
    import urllib.request

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    token = _user_bearer(request)
    if not (url and anon and token):
        raise HTTPException(400, "Paper library is not configured")
    q = f"{url}/rest/v1/e5o_papers?run_id=eq.{urllib.parse.quote(run_id)}&select=*"
    req = urllib.request.Request(
        q, headers={"apikey": anon, "Authorization": f"Bearer {token}",
                    "User-Agent": "researchclaw"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.loads(resp.read().decode())
    if not rows:
        raise HTTPException(404, "Paper not found")
    return rows[0]


@router.get("/me/usage")
async def my_usage(request: Request) -> dict[str, Any]:
    """The caller's monthly paper-run usage (read via their own token/RLS)."""
    import os
    import urllib.parse
    import urllib.request
    from datetime import datetime, timezone

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    limit = int(os.environ.get("E5O_MONTHLY_RUN_LIMIT", "20"))
    token = _user_bearer(request)
    if not (url and anon and token):
        return {"enabled": False, "used": 0, "limit": limit, "remaining": limit, "is_admin": False}

    month = datetime.now(timezone.utc).strftime("%Y-%m")

    def _get(path: str) -> Any:
        req2 = urllib.request.Request(
            url + path,
            headers={"apikey": anon, "Authorization": f"Bearer {token}",
                     "User-Agent": "researchclaw"})
        with urllib.request.urlopen(req2, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _go() -> dict[str, Any]:
        used = 0
        is_admin = False
        try:
            urows = _get("/rest/v1/e5o_users?select=is_admin&limit=1")
            if isinstance(urows, list) and urows:
                is_admin = bool(urows[0].get("is_admin"))
            rrows = _get(
                f"/rest/v1/e5o_run_usage?select=count&month=eq.{urllib.parse.quote(month)}")
            if isinstance(rrows, list) and rrows:
                used = int(rrows[0].get("count", 0))
        except Exception:
            logger.debug("usage read failed", exc_info=True)
        return {
            "enabled": True, "used": used, "limit": limit,
            "remaining": (999999 if is_admin else max(0, limit - used)),
            "is_admin": is_admin,
        }

    return await asyncio.get_event_loop().run_in_executor(None, _go)


@router.post("/pipeline/gate")
async def pipeline_gate(req: GateDecision, request: Request) -> dict[str, Any]:
    """Answer a co-pilot decision gate: approve / reject / adjust (with guidance)."""
    if not _active_run or _active_run.get("run_id") != req.run_id:
        raise HTTPException(409, "This paper is not currently waiting for a decision.")
    run_dir = _validated_run_dir(req.run_id)
    hitl_dir = run_dir / "hitl"
    hitl_dir.mkdir(parents=True, exist_ok=True)

    waiting = _waiting_state(run_dir) or {}
    stage_num = waiting.get("stage")

    def _write() -> None:
        import os
        import tempfile

        if req.decision == "adjust" and req.guidance.strip() and stage_num:
            # Guidance in the current gate stage dir is auto-injected into every
            # downstream stage's prompt, then we approve to continue.
            sd = run_dir / f"stage-{int(stage_num):02d}"
            sd.mkdir(parents=True, exist_ok=True)
            existing = ""
            gp = sd / "hitl_guidance.md"
            if gp.is_file():
                existing = gp.read_text() + "\n\n"
            gp.write_text(existing + "Director's guidance: " + req.guidance.strip())
            action = {"action": "approve", "message": "Approved with guidance"}
        elif req.decision == "reject":
            action = {"action": "reject", "message": req.guidance.strip() or "Rejected"}
        else:
            action = {"action": "approve", "message": req.guidance.strip() or "Approved"}

        # atomic write so the poller never reads a half-written file
        fd, tmp = tempfile.mkstemp(dir=hitl_dir, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(action))
        os.replace(tmp, hitl_dir / "response.json")

    await asyncio.get_event_loop().run_in_executor(None, _write)
    return {"ok": True, "decision": req.decision}


async def _restore_and_launch(row: dict, from_stage_num: int | None, guidance: str = "") -> None:
    """Restore a paper's run dir from the library and (re)launch it. Holds _run_lock."""
    from researchclaw.server import papers_store
    from researchclaw.pipeline.runner import Stage, read_checkpoint

    run_id = row["run_id"]
    owner = row.get("owner_email") or ""
    run_files = row.get("run_files") or {}
    run_dir = _validated_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Restore snapshot if the run dir is empty (e.g. after a deploy)
    if run_files and not any(run_dir.glob("stage-*")):
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: papers_store.restore_run_dir(run_dir, run_files))

    if from_stage_num is not None:
        from_stage = Stage(from_stage_num)
        # Optional steering: drop guidance into the stage dir (auto-injected downstream)
        if guidance.strip():
            sd = run_dir / f"stage-{from_stage_num:02d}"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "hitl_guidance.md").write_text("Director's guidance: " + guidance.strip())
    else:
        from_stage = read_checkpoint(run_dir) or Stage.TOPIC_INIT

    config = _apply_topic(_owner_config(owner), row.get("topic"))
    await _launch_run(
        run_id, config,
        owner_email=owner, title=row.get("title"), plan=row.get("plan"),
        from_stage=from_stage,
        preload_log=row.get("stage_log"), preload_files=run_files,
        persist_start=True,
        copilot=bool(row.get("plan", {}) and (row["plan"] or {}).get("copilot")),
    )


@router.post("/pipeline/resume")
async def pipeline_resume(req: ResumeRequest, request: Request) -> dict[str, Any]:
    """Resume a paused/stopped paper from its last checkpoint."""
    row = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _fetch_paper_row(request, req.run_id))
    async with _run_lock:
        if _active_run and _active_run.get("status") == "running":
            raise HTTPException(409, "Another paper is being written right now.")
        await _restore_and_launch(row, None)
    return {"ok": True, "status": "running"}


@router.post("/pipeline/redo")
async def pipeline_redo(req: RedoRequest, request: Request) -> dict[str, Any]:
    """Re-run a paper from a chosen stage, optionally with new direction."""
    if req.stage < 1 or req.stage > 23:
        raise HTTPException(400, "Stage must be 1-23")
    row = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _fetch_paper_row(request, req.run_id))
    async with _run_lock:
        if _active_run and _active_run.get("status") == "running":
            raise HTTPException(409, "Another paper is being written right now.")
        await _restore_and_launch(row, req.stage, req.guidance)
    return {"ok": True, "status": "running", "from_stage": req.stage}


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
