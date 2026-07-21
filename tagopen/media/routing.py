"""Image input routing: native pixels vs aux vision_analyze text (Hermes-style)."""

from __future__ import annotations

import re

from tagopen.config import settings
from tagopen.llm.client import resolve_model

# Heuristic substrings for models.dev-style vision capability when mode=auto
_VISION_HINTS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "gpt-4-turbo",
    "gpt-4-vision",
    "claude-3",
    "claude-4",
    "claude-sonnet",
    "claude-opus",
    "claude-haiku",
    "gemini",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "mimo-vl",
    "llava",
    "pixtral",
    "vision",
)

_NON_VISION_HINTS = (
    "kimi",
    "deepseek",
    "codex",
    "o1-mini",
    "o3-mini",
)


def model_supports_vision(model: str | None = None) -> bool:
    """Return whether the active model should receive native image parts."""
    cap = (settings.llm_vision_capability or "auto").strip().lower()
    if cap in {"true", "1", "yes", "native"}:
        return True
    if cap in {"false", "0", "no", "text"}:
        return False

    mid = (model or settings.llm_model or "").lower()
    for hint in _NON_VISION_HINTS:
        if hint in mid:
            return False
    for hint in _VISION_HINTS:
        if hint in mid:
            return True
    # Explicit allowlist overrides
    allow = [m.strip().lower() for m in settings.llm_vision_models.split(",") if m.strip()]
    if allow and mid in allow:
        return True
    return False


def decide_image_mode(*, channel_id: str, thread_ts: str = "") -> str:
    """Return ``native`` or ``text`` for inbound user-attached images."""
    mode = (settings.image_input_mode or "auto").strip().lower()
    if mode == "native":
        return "native"
    if mode == "text":
        return "text"
    # auto
    model = resolve_model(channel_id, thread_ts or None)
    return "native" if model_supports_vision(model) else "text"


def looks_like_data_url(url: str) -> bool:
    return bool(re.match(r"^data:image/[\w.+-]+;base64,", url or "", re.I))
