"""Skill lifecycle: usage tracking, semantic match, validated auto-create, weekly curator."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any

from tagopen.config import settings
from tagopen.memory.files import atomic_write_text

logger = logging.getLogger(__name__)

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*\S+", re.I),
    re.compile(r"-----BEGIN .*PRIVATE KEY-----"),
]
_DANGEROUS = [
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"curl\s+[^\n]*\|\s*(ba)?sh", re.I),
]


def _skills_dir(channel_id: str) -> Path:
    return settings.channels_dir / channel_id / "skills"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, parts[2]


def skill_checksum(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def validate_skill_content(content: str) -> tuple[bool, str]:
    meta, body = _parse_frontmatter(content)
    if not meta.get("name") or not meta.get("description"):
        return False, "missing name/description frontmatter"
    for pat in _SECRET_PATTERNS:
        if pat.search(content):
            return False, "secret-like pattern detected"
    for pat in _DANGEROUS:
        if pat.search(content):
            return False, "dangerous command pattern detected"
    if len(body.strip()) < 40:
        return False, "skill body too short"
    return True, ""


async def record_skill_use(
    store,
    channel_id: str,
    skill_name: str,
    *,
    success: bool = True,
    content: str = "",
) -> None:
    now = time.time()
    checksum = skill_checksum(content) if content else ""
    await store.db.execute(
        """INSERT INTO skill_stats (channel_id, skill_name, uses, successes, failures, last_used, checksum)
           VALUES (?, ?, 1, ?, ?, ?, ?)
           ON CONFLICT(channel_id, skill_name) DO UPDATE SET
             uses = uses + 1,
             successes = successes + excluded.successes,
             failures = failures + excluded.failures,
             last_used = excluded.last_used,
             checksum = CASE WHEN excluded.checksum != '' THEN excluded.checksum ELSE checksum END
        """,
        (
            channel_id,
            skill_name,
            1 if success else 0,
            0 if success else 1,
            now,
            checksum,
        ),
    )
    await store.db.commit()


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def semantic_skill_candidates(channel_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Local token-overlap retrieval (Contabo). SaaS can swap for pgvector embeddings."""
    q = _tokenize(query)
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    d = _skills_dir(channel_id)
    if not d.exists():
        return []
    for path in d.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        if (meta.get("status") or "active") != "active":
            continue
        name = meta.get("name") or path.stem
        desc = meta.get("description") or ""
        bag = _tokenize(f"{name} {desc} {body[:500]}")
        if not bag:
            continue
        overlap = len(q & bag) / max(1, len(q))
        if overlap <= 0:
            continue
        scored.append(
            (
                overlap,
                {
                    "name": name,
                    "description": desc,
                    "score": overlap,
                    "path": str(path),
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:limit]]


def format_match_hint(channel_id: str, query: str) -> str:
    cands = semantic_skill_candidates(channel_id, query)
    if not cands:
        return ""
    lines = ["Likely skills (call skill_view before following):"]
    for c in cands:
        lines.append(f"- `{c['name']}` ({c['score']:.2f}) — {c['description']}")
    return "\n".join(lines)


async def curated_create_skill(channel_id: str, content: str, store=None) -> tuple[bool, str]:
    ok, reason = validate_skill_content(content)
    if not ok:
        return False, reason
    meta, _ = _parse_frontmatter(content)
    name = meta["name"]
    # Duplicate similarity
    existing = semantic_skill_candidates(channel_id, meta.get("description", name), limit=3)
    for e in existing:
        if e["name"] == name or e["score"] > 0.85:
            return False, f"duplicate/similar skill exists: {e['name']}"
    path = _skills_dir(channel_id) / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False, "skill file already exists"
    atomic_write_text(path, content if content.endswith("\n") else content + "\n")
    if store is not None:
        await record_skill_use(store, channel_id, name, success=True, content=content)
    return True, name


async def weekly_curator(store, channel_id: str) -> dict[str, Any]:
    """Mark stale (30d), archive (90d), merge near-duplicates by description overlap."""
    now = time.time()
    d = _skills_dir(channel_id)
    report = {"stale": [], "archived": [], "duplicates": []}
    if not d.exists():
        return report
    skills = []
    for path in d.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        name = meta.get("name") or path.stem
        skills.append((name, meta, body, path, text))

    # Duplicate detection
    for i, (n1, m1, b1, p1, t1) in enumerate(skills):
        for n2, m2, b2, p2, t2 in skills[i + 1 :]:
            bag1 = _tokenize(f"{n1} {m1.get('description','')}")
            bag2 = _tokenize(f"{n2} {m2.get('description','')}")
            if not bag1 or not bag2:
                continue
            sim = len(bag1 & bag2) / max(len(bag1 | bag2), 1)
            if sim >= 0.7:
                report["duplicates"].append([n1, n2, round(sim, 2)])

    async with store.db.execute(
        "SELECT skill_name, last_used, status FROM skill_stats WHERE channel_id = ?",
        (channel_id,),
    ) as cur:
        rows = {r["skill_name"]: r for r in await cur.fetchall()}

    for name, meta, body, path, text in skills:
        row = rows.get(name)
        last = float(row["last_used"]) if row and row["last_used"] else 0.0
        age = now - last if last else now
        status = (row["status"] if row else meta.get("status")) or "active"
        if status == "active" and last and age > 30 * 86400:
            await store.db.execute(
                """UPDATE skill_stats SET status = 'stale'
                   WHERE channel_id = ? AND skill_name = ?""",
                (channel_id, name),
            )
            report["stale"].append(name)
        if last and age > 90 * 86400:
            await store.db.execute(
                """UPDATE skill_stats SET status = 'archived'
                   WHERE channel_id = ? AND skill_name = ?""",
                (channel_id, name),
            )
            # preserve rollback: write .archived.md
            archived = path.with_suffix(".archived.md")
            atomic_write_text(archived, text)
            report["archived"].append(name)
    await store.db.commit()
    return report
