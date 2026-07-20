#!/usr/bin/env python3
"""Minimal stdio MCP server: org knowledge base over data/org/*.md (and optional JSON).

Proof that Tango can call non-builtin tools via tools.toml. Not a full CRM — replace
with real MCP servers (Postgres, HubSpot, etc.) the same way.

Run (from repo root / WorkingDirectory):
  .venv/bin/python examples/mcp/org_kb_server.py

tools.toml example:
  [[mcp_server]]
  name = "org_kb"
  command = "/opt/apps/open-claude-tag/.venv/bin/python"
  args = ["/opt/apps/open-claude-tag/examples/mcp/org_kb_server.py"]
  allowed_tools = ["org_lookup", "list_org_docs"]
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
ORG_DIR = DATA_DIR / "org"

mcp = FastMCP("org_kb")


def _docs() -> list[Path]:
    if not ORG_DIR.exists():
        return []
    return sorted([*ORG_DIR.glob("*.md"), *ORG_DIR.glob("*.json")])


@mcp.tool()
def list_org_docs() -> str:
    """List organization knowledge files available under data/org/."""
    paths = _docs()
    if not paths:
        return "No org docs found. Create data/org/ORG.md (and other .md files)."
    return "\n".join(f"- {p.name}" for p in paths)


@mcp.tool()
def org_lookup(query: str) -> str:
    """Search organization knowledge (data/org/*.md) for facts matching the query."""
    q = (query or "").strip().lower()
    if not q:
        return "Provide a non-empty query."
    terms = [t for t in re.split(r"\W+", q) if len(t) >= 2]
    hits: list[str] = []
    for path in _docs():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            hits.append(f"{path.name}: read error {e}")
            continue
        lower = text.lower()
        if q in lower or any(t in lower for t in terms):
            # Return matching paragraphs / bullets
            chunks = []
            for line in text.splitlines():
                ll = line.lower()
                if q in ll or any(t in ll for t in terms):
                    chunks.append(line.strip())
            if not chunks:
                chunks = [text.strip()[:500]]
            hits.append(f"### {path.name}\n" + "\n".join(chunks[:12]))
    if not hits:
        return f"No matches in org docs for {query!r}."
    return "\n\n".join(hits[:8])


if __name__ == "__main__":
    mcp.run(transport="stdio")
