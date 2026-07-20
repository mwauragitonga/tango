"""Progressive skills (Hermes-inspired): index in prompt, body via skill_view."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from tagopen.config import settings

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def skills_dir(channel_id: str) -> Path:
    return settings.channels_dir / channel_id / "skills"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    m = _FRONTMATTER_RE.match(text)
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        body = text[m.end() :]
    return meta, body


_IMPORT_NOISE_RE = re.compile(
    r"\s*\(Hermes playbook[^)]*\)\s*$",
    re.I,
)


def _clean_description(desc: str) -> str:
    """Strip import boilerplate so match signal stays in the trigger text."""
    desc = _IMPORT_NOISE_RE.sub("", (desc or "").strip())
    # Cap for prompt index (Hermes-style metadata tier)
    if len(desc) > 220:
        desc = desc[:217].rstrip() + "…"
    return desc


def list_skill_summaries(channel_id: str) -> list[dict[str, str]]:
    """Return active skills as {name, description} for the system prompt index."""
    root = skills_dir(channel_id)
    if not root.exists():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(root.glob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = _parse_frontmatter(raw)
        if meta.get("status") == "archived" or "status: archived" in raw[:200]:
            continue
        name = meta.get("name") or path.stem
        desc = meta.get("description") or ""
        if not desc:
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    desc = line[:160]
                    break
        out.append({"name": name, "description": _clean_description(desc) or "(no description)"})
    return out


def format_skills_index(channel_id: str) -> str:
    summaries = list_skill_summaries(channel_id)
    if not summaries:
        return ""
    lines = [
        "## Skills (mandatory — Hermes-style progressive disclosure)",
        "Before replying, scan the skills below. If a skill matches or is even *partially* "
        "relevant to the user's task, you MUST call `skill_view(name=<skill>)` and follow "
        "its instructions before answering. Err on the side of loading — better to have "
        "context you do not need than to miss an established playbook.",
        "Examples: natural/human voice rewrite or strip AI-isms → `humanizer`; SEO audit → "
        "`seo-audit`; GitHub PR/issue help → `github`; standup digest → `standup-notes`.",
        "Do **not** invent skill contents. Do **not** wait for the user to name `skill_view`.",
        "Host shell/DB/SSH steps in a playbook require confirm + `hermes_ask` (if available).",
        "",
        "<available_skills>",
    ]
    for s in summaries:
        lines.append(f"- {s['name']}: {s['description']}")
    lines.append("</available_skills>")
    return "\n".join(lines)


def skill_view(channel_id: str, name: str) -> str:
    """Load full skill markdown by name (stem or frontmatter name)."""
    want = (name or "").strip().lower()
    if not want:
        return "Provide a skill name."
    root = skills_dir(channel_id)
    if not root.exists():
        return "No skills directory for this channel."
    for path in sorted(root.glob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        meta, _body = _parse_frontmatter(raw)
        if meta.get("status") == "archived":
            continue
        names = {path.stem.lower()}
        if meta.get("name"):
            names.add(meta["name"].lower())
        if want in names:
            return raw.strip()
    available = ", ".join(s["name"] for s in list_skill_summaries(channel_id)) or "(none)"
    return f"Skill '{name}' not found. Available: {available}"


def skills_list_text(channel_id: str) -> str:
    summaries = list_skill_summaries(channel_id)
    if not summaries:
        return "No skills installed for this channel. Add markdown under skills/."
    return "\n".join(f"- `{s['name']}` — {s['description']}" for s in summaries)
