"""LiteLLM gateway streaming + first-token callback (no live provider)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tagopen.llm.gateway import LLMRequestContext, _chunk_has_output, complete


def _delta_chunk(*, content: str | None = None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=None)


def test_chunk_has_output_content_and_tools():
    assert _chunk_has_output(_delta_chunk(content="hi"))
    assert _chunk_has_output(
        _delta_chunk(tool_calls=[SimpleNamespace(index=0, function=SimpleNamespace())])
    )
    assert not _chunk_has_output(_delta_chunk())
    assert not _chunk_has_output(SimpleNamespace(choices=[]))


@pytest.mark.asyncio
async def test_complete_stream_fires_on_first_token_once():
    chunks = [
        _delta_chunk(),  # role-only / empty
        _delta_chunk(content="Hel"),
        _delta_chunk(content="lo"),
    ]

    async def fake_stream(**_kwargs):
        async def gen():
            for c in chunks:
                yield c

        return gen()

    rebuilt = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello", tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        id="chatcmpl_test",
        _hidden_params={},
    )

    first_token = AsyncMock()
    ctx = LLMRequestContext(workspace_id="T1", channel_id="C1", thread_ts="1.0")

    with (
        patch("tagopen.llm.gateway.litellm.acompletion", new=AsyncMock(side_effect=fake_stream)),
        patch("tagopen.llm.gateway.litellm.stream_chunk_builder", return_value=rebuilt),
        patch("tagopen.llm.gateway.resolve_model", return_value="test-model"),
        patch("tagopen.llm.gateway.settings") as mock_settings,
    ):
        mock_settings.llm_stream = True
        mock_settings.llm_use_app_fallbacks = False
        mock_settings.fallback_models = []
        mock_settings.llm_timeout_seconds = 30.0

        resp, notice = await complete(ctx, messages=[{"role": "user", "content": "hi"}], on_first_token=first_token)

    assert resp is rebuilt
    assert notice is None
    assert first_token.await_count == 1


@pytest.mark.asyncio
async def test_complete_non_stream_still_fires_first_token():
    rebuilt = MagicMock()
    rebuilt.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    rebuilt.id = "x"
    rebuilt._hidden_params = {}

    first_token = AsyncMock()
    ctx = LLMRequestContext(workspace_id="T1", channel_id="C1")

    with (
        patch("tagopen.llm.gateway.litellm.acompletion", new=AsyncMock(return_value=rebuilt)),
        patch("tagopen.llm.gateway.resolve_model", return_value="test-model"),
        patch("tagopen.llm.gateway.settings") as mock_settings,
    ):
        mock_settings.llm_stream = False
        mock_settings.llm_use_app_fallbacks = False
        mock_settings.fallback_models = []
        mock_settings.llm_timeout_seconds = 30.0

        await complete(
            ctx,
            messages=[{"role": "user", "content": "hi"}],
            on_first_token=first_token,
            stream=False,
        )

    first_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_first_token_reaction():
    from tagopen.slack_status import FIRST_TOKEN_EMOJI, SlackStatus

    client = MagicMock()
    client.reactions_add = AsyncMock(return_value={"ok": True})
    client.reactions_remove = AsyncMock(return_value={"ok": True})

    status = SlackStatus(client, channel_id="C1", thread_ts="1.0", event_ts="1.0")
    await status.llm_first_token()
    client.reactions_add.assert_awaited_with(
        channel="C1", timestamp="1.0", name=FIRST_TOKEN_EMOJI
    )
    await status.finish()
    assert any(
        c.kwargs.get("name") == FIRST_TOKEN_EMOJI for c in client.reactions_remove.await_args_list
    )
