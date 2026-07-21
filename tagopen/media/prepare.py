"""Prepare Slack file attachments: download, classify, route images, inject text."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tagopen.config import settings
from tagopen.media.cache import download_slack_file, media_cache_dir
from tagopen.media.classify import classify_file
from tagopen.media.routing import decide_image_mode
from tagopen.media.vision import vision_analyze_file

logger = logging.getLogger(__name__)


@dataclass
class PreparedAttachments:
    """Result of Hermes-style attachment preparation for one Slack turn."""

    text_addon: str = ""
    native_images: list[dict[str, str]] = field(default_factory=list)
    # Serializable paths for durable tasks / read_attachment
    cached_paths: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_checkpoint(self) -> dict[str, Any]:
        return {
            "cached_paths": self.cached_paths,
            "native_image_paths": [
                {"path": i["path"], "mime": i["mime"]} for i in self.native_images
            ],
        }


async def prepare_slack_files(
    *,
    files: list[dict[str, Any]] | None,
    bot_token: str,
    workspace_id: str,
    channel_id: str,
    thread_ts: str = "",
) -> PreparedAttachments:
    """Download Slack files and build inject payload (images/text/binary)."""
    out = PreparedAttachments()
    if not files:
        return out
    if not bot_token:
        out.errors.append("No bot token — cannot download attachments (need files:read).")
        out.text_addon = "\n".join(f"⚠ {e}" for e in out.errors)
        return out

    mode = decide_image_mode(channel_id=channel_id, thread_ts=thread_ts)
    dest_dir = media_cache_dir(workspace_id, channel_id)
    max_bytes = settings.media_max_bytes
    inline_max = settings.media_inline_text_max_bytes
    notes: list[str] = ["--- Attached files ---"]

    for f in files:
        if not isinstance(f, dict):
            continue
        file_id = str(f.get("id") or "")
        name = str(f.get("name") or f.get("title") or "file")
        mime = str(f.get("mimetype") or "")
        url = (
            str(f.get("url_private_download") or "")
            or str(f.get("url_private") or "")
        )
        if not url:
            out.errors.append(f"No download URL for `{name}` ({file_id})")
            continue
        try:
            path, data = await download_slack_file(
                url=url,
                bot_token=bot_token,
                dest_dir=dest_dir,
                filename=name,
                max_bytes=max_bytes,
            )
        except Exception as e:
            logger.warning("Failed to download Slack file %s: %s", name, e)
            out.errors.append(f"Download failed for `{name}`: {e}")
            continue

        kind = classify_file(filename=name, mimetype=mime, magic_prefix=data[:16])
        rel = str(path)
        out.cached_paths.append(
            {"path": rel, "name": name, "mime": kind.mime, "kind": kind.kind}
        )

        if kind.kind == "image":
            if mode == "native":
                b64 = base64.b64encode(data).decode("ascii")
                media = kind.mime if kind.mime.startswith("image/") else "image/png"
                out.native_images.append(
                    {
                        "path": rel,
                        "mime": media,
                        "data_url": f"data:{media};base64,{b64}",
                    }
                )
                notes.append(f"[image native] `{name}` → `{path}`")
            else:
                desc = await vision_analyze_file(
                    path,
                    mime=kind.mime,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                )
                notes.append(f"[image description for `{name}`]\n{desc}")
            continue

        if kind.kind == "text":
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                notes.append(
                    f"[binary] `{name}` at `{path}` (not valid UTF-8). "
                    "Use `read_attachment` or extract with tools."
                )
                continue
            if len(data) > inline_max:
                notes.append(
                    f"[text truncated] `{name}` at `{path}` "
                    f"({len(data)} bytes > {inline_max}). "
                    "Use `read_attachment` for the full file.\n"
                    f"Preview:\n```\n{text[: inline_max // 2]}\n```"
                )
            else:
                notes.append(f"[text `{name}`]\n```\n{text}\n```")
            continue

        # binary documents / sheets
        notes.append(
            f"[document] `{name}` ({kind.mime or 'binary'}) saved at `{path}`.\n"
            "Text is not inlined (binary/Office/PDF). Use `read_attachment` "
            "(text extract when possible) or process via tools before answering."
        )

    if out.errors:
        notes.extend(f"⚠ {e}" for e in out.errors)
    if len(notes) > 1:
        out.text_addon = "\n".join(notes)
    return out


def reload_native_images_from_checkpoint(
    checkpoint_attachments: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Rebuild data_url image parts from cached paths (durable first turns)."""
    if not checkpoint_attachments:
        return []
    images: list[dict[str, str]] = []
    for item in checkpoint_attachments.get("native_image_paths") or []:
        path = Path(str(item.get("path") or ""))
        mime = str(item.get("mime") or "image/png")
        if not path.is_file():
            continue
        try:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            images.append(
                {
                    "path": str(path),
                    "mime": mime,
                    "data_url": f"data:{mime};base64,{b64}",
                }
            )
        except Exception as e:
            logger.warning("reload native image failed %s: %s", path, e)
    return images
