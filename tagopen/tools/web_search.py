"""Multi-provider web search used by the web_search builtin."""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import httpx

from tagopen.config import settings

logger = logging.getLogger(__name__)


def _clean(text: str) -> str:
    """Strip HTML tags/entities from provider snippets before the LLM sees them."""
    if not text:
        return ""
    text = html.unescape(html.unescape(text))
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


def _resolve_provider() -> str:
    explicit = (settings.web_search_provider or "").strip().lower()
    if explicit:
        return explicit
    if settings.tavily_api_key:
        return "tavily"
    if settings.brave_api_key:
        return "brave"
    if settings.serper_api_key:
        return "serper"
    if settings.firecrawl_api_key:
        return "firecrawl"
    return "ddgs"


def _format_results(rows: list[dict[str, str]], limit: int = 5) -> str:
    lines: list[str] = []
    for row in rows[:limit]:
        title = _clean(row.get("title") or "")
        url = html.unescape(html.unescape((row.get("url") or "").strip()))
        snippet = _clean(row.get("snippet") or "")
        if not title and not snippet:
            continue
        # Slack mrkdwn link so the model can copy a clean form
        if title and url:
            block = f"- <{url}|{title}>"
        elif title:
            block = f"- *{title}*"
        else:
            block = "-"
        if snippet:
            block += f"\n  {snippet}"
        lines.append(block)
    return "\n".join(lines) if lines else "No results found."


async def search_web(query: str) -> str:
    """Search the web; returns Slack-friendly plain text with titles/urls/snippets."""
    provider = _resolve_provider()
    logger.info("web_search provider=%s query=%r", provider, query[:80])
    try:
        if provider == "tavily":
            return await _tavily(query)
        if provider == "brave":
            return await _brave(query)
        if provider == "serper":
            return await _serper(query)
        if provider == "firecrawl":
            return await _firecrawl(query)
        if provider in ("ddgs", "duckduckgo", "ddg"):
            return await _ddgs(query)
        # Unknown provider — try ddgs
        logger.warning("Unknown web_search provider %r; falling back to ddgs", provider)
        return await _ddgs(query)
    except Exception as e:
        logger.warning("Web search failed (%s): %s", provider, e)
        # Last-resort ddgs if a keyed provider failed
        if provider != "ddgs":
            try:
                return await _ddgs(query)
            except Exception as e2:
                return f"Search failed: {e2}"
        return f"Search failed: {e}"


async def _tavily(query: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    rows = [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("content") or "",
        }
        for r in data.get("results") or []
    ]
    return _format_results(rows)


async def _brave(query: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    rows = [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "snippet": r.get("description") or "",
        }
        for r in (data.get("web") or {}).get("results") or []
    ]
    return _format_results(rows)


async def _serper(query: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 5},
        )
        resp.raise_for_status()
        data = resp.json()
    rows = [
        {
            "title": r.get("title") or "",
            "url": r.get("link") or "",
            "snippet": r.get("snippet") or "",
        }
        for r in data.get("organic") or []
    ]
    return _format_results(rows)


async def _firecrawl(query: str) -> str:
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            "https://api.firecrawl.dev/v1/search",
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": 5},
        )
        resp.raise_for_status()
        data = resp.json()
    items: list[Any] = data.get("data") or []
    rows = [
        {
            "title": (r.get("title") or "") if isinstance(r, dict) else "",
            "url": (r.get("url") or "") if isinstance(r, dict) else "",
            "snippet": (r.get("description") or r.get("markdown") or "")[:400]
            if isinstance(r, dict)
            else "",
        }
        for r in items
    ]
    return _format_results(rows)


async def _ddgs(query: str) -> str:
    """Keyless search via the ddgs package (replaces broken DDG Instant Answer)."""
    import asyncio

    def _run() -> list[dict[str, str]]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))
        return [
            {
                "title": r.get("title") or "",
                "url": r.get("href") or r.get("link") or "",
                "snippet": r.get("body") or "",
            }
            for r in raw
        ]

    rows = await asyncio.to_thread(_run)
    return _format_results(rows)
