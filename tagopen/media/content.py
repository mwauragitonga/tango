"""Build LiteLLM user message content from prepared attachments."""

from __future__ import annotations

from typing import Any

from tagopen.media.prepare import PreparedAttachments


def build_user_message_content(
    *,
    display_name: str,
    text: str,
    prepared: PreparedAttachments | None,
) -> str | list[dict[str, Any]]:
    """Return string or multimodal content list for the current user turn."""
    body = f"[@{display_name}] {text or ''}".rstrip()
    if prepared and prepared.text_addon.strip():
        body = f"{body}\n\n{prepared.text_addon.strip()}".strip()

    if not prepared or not prepared.native_images:
        return body

    parts: list[dict[str, Any]] = [{"type": "text", "text": body}]
    for img in prepared.native_images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": img["data_url"]},
            }
        )
    return parts


def text_with_addon(text: str, prepared: PreparedAttachments | None) -> str:
    """Plain-text merge for storage / durable objectives (no pixel parts)."""
    if not prepared or not prepared.text_addon.strip():
        return text
    return f"{text}\n\n{prepared.text_addon.strip()}".strip()
