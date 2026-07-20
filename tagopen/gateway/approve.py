"""HITL approve/deny command parsing (pure helpers)."""

from __future__ import annotations

import re

# Bare `approve`/`deny` or `approve <id>` / `deny <id>`
_APPROVE = re.compile(r"^\s*(approve|deny)(?:\s+(\S+))?\s*$", re.I)


def parse_approve_command(text: str) -> tuple[str, str | None] | None:
    """Return (action, approval_id|None) or None if not an approve/deny command."""
    m = _APPROVE.match(text or "")
    if not m:
        return None
    return m.group(1).lower(), m.group(2)
