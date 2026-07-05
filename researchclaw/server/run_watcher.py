"""Live run watcher: turns stage directories into human-readable progress.

Polls the run directory while a pipeline executes. When a stage completes,
its outputs are summarized (via the run's LLM) into one plain-English line,
broadcast over the events WebSocket, and persisted to the paper library.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Present-tense activity lines shown while a stage is running.
DOING: dict[str, str] = {
    "TOPIC_INIT": "Reading your idea, sharpening the research goal, and sizing up the available compute",
    "PROBLEM_DECOMPOSE": "Splitting the big question into concrete, testable sub-questions",
    "SEARCH_STRATEGY": "Choosing search queries and sources to sweep the literature",
    "LITERATURE_COLLECT": "Querying arXiv, OpenAlex, and Semantic Scholar and gathering candidate papers",
    "LITERATURE_SCREEN": "Reading abstracts and scoring each paper's relevance",
    "KNOWLEDGE_EXTRACT": "Pulling key findings, methods, and numbers out of the shortlisted papers",
    "SYNTHESIS": "Connecting the findings into a picture of what's known and where the gaps are",
    "HYPOTHESIS_GEN": "Debating candidate hypotheses from multiple angles and picking the strongest",
    "EXPERIMENT_DESIGN": "Designing experiments that can actually confirm or refute the hypothesis",
    "CODE_GENERATION": "Writing the experiment code",
    "RESOURCE_PLANNING": "Budgeting compute and runtime for the experiment plan",
    "EXPERIMENT_RUN": "Executing the experiments and logging every result",
    "ITERATIVE_REFINE": "Adjusting parameters and re-running where results look unstable",
    "RESULT_ANALYSIS": "Crunching the results and testing them against the hypothesis",
    "RESEARCH_DECISION": "Deciding whether to proceed, refine, or pivot based on the evidence",
    "PAPER_OUTLINE": "Structuring the paper section by section",
    "PAPER_DRAFT": "Writing the full draft with figures and citations",
    "PEER_REVIEW": "Running a multi-reviewer critique of the draft",
    "PAPER_REVISION": "Rewriting weak sections based on the reviews",
    "QUALITY_GATE": "Checking claims against evidence and hunting for inconsistencies",
    "KNOWLEDGE_ARCHIVE": "Filing what was learned for future runs",
    "EXPORT_PUBLISH": "Producing the final LaTeX, bibliography, and deliverables",
    "CITATION_VERIFY": "Cross-checking every citation against the collected literature",
}

# Ordered stage catalog with end-user labels and phase grouping.
STAGES: list[dict[str, str]] = [
    {"key": "TOPIC_INIT", "label": "Understanding your idea", "phase": "Scoping"},
    {"key": "PROBLEM_DECOMPOSE", "label": "Breaking it into research questions", "phase": "Scoping"},
    {"key": "SEARCH_STRATEGY", "label": "Planning the literature search", "phase": "Literature"},
    {"key": "LITERATURE_COLLECT", "label": "Collecting papers", "phase": "Literature"},
    {"key": "LITERATURE_SCREEN", "label": "Screening for relevance", "phase": "Literature"},
    {"key": "KNOWLEDGE_EXTRACT", "label": "Extracting key findings", "phase": "Literature"},
    {"key": "SYNTHESIS", "label": "Synthesizing what's known", "phase": "Hypothesis"},
    {"key": "HYPOTHESIS_GEN", "label": "Forming the hypothesis", "phase": "Hypothesis"},
    {"key": "EXPERIMENT_DESIGN", "label": "Designing the experiments", "phase": "Experiments"},
    {"key": "CODE_GENERATION", "label": "Writing the experiment code", "phase": "Experiments"},
    {"key": "RESOURCE_PLANNING", "label": "Planning compute resources", "phase": "Experiments"},
    {"key": "EXPERIMENT_RUN", "label": "Running the experiments", "phase": "Experiments"},
    {"key": "ITERATIVE_REFINE", "label": "Refining the experiments", "phase": "Experiments"},
    {"key": "RESULT_ANALYSIS", "label": "Analyzing the results", "phase": "Analysis"},
    {"key": "RESEARCH_DECISION", "label": "Deciding how to proceed", "phase": "Analysis"},
    {"key": "PAPER_OUTLINE", "label": "Outlining the paper", "phase": "Writing"},
    {"key": "PAPER_DRAFT", "label": "Writing the draft", "phase": "Writing"},
    {"key": "PEER_REVIEW", "label": "Running peer review", "phase": "Writing"},
    {"key": "PAPER_REVISION", "label": "Revising the paper", "phase": "Writing"},
    {"key": "QUALITY_GATE", "label": "Final quality checks", "phase": "Finalizing"},
    {"key": "KNOWLEDGE_ARCHIVE", "label": "Archiving what was learned", "phase": "Finalizing"},
    {"key": "EXPORT_PUBLISH", "label": "Exporting the deliverables", "phase": "Finalizing"},
    {"key": "CITATION_VERIFY", "label": "Verifying every citation", "phase": "Finalizing"},
]

_STAGE_INDEX = {s["key"]: i for i, s in enumerate(STAGES)}
_MAX_SUMMARY_INPUT = 8_000

_SUMMARY_PROMPT = (
    "You are narrating an autonomous research run to the paper's owner (a smart "
    "non-technical person). A pipeline stage named '{label}' just finished. Below "
    "are excerpts of what it produced. Reply with ONE or TWO short plain-English "
    "sentences describing concretely what was accomplished (mention real specifics "
    "like counts, titles, or decisions when visible). No preamble, no markdown.\n\n{content}"
)


def _stage_key_from_dir(name: str) -> str | None:
    """stage-03 (or stage-03-search_strategy) -> the stage key by number."""
    m = re.match(r"stage-(\d+)", name)
    if not m:
        return None
    idx = int(m.group(1)) - 1
    return STAGES[idx]["key"] if 0 <= idx < len(STAGES) else None


def _stage_excerpt(stage_dir: Path) -> str:
    parts: list[str] = []
    total = 0
    for path in sorted(stage_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt", ".tex", ".csv"}:
            continue
        try:
            text = path.read_text(errors="replace")[:2500]
        except Exception:
            continue
        parts.append(f"--- {path.name} ---\n{text}")
        total += len(text)
        if total > _MAX_SUMMARY_INPUT:
            break
    return "\n\n".join(parts)[:_MAX_SUMMARY_INPUT]


class RunWatcher:
    """Watches one run directory and narrates stage completions."""

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        config: Any,
        broadcast: Callable[[dict], Any] | None = None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.config = config
        self.broadcast = broadcast
        self.stage_log: list[dict[str, Any]] = []
        self.run_files: dict[str, dict[str, str]] = {}
        self._summarized: set[str] = set()
        self._task: asyncio.Task | None = None

    def preload(self, stage_log: list | None, run_files: dict | None) -> None:
        """Reattach after a resume: carry forward prior narration and files."""
        self.stage_log = list(stage_log or [])
        self.run_files = dict(run_files or {})
        self._summarized = {e["key"] for e in self.stage_log}

    # -- public snapshot used by /api/pipeline/status and the paper page --
    def snapshot(self) -> dict[str, Any]:
        import time as _time

        seen = {e["key"] for e in self.stage_log}
        current = self._current_stage_key()
        stages = []
        for s in STAGES:
            state = "done" if s["key"] in seen else "pending"
            if s["key"] == current and current not in seen:
                state = "active"
            entry = next((e for e in self.stage_log if e["key"] == s["key"]), None)
            stages.append({**s, "state": state, "summary": (entry or {}).get("summary")})

        # Live activity inside the current stage: recent files + elapsed time
        activity: list[dict[str, Any]] = []
        stage_started: float | None = None
        dirs = self._stage_dirs()
        if dirs:
            cur_dir = dirs[-1][1]
            try:
                stage_started = cur_dir.stat().st_ctime
                now = _time.time()
                files = [f for f in cur_dir.rglob("*") if f.is_file()]
                files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                for f in files[:6]:
                    activity.append({
                        "file": f.name,
                        "ago": max(0, int(now - f.stat().st_mtime)),
                    })
            except Exception:
                pass

        done = len([x for x in stages if x["state"] == "done"])
        return {
            "stages": stages,
            "current": current,
            "doing": DOING.get(current or "", ""),
            "log": self.stage_log,
            "done": done,
            "total": len(STAGES),
            "percent": round(done * 100 / len(STAGES)),
            "stage_started": stage_started,
            "activity": activity,
        }

    def _stage_dirs(self) -> list[tuple[str, Path]]:
        out = []
        try:
            for d in sorted(self.run_dir.iterdir()):
                if d.is_dir() and d.name.startswith("stage-"):
                    key = _stage_key_from_dir(d.name)
                    if key:
                        out.append((key, d))
        except Exception:
            pass
        out.sort(key=lambda kv: _STAGE_INDEX.get(kv[0], 99))
        return out

    def _current_stage_key(self) -> str | None:
        dirs = self._stage_dirs()
        return dirs[-1][0] if dirs else (STAGES[0]["key"] if self.run_dir.exists() else None)

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(8)
                await self._tick(final=False)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("run watcher crashed", exc_info=True)

    async def finalize(self) -> None:
        """Summarize anything left (called when the run ends)."""
        self._final = True
        await self._tick(final=True)

    async def _tick(self, final: bool) -> None:
        dirs = self._stage_dirs()
        # A stage is complete when a later stage dir exists (or the run ended).
        for idx, (key, path) in enumerate(dirs):
            is_last = idx == len(dirs) - 1
            if key in self._summarized or (is_last and not final):
                continue
            summary = await asyncio.to_thread(self._summarize, key, path)
            self._summarized.add(key)
            # Snapshot this stage's files (plus run-root state) so the run can
            # be resumed if the container is replaced mid-run.
            try:
                from researchclaw.server import papers_store

                self.run_files[path.name] = await asyncio.to_thread(
                    papers_store.capture_dir_files, path
                )
                root_files: dict[str, str] = {}
                for name in ("checkpoint.json", "goal.md", "hardware_profile.json"):
                    f = self.run_dir / name
                    if f.is_file():
                        try:
                            root_files[name] = f.read_text(errors="replace")
                        except Exception:
                            pass
                self.run_files["_root"] = root_files
            except Exception:
                logger.debug("stage file capture failed", exc_info=True)
            entry = {
                "key": key,
                "label": STAGES[_STAGE_INDEX[key]]["label"],
                "phase": STAGES[_STAGE_INDEX[key]]["phase"],
                "index": _STAGE_INDEX[key] + 1,
                "summary": summary,
            }
            self.stage_log.append(entry)
            self._persist()
            self._emit(entry)

    def _summarize(self, key: str, stage_dir: Path) -> str:
        label = STAGES[_STAGE_INDEX[key]]["label"]
        excerpt = _stage_excerpt(stage_dir)
        if not excerpt:
            return f"{label} finished."
        try:
            from researchclaw.llm.client import LLMClient

            client = LLMClient.from_rc_config(self.config)
            resp = client.chat(
                [{"role": "user", "content": _SUMMARY_PROMPT.format(label=label, content=excerpt)}],
                max_tokens=1400,
                strip_thinking=True,
            )
            text = (resp.content or "").strip()
            return text[:500] if text else f"{label} finished."
        except Exception:
            logger.debug("stage summary LLM call failed", exc_info=True)
            return f"{label} finished."

    def _persist(self) -> None:
        try:
            from researchclaw.server import papers_store

            if papers_store.enabled():
                papers_store.upsert_paper(
                    self.run_id, stage_log=self.stage_log, run_files=self.run_files
                )
        except Exception:
            logger.debug("stage log persist failed", exc_info=True)

    def _emit(self, entry: dict[str, Any]) -> None:
        if not self.broadcast:
            return
        try:
            self.broadcast({"run_id": self.run_id, **entry})
        except Exception:
            pass
