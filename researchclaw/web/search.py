"""Web search powered by Tavily AI Search API.

Tavily is the primary search engine (installed as a dependency).
A DuckDuckGo HTML scrape fallback exists for when no API key is set.

Usage::

    client = WebSearchClient(api_key="tvly-...")
    results = client.search("knowledge distillation survey 2024")
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str = ""
    content: str = ""
    score: float = 0.0
    source: str = ""  # "tavily" | "duckduckgo"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }


@dataclass
class WebSearchResponse:
    """Response from a web search query."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    answer: str = ""  # Tavily can provide a direct AI answer
    elapsed_seconds: float = 0.0
    source: str = ""  # "tavily" | "duckduckgo"

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0


class WebSearchClient:
    """General-purpose web search client.

    Uses Tavily (installed) as primary engine. Falls back to DuckDuckGo
    HTML scraping only if no Tavily API key is available.

    Parameters
    ----------
    api_key:
        Tavily API key. Falls back to ``TAVILY_API_KEY`` env var.
    max_results:
        Default number of results per query.
    search_depth:
        Tavily search depth: "basic" or "advanced".
    include_answer:
        Whether to request Tavily's AI-generated answer.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        max_results: int = 10,
        search_depth: str = "advanced",
        include_answer: bool = True,
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
        self.max_results = max_results
        self.search_depth = search_depth
        self.include_answer = include_answer

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> WebSearchResponse:
        """Search the web for a query."""
        limit = max_results or self.max_results
        t0 = time.monotonic()

        # Firecrawl is preferred when configured (REST, no SDK dependency)
        if self.firecrawl_key:
            try:
                return self._search_firecrawl(query, limit, t0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Firecrawl search failed, trying next engine: %s", exc)

        # Tavily next
        if self.api_key:
            try:
                return self._search_tavily(query, limit, include_domains, exclude_domains, t0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tavily search failed, falling back to DuckDuckGo: %s", exc)

        return self._search_duckduckgo(query, limit, t0)

    # ------------------------------------------------------------------
    # Firecrawl backend (REST — https://api.firecrawl.dev/v2/search)
    # ------------------------------------------------------------------

    def _search_firecrawl(self, query: str, limit: int, t0: float) -> WebSearchResponse:
        """Search using Firecrawl's search API (stdlib HTTP, no SDK)."""
        import json as _json
        import urllib.request

        body = _json.dumps({
            "query": query,
            "limit": min(limit, 20),
            "scrapeOptions": {"formats": ["markdown"]},
        }).encode()
        req = urllib.request.Request(
            "https://api.firecrawl.dev/v2/search",
            data=body,
            headers={
                "Authorization": f"Bearer {self.firecrawl_key}",
                "Content-Type": "application/json",
                "User-Agent": "researchclaw",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = _json.loads(resp.read().decode())

        # Firecrawl returns {"success": true, "data": {"web": [...]}} (v2) or
        # {"data": [...]} (older) — accept both.
        data = payload.get("data", payload)
        items = data.get("web", data) if isinstance(data, dict) else data
        results = []
        for item in (items or []):
            md = item.get("markdown") or item.get("content") or ""
            desc = item.get("description") or item.get("snippet") or ""
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=(desc or md)[:500],
                content=md or desc,
                score=0.0,
                source="firecrawl",
            ))
        return WebSearchResponse(
            query=query,
            results=results,
            answer="",
            elapsed_seconds=time.monotonic() - t0,
            source="firecrawl",
        )

    def search_multi(
        self,
        queries: list[str],
        *,
        max_results: int | None = None,
        inter_query_delay: float = 1.0,
    ) -> list[WebSearchResponse]:
        """Run multiple search queries with cross-query deduplication."""
        responses = []
        seen_urls: set[str] = set()

        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(inter_query_delay)
            resp = self.search(query, max_results=max_results)
            unique_results = [r for r in resp.results if r.url not in seen_urls]
            seen_urls.update(r.url for r in unique_results)
            resp.results = unique_results
            responses.append(resp)

        return responses

    # ------------------------------------------------------------------
    # Tavily backend (primary — uses installed tavily-python SDK)
    # ------------------------------------------------------------------

    def _search_tavily(
        self,
        query: str,
        limit: int,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
        t0: float,
    ) -> WebSearchResponse:
        """Search using Tavily API (installed SDK)."""
        from tavily import TavilyClient

        client = TavilyClient(api_key=self.api_key)

        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": limit,
            "search_depth": self.search_depth,
            "include_answer": self.include_answer,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        response = client.search(**kwargs)
        elapsed = time.monotonic() - t0

        results = []
        for item in response.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", "")[:500],
                content=item.get("content", ""),
                score=item.get("score", 0.0),
                source="tavily",
            ))

        return WebSearchResponse(
            query=query,
            results=results,
            answer=response.get("answer", ""),
            elapsed_seconds=elapsed,
            source="tavily",
        )

    # ------------------------------------------------------------------
    # DuckDuckGo fallback (no API key needed)
    # ------------------------------------------------------------------

    def _search_duckduckgo(
        self, query: str, limit: int, t0: float
    ) -> WebSearchResponse:
        """Fallback: scrape DuckDuckGo HTML search results."""
        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })

        try:
            resp = urlopen(req, timeout=15)  # noqa: S310
            html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            logger.warning("DuckDuckGo search failed: %s", exc)
            return WebSearchResponse(query=query, elapsed_seconds=elapsed, source="duckduckgo")

        results = self._parse_ddg_html(html, limit)
        elapsed = time.monotonic() - t0
        return WebSearchResponse(query=query, results=results, elapsed_seconds=elapsed, source="duckduckgo")

    @staticmethod
    def _parse_ddg_html(html: str, limit: int) -> list[SearchResult]:
        """Parse DuckDuckGo HTML results page."""
        results = []
        link_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title_html) in enumerate(links[:limit]):
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            if "duckduckgo.com" in url:
                # Extract actual URL from DDG redirect: //duckduckgo.com/l/?uddg=https%3A...
                from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs, unquote as _unquote
                _parsed_ddg = _urlparse(url)
                _uddg = _parse_qs(_parsed_ddg.query).get("uddg")
                if _uddg:
                    url = _unquote(_uddg[0])
                else:
                    continue
            results.append(SearchResult(title=title, url=url, snippet=snippet, source="duckduckgo"))

        return results
