"""LiteLLM gateway metadata attribution tests (no live provider)."""

from __future__ import annotations

from tagopen.llm.gateway import LLMRequestContext, build_metadata


def test_build_metadata_stable_tags():
    ctx = LLMRequestContext(
        workspace_id="T09P",
        channel_id="C09P",
        thread_ts="1.2",
        slack_user_id="U1",
        task_id="tsk_abc",
        run_id="run_1",
        step_id="s1",
        purpose="agent",
        request_id="req_fixed",
    )
    meta = build_metadata(ctx)
    assert meta["workspace_id"] == "T09P"
    assert meta["channel_id"] == "C09P"
    assert meta["task_id"] == "tsk_abc"
    assert meta["purpose"] == "agent"
    assert meta["request_id"] == "req_fixed"
    assert meta["user"] == "U1"
