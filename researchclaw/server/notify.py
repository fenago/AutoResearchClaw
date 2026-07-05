"""Completion notifications (email via Resend — active when RESEND_API_KEY set)."""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


def paper_finished(owner_email: str, title: str, run_id: str, status: str) -> bool:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key or not owner_email or "@" not in owner_email:
        return False

    app_url = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")
    link = f"{app_url}/app" if app_url else ""
    sender = os.environ.get("NOTIFY_FROM", "e5o <onboarding@resend.dev>")

    if status == "completed":
        subject = f"Your paper is ready: {title}"
        body = (f"<p>Good news — your paper <strong>{title}</strong> is finished.</p>"
                + (f'<p><a href="{link}">Open it in your library</a></p>' if link else ""))
    else:
        subject = f"Your paper run hit a problem: {title}"
        body = (f"<p>Your paper <strong>{title}</strong> stopped before finishing. "
                "You can open it and click “Try again”.</p>"
                + (f'<p><a href="{link}">Open your library</a></p>' if link else ""))

    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps({
                "from": sender,
                "to": [owner_email],
                "subject": subject,
                "html": body,
            }).encode(),
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20):
            pass
        logger.info("Sent completion email to %s for %s", owner_email, run_id)
        return True
    except Exception:
        logger.warning("completion email failed", exc_info=True)
        return False
