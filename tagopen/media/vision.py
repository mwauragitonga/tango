"""Auxiliary vision_analyze — describe an image for text-only main models."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import litellm

from tagopen.config import settings
from tagopen.llm.client import resolve_model
from tagopen.media.routing import model_supports_vision

logger = logging.getLogger(__name__)


def _aux_vision_model(channel_id: str, thread_ts: str = "") -> str | None:
    if settings.vision_model.strip():
        return settings.vision_model.strip()
    main = resolve_model(channel_id, thread_ts or None)
    if model_supports_vision(main):
        return main
    # Fallbacks that commonly support vision
    for fb in settings.fallback_models:
        if model_supports_vision(fb):
            return fb
    return None


async def vision_analyze_file(
    path: Path,
    *,
    mime: str,
    channel_id: str,
    thread_ts: str = "",
    prompt: str = "Describe this image for a coworker who cannot see it. Be concrete.",
) -> str:
    """Describe a local image via an auxiliary (or main) vision-capable model."""
    model = _aux_vision_model(channel_id, thread_ts)
    if not model:
        return (
            f"[Image attached at `{path}` — no vision-capable model configured; "
            "set VISION_MODEL or use a vision main model.]"
        )
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    media = mime if mime.startswith("image/") else "image/png"
    data_url = f"data:{media};base64,{b64}"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=messages,
            timeout=settings.llm_timeout_seconds,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or f"[vision_analyze returned empty for `{path.name}`]"
    except Exception as e:
        logger.warning("vision_analyze failed for %s: %s", path, e)
        return f"[vision_analyze failed for `{path.name}`: {e}]"
