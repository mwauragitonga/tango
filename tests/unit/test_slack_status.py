"""Unit tests for Slack tool-status helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tagopen.slack_status import SlackStatus, emoji_for_tool


def test_emoji_mapping():
    assert emoji_for_tool("web_search") == "mag"
    assert emoji_for_tool("run_python") == "snake"
    assert emoji_for_tool("task_plan") == "clipboard"
    assert emoji_for_tool("task_update") == "clipboard"
    assert emoji_for_tool("some_mcp_tool") == "gear"


@pytest.mark.asyncio
async def test_tool_lifecycle_uses_reactions_when_event_ts():
    client = MagicMock()
    client.reactions_add = AsyncMock(return_value={"ok": True})
    client.reactions_remove = AsyncMock(return_value={"ok": True})
    client.chat_postMessage = AsyncMock()
    client.chat_delete = AsyncMock()

    status = SlackStatus(
        client, channel_id="C1", thread_ts="1.0", event_ts="1.0"
    )
    await status.llm_start()
    client.reactions_add.assert_awaited_with(
        channel="C1", timestamp="1.0", name="thinking_face"
    )

    await status.tool_start("web_search")
    client.reactions_add.assert_awaited_with(
        channel="C1", timestamp="1.0", name="mag"
    )
    await status.tool_end("web_search")
    client.reactions_remove.assert_awaited_with(
        channel="C1", timestamp="1.0", name="mag"
    )
    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_tool_lifecycle_status_post_without_event_ts():
    client = MagicMock()
    client.reactions_add = AsyncMock()
    client.reactions_remove = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ts": "9.9"})
    client.chat_delete = AsyncMock(return_value={"ok": True})

    status = SlackStatus(client, channel_id="C1", thread_ts="1.0", event_ts=None)
    await status.llm_start()
    client.reactions_add.assert_not_called()

    await status.tool_start("run_python")
    client.chat_postMessage.assert_awaited_once()
    assert "run_python" in client.chat_postMessage.await_args.kwargs["text"]

    await status.tool_end("run_python")
    client.chat_delete.assert_awaited_once_with(channel="C1", ts="9.9")


@pytest.mark.asyncio
async def test_status_post_throttled_to_one_live_message():
    client = MagicMock()
    client.chat_postMessage = AsyncMock(
        side_effect=[{"ts": "1.1"}, {"ts": "1.2"}]
    )
    client.chat_delete = AsyncMock(return_value={"ok": True})

    status = SlackStatus(client, channel_id="C1", thread_ts="1.0")
    await status.tool_start("web_search")
    await status.tool_start("run_python")
    assert client.chat_delete.await_count == 1
    assert client.chat_postMessage.await_count == 2
    assert client.chat_delete.await_args.kwargs["ts"] == "1.1"
