"""Download Slack files into a workspace-local media cache."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from tagopen.config import settings
from tagopen.tasks.models import new_id

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def media_cache_dir(workspace_id: str, channel_id: str) -> Path:
    root = settings.data_dir / "media" / workspace_id / channel_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(name: str) -> str:
    base = Path(name or "file").name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "file"
    return cleaned[:180]


async def download_slack_file(
    *,
    url: str,
    bot_token: str,
    dest_dir: Path,
    filename: str,
    max_bytes: int,
) -> tuple[Path, bytes]:
    """Download a Slack private file URL with the bot token. Returns (path, bytes)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{new_id('att_')[:12]}_{safe_filename(filename)}"
    dest = dest_dir / fname
    headers = {"Authorization": f"Bearer {bot_token}"}
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Attachment exceeds max size ({max_bytes} bytes)")
                chunks.append(chunk)
    data = b"".join(chunks)
    dest.write_bytes(data)
    return dest, data


def is_under_media_cache(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = (settings.data_dir / "media").resolve()
        return root in resolved.parents or resolved == root
    except Exception:
        return False
