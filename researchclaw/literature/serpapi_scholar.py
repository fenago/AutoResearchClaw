"""Google Scholar search via SerpApi (reliable from servers; scholarly is not).

SerpApi handles the proxying/CAPTCHA that block direct Google Scholar scraping
from datacenter IPs. Requires SERPAPI_API_KEY. Docs:
https://serpapi.com/google-scholar-api
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request

from researchclaw.literature.models import Author, Paper

logger = logging.getLogger(__name__)

_ENDPOINT = "https://serpapi.com/search.json"


def _year_from_summary(summary: str) -> int:
    # publication_info.summary looks like "J Smith, A Doe - Journal, 2023 - publisher"
    m = re.search(r"\b(19|20)\d{2}\b", summary or "")
    return int(m.group(0)) if m else 0


def _authors_from_summary(summary: str) -> tuple[Author, ...]:
    # Authors are the part before the first " - "
    head = (summary or "").split(" - ")[0]
    names = [n.strip() for n in head.split(",") if n.strip()]
    return tuple(Author(name=n) for n in names[:10])


def search_serpapi_scholar(
    query: str, *, limit: int = 20, year_min: int = 0, api_key: str = ""
) -> list[Paper]:
    """Search Google Scholar via SerpApi and return Paper objects."""
    key = api_key or os.environ.get("SERPAPI_API_KEY", "")
    if not key:
        return []

    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": key,
        "num": str(min(limit, 20)),
    }
    if year_min > 0:
        params["as_ylo"] = str(year_min)

    url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "researchclaw"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode())

    papers: list[Paper] = []
    for item in data.get("organic_results", [])[:limit]:
        info = item.get("publication_info", {}) or {}
        summary = info.get("summary", "")
        cited = (
            (item.get("inline_links", {}) or {})
            .get("cited_by", {})
            .get("total", 0)
        )
        papers.append(
            Paper(
                paper_id=str(item.get("result_id", "")) or item.get("link", ""),
                title=item.get("title", ""),
                authors=_authors_from_summary(summary),
                year=_year_from_summary(summary),
                abstract=item.get("snippet", ""),
                venue=summary,
                citation_count=int(cited or 0),
                url=item.get("link", ""),
                source="google_scholar",
            )
        )
    logger.info("SerpApi Google Scholar returned %d papers for %r", len(papers), query)
    return papers
