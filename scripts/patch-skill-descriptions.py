#!/usr/bin/env python3
"""Tighten skill frontmatter descriptions for NL matching (Contabo coworker pack)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

OVERRIDES = {
    "humanizer": (
        "Humanize text: strip AI-isms, buzzwords, and corporate tone; "
        "rewrite in a natural human voice."
    ),
    "seo-audit": (
        "Audit or diagnose SEO issues, rankings, on-page SEO, meta tags, technical SEO health."
    ),
    "social-content": (
        "Create or optimize social posts for LinkedIn, Twitter/X, Instagram, TikTok, content calendars."
    ),
    "github": "GitHub operations via gh: repos, PRs, code review, issues, analytics.",
    "standup-notes": "Turn messy channel chatter into a short standup summary.",
    "creative-ideation": "Generate project ideas via creative constraints.",
}

_NOISE = re.compile(r"\s*\(Hermes playbook[^)]*\)\s*", re.I)
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def patch_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    m = _FM.match(raw)
    if not m:
        return False
    name = path.stem
    meta_block = m.group(1)
    new_desc = OVERRIDES.get(name)
    if not new_desc:
        # strip noise from existing description
        lines = []
        changed = False
        for line in meta_block.splitlines():
            if line.lower().startswith("description:"):
                val = line.split(":", 1)[1].strip().strip("\"'")
                cleaned = _NOISE.sub("", val).strip()
                if cleaned != val:
                    changed = True
                if len(cleaned) > 220:
                    cleaned = cleaned[:217].rstrip() + "…"
                    changed = True
                lines.append(f"description: {cleaned}")
            else:
                lines.append(line)
        if not changed:
            return False
        new_meta = "\n".join(lines)
    else:
        lines = []
        saw_desc = False
        for line in meta_block.splitlines():
            if line.lower().startswith("description:"):
                lines.append(f"description: {new_desc}")
                saw_desc = True
            else:
                lines.append(line)
        if not saw_desc:
            lines.insert(0, f"description: {new_desc}")
        new_meta = "\n".join(lines)

    path.write_text(f"---\n{new_meta}\n---\n" + raw[m.end() :], encoding="utf-8")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: patch-skill-descriptions.py <skills_dir>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    n = 0
    for path in sorted(root.glob("*.md")):
        if patch_file(path):
            print(f"patched: {path.name}")
            n += 1
    print(f"done: {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
