"""Per-tool Slack status UX via reactions (preferred) or ephemeral status posts."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

THINKING_EMOJI = "thinking_face"


def emoji_for_tool(tool_name: str) -> str:
    """Map a tool name to a Slack reaction emoji (without colons)."""
    if tool_name == "web_search":
        return "mag"
    if tool_name == "run_python":
        return "snake"
    if tool_name.startswith("task_"):
        return "clipboard"
    return "gear"


class SlackStatus:
    """Show LLM/tool activity on the triggering message or as a status post."""

    def __init__(
        self,
        client: Any,
        *,
        channel_id: str,
        thread_ts: str,
        event_ts: str | None = None,
    ) -> None:
        self.client = client
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.event_ts = event_ts
        self._active_tool_emoji: str | None = None
        self._status_msg_ts: str | None = None

    async def llm_start(self) -> None:
        """Ensure thinking_face is present on the event (idempotent)."""
        if not self.event_ts:
            return
        await self._reactions_add(THINKING_EMOJI)

    async def tool_start(self, tool_name: str) -> None:
        emoji = emoji_for_tool(tool_name)
        if self.event_ts:
            if self._active_tool_emoji and self._active_tool_emoji != emoji:
                await self._reactions_remove(self._active_tool_emoji)
                self._active_tool_emoji = None
            await self._reactions_add(emoji)
            self._active_tool_emoji = emoji
            return

        # No event_ts: at most one live status post (delete + repost on new tool).
        await self._clear_status_post()
        try:
            resp = await self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=self.thread_ts,
                text=f"Running `{tool_name}`…",
            )
            if isinstance(resp, dict):
                self._status_msg_ts = resp.get("ts")
            else:
                data = getattr(resp, "data", None) or {}
                self._status_msg_ts = data.get("ts") if isinstance(data, dict) else None
        except Exception:
            logger.debug("Failed to post tool status for %s", tool_name, exc_info=True)
            self._status_msg_ts = None

    async def tool_end(self, tool_name: str) -> None:
        emoji = emoji_for_tool(tool_name)
        if self.event_ts:
            if self._active_tool_emoji == emoji:
                await self._reactions_remove(emoji)
                self._active_tool_emoji = None
            # Leave thinking_face in place until finish() / gateway cleanup.
            return
        await self._clear_status_post()

    async def finish(self) -> None:
        """Best-effort cleanup of tool reaction/status and thinking_face."""
        if self._active_tool_emoji and self.event_ts:
            await self._reactions_remove(self._active_tool_emoji)
            self._active_tool_emoji = None
        await self._clear_status_post()
        if self.event_ts:
            await self._reactions_remove(THINKING_EMOJI)

    async def _clear_status_post(self) -> None:
        if not self._status_msg_ts:
            return
        try:
            await self.client.chat_delete(
                channel=self.channel_id,
                ts=self._status_msg_ts,
            )
        except Exception:
            logger.debug("Failed to delete status post %s", self._status_msg_ts, exc_info=True)
        self._status_msg_ts = None

    async def _reactions_add(self, name: str) -> None:
        try:
            await self.client.reactions_add(
                channel=self.channel_id,
                timestamp=self.event_ts,
                name=name,
            )
        except Exception:
            # Already present or transient Slack error — treat as idempotent.
            logger.debug(
                "reactions_add %s failed (channel=%s ts=%s)",
                name,
                self.channel_id,
                self.event_ts,
                exc_info=True,
            )

    async def _reactions_remove(self, name: str) -> None:
        try:
            await self.client.reactions_remove(
                channel=self.channel_id,
                timestamp=self.event_ts,
                name=name,
            )
        except Exception:
            logger.debug(
                "reactions_remove %s failed (channel=%s ts=%s)",
                name,
                self.channel_id,
                self.event_ts,
                exc_info=True,
            )
