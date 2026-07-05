"""Persistent paper library backed by Supabase (survives container rebuilds).

Reads go through the caller's own JWT (RLS: owners see their papers).
Writes go through a single Vault-gated SQL function (e5o_upsert_paper) using
E5O_WRITER_SECRET — the server can save papers and nothing else.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 300_000
_MAX_TOTAL_BYTES = 900_000
_TEXT_EXTS = {".md", ".tex", ".bib", ".txt", ".json", ".csv"}


def _env() -> tuple[str, str, str]:
    return (
        os.environ.get("SUPABASE_URL", "").rstrip("/"),
        os.environ.get("SUPABASE_ANON_KEY", ""),
        os.environ.get("E5O_WRITER_SECRET", ""),
    )


def enabled() -> bool:
    url, anon, secret = _env()
    return bool(url and anon and secret)


def _request(url: str, headers: dict, body: dict | None = None, method: str = "POST") -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None


def upsert_paper(run_id: str, **fields: Any) -> bool:
    """Insert/update a paper row via the Vault-gated RPC. Best-effort."""
    if not enabled():
        return False
    url, anon, secret = _env()
    payload = {"p_secret": secret, "p_run_id": run_id}
    for key, value in fields.items():
        payload[f"p_{key}"] = value
    try:
        _request(
            f"{url}/rest/v1/rpc/e5o_upsert_paper",
            {"apikey": anon, "Authorization": f"Bearer {anon}",
             "Content-Type": "application/json", "User-Agent": "researchclaw"},
            payload,
        )
        return True
    except Exception:
        logger.warning("Failed to persist paper %s", run_id, exc_info=True)
        return False


def owner_email(token: str) -> str:
    """Resolve the email behind a Supabase access token ('' if unknown)."""
    url, anon, _ = _env()
    if not (url and anon and token):
        return ""
    try:
        user = _request(
            f"{url}/auth/v1/user",
            {"apikey": anon, "Authorization": f"Bearer {token}", "User-Agent": "researchclaw"},
            method="GET",
        )
        return (user or {}).get("email", "")
    except Exception:
        return ""


def collect_deliverables(run_dir: Path) -> dict[str, Any]:
    """Gather the run's text deliverables: main .md, main .tex, other files."""
    root = run_dir / "deliverables"
    if not root.is_dir():
        root = run_dir

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in _TEXT_EXTS:
            files.append(path)

    paper_md = paper_tex = None
    artifacts: dict[str, str] = {}
    total = 0
    md_candidates = [f for f in files if f.suffix.lower() == ".md" and f.name.lower() != "readme.md"]
    tex_candidates = [f for f in files if f.suffix.lower() == ".tex"]
    main_md = max(md_candidates, key=lambda f: f.stat().st_size, default=None)
    main_tex = max(tex_candidates, key=lambda f: f.stat().st_size, default=None)

    for path in files:
        try:
            size = path.stat().st_size
            if size > _MAX_FILE_BYTES or total + size > _MAX_TOTAL_BYTES:
                continue
            content = path.read_text(errors="replace")
            total += size
        except Exception:
            continue
        if path == main_md:
            paper_md = content
        elif path == main_tex:
            paper_tex = content
        else:
            artifacts[str(path.relative_to(root))] = content

    return {"paper_md": paper_md, "paper_tex": paper_tex, "artifacts": artifacts or None}


def get_user_llm(email: str) -> dict[str, str] | None:
    """Server-side fetch of a user's LLM choice + decrypted key (writer-gated)."""
    if not enabled() or not email:
        return None
    url, anon, secret = _env()
    try:
        rows = _request(
            f"{url}/rest/v1/rpc/e5o_get_user_llm",
            {"apikey": anon, "Authorization": f"Bearer {anon}",
             "Content-Type": "application/json", "User-Agent": "researchclaw"},
            {"p_secret": secret, "p_email": email},
        )
        if isinstance(rows, list) and rows and rows[0].get("provider"):
            return {
                "provider": rows[0].get("provider") or "",
                "model": rows[0].get("model") or "",
                "api_key": rows[0].get("api_key") or "",
            }
    except Exception:
        logger.warning("get_user_llm failed for %s", email, exc_info=True)
    return None


def mark_interrupted_runs() -> int:
    """At server startup: flag papers whose pipeline died with the old container."""
    if not enabled():
        return 0
    url, anon, secret = _env()
    try:
        count = _request(
            f"{url}/rest/v1/rpc/e5o_mark_interrupted",
            {"apikey": anon, "Authorization": f"Bearer {anon}",
             "Content-Type": "application/json", "User-Agent": "researchclaw"},
            {"p_secret": secret},
        )
        if count:
            logger.info("Marked %s interrupted paper run(s) as failed", count)
        return int(count or 0)
    except Exception:
        logger.warning("mark_interrupted_runs failed", exc_info=True)
        return 0


def get_active_work() -> list[dict[str, Any]]:
    """Fetch running (to resume) and queued (to start) papers. Writer-gated."""
    if not enabled():
        return []
    url, anon, secret = _env()
    try:
        rows = _request(
            f"{url}/rest/v1/rpc/e5o_get_active_work",
            {"apikey": anon, "Authorization": f"Bearer {anon}",
             "Content-Type": "application/json", "User-Agent": "researchclaw"},
            {"p_secret": secret},
        )
        return rows if isinstance(rows, list) else []
    except Exception:
        logger.warning("get_active_work failed", exc_info=True)
        return []


def restore_run_dir(run_dir: Path, run_files: dict[str, dict[str, str]]) -> int:
    """Recreate a run directory from persisted file snapshots."""
    count = 0
    for group, files in (run_files or {}).items():
        base = run_dir if group == "_root" else run_dir / group
        base.mkdir(parents=True, exist_ok=True)
        for rel, content in (files or {}).items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_text(content)
                count += 1
            except Exception:
                logger.warning("could not restore %s", target, exc_info=True)
    return count


_CAPTURE_EXTS = {".md", ".json", ".jsonl", ".txt", ".tex", ".bib", ".yaml", ".yml", ".csv", ".py"}
_CAPTURE_FILE_CAP = 400_000
_CAPTURE_GROUP_CAP = 2_000_000


def capture_dir_files(base: Path) -> dict[str, str]:
    """Snapshot a directory's text files (capped) for resume storage."""
    out: dict[str, str] = {}
    total = 0
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _CAPTURE_EXTS:
            continue
        try:
            size = path.stat().st_size
            if size > _CAPTURE_FILE_CAP or total + size > _CAPTURE_GROUP_CAP:
                continue
            out[str(path.relative_to(base))] = path.read_text(errors="replace")
            total += size
        except Exception:
            continue
    return out
