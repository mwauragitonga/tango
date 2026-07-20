"""Format live tool schemas for prompts and list_tools."""

from __future__ import annotations


def format_tools_catalog(schemas: list[dict]) -> str:
    """One bullet per tool: `name` — first line of description."""
    lines: list[str] = []
    for schema in schemas:
        fn = schema.get("function") or {}
        name = fn.get("name") or "?"
        desc = (fn.get("description") or "").strip().split("\n")[0][:160]
        if desc:
            lines.append(f"- `{name}` — {desc}")
        else:
            lines.append(f"- `{name}`")
    return "\n".join(lines) if lines else "(no tools registered)"
