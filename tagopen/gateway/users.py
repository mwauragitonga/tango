"""TTL-cached Slack user lookups."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_TTL = 300.0


async def get_display_name(app: "AsyncApp", user_id: str) -> str:
    now = time.time()
    # Per-user mini cache inside channel maps is enough; keep simple single-user fetch
    key = f"u:{user_id}"
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1].get(user_id, user_id)
    try:
        info = await app.client.users_info(user=user_id)
        profile = info["user"].get("profile", {})
        name = profile.get("display_name") or info["user"].get("real_name") or user_id
    except Exception:
        name = user_id
    _CACHE[key] = (now, {user_id: name})
    return name


async def get_user_map(
    app: "AsyncApp",
    channel_id: str,
    fallback: dict[str, str] | None = None,
) -> dict[str, str]:
    now = time.time()
    hit = _CACHE.get(channel_id)
    if hit and now - hit[0] < _TTL:
        return dict(hit[1])
    user_map: dict[str, str] = dict(fallback or {})
    try:
        members = await app.client.conversations_members(channel=channel_id)
        for uid in (members.get("members") or [])[:50]:
            user_map[uid] = await get_display_name(app, uid)
    except Exception:
        pass
    _CACHE[channel_id] = (now, user_map)
    return user_map
