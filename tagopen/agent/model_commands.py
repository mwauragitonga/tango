"""In-chat model switching — Hermes /model inspired, thread-scoped for Slack multiplayer."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches: model | models | model reset | model channel <id> | model <id>
_MODEL_CMD = re.compile(
    r"^\s*(?:model|models)(?:\s+(channel)\s+(\S+)|\s+(reset)|(?:\s+(.+))?)?\s*$",
    re.I,
)


@dataclass
class ModelCommand:
    kind: str  # list | set | reset | channel
    model: str | None = None


def parse_model_command(text: str) -> ModelCommand | None:
    """Parse user text after stripping bot mention."""
    cleaned = re.sub(r"<@[^>]+>", "", text or "")
    cleaned = re.sub(r"@\w+", "", cleaned).strip()
    m = _MODEL_CMD.match(cleaned)
    if not m:
        return None
    if m.group(1) == "channel" and m.group(2):
        return ModelCommand(kind="channel", model=m.group(2).strip())
    if m.group(3):
        return ModelCommand(kind="reset")
    rest = (m.group(4) or "").strip()
    if not rest:
        return ModelCommand(kind="list")
    return ModelCommand(kind="set", model=rest)
