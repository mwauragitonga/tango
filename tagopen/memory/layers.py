"""Layered memory: working / channel / episodic / semantic (Mem0 optional)."""

from __future__ import annotations

import logging
import time
from typing import Any

from tagopen.config import settings
from tagopen.tasks.models import new_id

logger = logging.getLogger(__name__)


async def write_channel_memory(
    store,
    *,
    workspace_id: str,
    channel_id: str,
    content: str,
    author: str,
    provenance: str,
    confidence: float = 0.7,
    supersedes: str | None = None,
) -> str | None:
    if not provenance.strip():
        logger.warning("Rejected memory without provenance")
        return None
    mid = new_id("mem_")
    now = time.time()
    await store.db.execute(
        """INSERT INTO memories (
             id, workspace_id, channel_id, kind, content, provenance, author,
             confidence, supersedes, created_at, updated_at
           ) VALUES (?, ?, ?, 'channel', ?, ?, ?, ?, ?, ?, ?)""",
        (
            mid,
            workspace_id,
            channel_id,
            content.strip(),
            provenance.strip(),
            author,
            confidence,
            supersedes,
            now,
            now,
        ),
    )
    await store.db.commit()
    return mid


async def write_episodic(
    store,
    *,
    workspace_id: str,
    channel_id: str,
    content: str,
    provenance: str,
    author: str = "system",
) -> str | None:
    return await write_channel_memory(
        store,
        workspace_id=workspace_id,
        channel_id=channel_id,
        content=content,
        author=author,
        provenance=provenance,
        confidence=0.8,
    )


async def list_channel_memories(
    store, workspace_id: str, channel_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    async with store.db.execute(
        """SELECT id, content, provenance, author, confidence, created_at
           FROM memories
           WHERE workspace_id = ? AND channel_id = ? AND kind IN ('channel', 'episodic')
           ORDER BY updated_at DESC LIMIT ?""",
        (workspace_id, channel_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def semantic_recall(
    *,
    workspace_id: str,
    channel_id: str,
    query: str,
    limit: int = 5,
) -> list[str]:
    """Namespaced Mem0 recall when enabled; never indexes Hermes USER.md."""
    if not settings.mem0_enabled or not settings.mem0_dsn:
        return []
    try:
        # Optional dependency — soft-fail
        from mem0 import Memory  # type: ignore

        namespace = f"{workspace_id}/{channel_id}"
        # Minimal local config; production wires Postgres+pgvector via mem0 config
        m = Memory()
        results = m.search(query, user_id=namespace, limit=limit)
        out = []
        for r in results.get("results", results) if isinstance(results, dict) else results:
            if isinstance(r, dict):
                out.append(str(r.get("memory") or r.get("text") or r))
            else:
                out.append(str(r))
        return out[:limit]
    except Exception:
        logger.exception("Mem0 semantic recall failed")
        return []


def format_memory_citations(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for r in rows:
        lines.append(
            f"{r['content']} 〔{r['id'][:8]} · {r.get('author','?')} · conf={r.get('confidence',0):.2f} · {r.get('provenance','')}〕"
        )
    return lines
