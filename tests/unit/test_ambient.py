"""Heartbeat decision + quiet hours + skip-when-busy helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tagopen.ambient.heartbeat import (
    _is_heartbeat_task,
    _is_slack_ts,
    build_observation,
    decide_heartbeat,
    run_heartbeat_enqueue,
)
from tagopen.gateway.approve import parse_approve_command


def test_heartbeat_dedupe_and_post():
    class T:
        id = "tsk_abc"
        status = type("S", (), {"value": "waiting_approval"})()
        objective = "Do a thing"
        requester_user_id = "U1"

    from tagopen.ambient import heartbeat as hb

    hb._recent_nudge_hashes.clear()
    obs = build_observation([T()], ["stale thread"])
    d1 = decide_heartbeat(obs)
    assert d1["action"] == "post"
    hb._recent_nudge_hashes[d1["hash"]] = __import__("time").time()
    d2 = decide_heartbeat(obs)
    assert d2["action"] == "silent"


def test_is_slack_ts_and_heartbeat_task():
    assert _is_slack_ts("1712345678.123456")
    assert not _is_slack_ts("heartbeat-C123-1712345678")
    assert not _is_slack_ts("")
    assert not _is_slack_ts(None)

    class Hb:
        requester_user_id = "heartbeat"
        objective = "x"

    class HbObj:
        requester_user_id = "U1"
        objective = "[heartbeat] nudge"

    class User:
        requester_user_id = "U1"
        objective = "ship it"

    assert _is_heartbeat_task(Hb())
    assert _is_heartbeat_task(HbObj())
    assert not _is_heartbeat_task(User())


def test_observation_excludes_heartbeat_tasks():
    class S:
        def __init__(self, v):
            self.value = v

    class T:
        def __init__(self, tid, status, objective, requester="U1"):
            self.id = tid
            self.status = S(status)
            self.objective = objective
            self.requester_user_id = requester

    obs = build_observation(
        [
            T("a", "paused", "real work"),
            T("b", "queued", "[heartbeat] x", requester="heartbeat"),
        ],
        [],
    )
    assert obs["open_tasks"] == 1
    assert obs["items"][0]["task_id"] == "a"


@pytest.mark.asyncio
async def test_heartbeat_skips_active_user_work_no_create_task():
    from tagopen.ambient import heartbeat as hb

    hb._recent_nudge_hashes.clear()

    class S:
        def __init__(self, v):
            self.value = v

    class T:
        def __init__(self):
            self.id = "tsk_user"
            self.status = S("running")
            self.objective = "do real work"
            self.requester_user_id = "U1"
            self.thread_ts = "1712345678.123456"
            self.updated_at = 0.0

    store = MagicMock()

    class _Ctx:
        async def __aenter__(self):
            cur = AsyncMock()
            cur.fetchall = AsyncMock(return_value=[("C1",)])
            return cur

        async def __aexit__(self, *a):
            return False

    store.db.execute = MagicMock(return_value=_Ctx())
    store.list_open_for_channel = AsyncMock(return_value=[T()])

    app = MagicMock()
    app.client.chat_postMessage = AsyncMock()

    await run_heartbeat_enqueue(app, store, "W1")

    app.client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_heartbeat_posts_without_fake_thread_ts():
    from tagopen.ambient import heartbeat as hb

    hb._recent_nudge_hashes.clear()

    class S:
        def __init__(self, v):
            self.value = v

    class T:
        def __init__(self):
            self.id = "tsk_paused"
            self.status = S("paused")
            self.objective = "paused work"
            self.requester_user_id = "U1"
            self.thread_ts = "1712345678.999999"
            self.updated_at = 0.0

    store = MagicMock()

    class _Ctx:
        async def __aenter__(self):
            cur = AsyncMock()
            cur.fetchall = AsyncMock(return_value=[MagicMock(__getitem__=lambda s, i: "C1")])
            return cur

        async def __aexit__(self, *a):
            return False

    store.db.execute = MagicMock(return_value=_Ctx())
    store.list_open_for_channel = AsyncMock(return_value=[T()])

    app = MagicMock()
    app.client.chat_postMessage = AsyncMock()

    await run_heartbeat_enqueue(app, store, "W1")

    app.client.chat_postMessage.assert_awaited_once()
    kwargs = app.client.chat_postMessage.await_args.kwargs
    assert kwargs["channel"] == "C1"
    assert kwargs["thread_ts"] == "1712345678.999999"
    assert not str(kwargs.get("thread_ts", "")).startswith("heartbeat-")


def test_parse_approve_command_short_and_with_id():
    assert parse_approve_command("approve") == ("approve", None)
    assert parse_approve_command("deny") == ("deny", None)
    assert parse_approve_command("  Approve  ") == ("approve", None)
    assert parse_approve_command("approve apr_abc") == ("approve", "apr_abc")
    assert parse_approve_command("deny apr_xyz") == ("deny", "apr_xyz")
    assert parse_approve_command("approve please") == ("approve", "please")
    assert parse_approve_command("yes") is None
    assert parse_approve_command("approve this now") is None
