"""LLM gateway — sole entry point with attribution metadata and usage recording."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import litellm

from tagopen.config import settings
from tagopen.llm.client import resolve_model
from tagopen.tasks.models import UsageRecord, new_id

if TYPE_CHECKING:
    from tagopen.tasks.store import SqliteTaskStore

logger = logging.getLogger(__name__)


@dataclass
class LLMRequestContext:
    workspace_id: str
    channel_id: str
    thread_ts: str = ""
    slack_user_id: str = ""
    task_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    purpose: str = "agent"
    request_id: str | None = None


def _usage_from_response(resp: Any) -> tuple[int, int, int, float, str]:
    usage = getattr(resp, "usage", None) or {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    elif not isinstance(usage, dict):
        usage = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    cost = float(getattr(resp, "_hidden_params", {}).get("response_cost") or 0.0)
    if not cost:
        try:
            cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:
            cost = 0.0
    call_id = str(getattr(resp, "id", "") or "")
    return prompt, completion, total, cost, call_id


def build_metadata(ctx: LLMRequestContext) -> dict[str, Any]:
    rid = ctx.request_id or f"req_{uuid4().hex}"
    return {
        "workspace_id": ctx.workspace_id,
        "channel_id": ctx.channel_id,
        "thread_ts": ctx.thread_ts,
        "slack_user_id": ctx.slack_user_id,
        "task_id": ctx.task_id or "",
        "run_id": ctx.run_id or "",
        "step_id": ctx.step_id or "",
        "request_id": rid,
        "purpose": ctx.purpose,
        "user": ctx.slack_user_id or "anonymous",
    }


async def complete(
    ctx: LLMRequestContext,
    *,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
    task_store: SqliteTaskStore | None = None,
    use_proxy_fallbacks: bool | None = None,
    **kwargs: Any,
) -> tuple[Any, str | None]:
    """Complete with attribution. Returns (response, failover_notice)."""
    model = kwargs.pop("model", None) or resolve_model(ctx.channel_id, ctx.thread_ts)
    meta = build_metadata(ctx)
    kwargs["metadata"] = {**(kwargs.get("metadata") or {}), **meta}
    kwargs.setdefault("timeout", settings.llm_timeout_seconds)

    use_app_fallbacks = (
        settings.llm_use_app_fallbacks
        if use_proxy_fallbacks is None
        else not use_proxy_fallbacks
    )
    chain = [model]
    if use_app_fallbacks:
        for fb in settings.fallback_models:
            if fb not in chain:
                chain.append(fb)

    last_err: Exception | None = None
    notice: str | None = None
    for i, m in enumerate(chain):
        try:
            kwargs["model"] = m
            resp = await litellm.acompletion(
                messages=messages,
                tools=tools or None,
                tool_choice=tool_choice if tools else None,
                **kwargs,
            )
            if i > 0:
                notice = f"↪️ switched to `{m}` (primary `{model}` failed)"
                logger.warning("LLM failover: %s → %s", model, m)

            prompt, completion, total, cost, call_id = _usage_from_response(resp)
            if task_store is not None:
                await task_store.record_usage(
                    UsageRecord(
                        id=new_id("llm_"),
                        workspace_id=ctx.workspace_id,
                        channel_id=ctx.channel_id,
                        thread_ts=ctx.thread_ts,
                        task_id=ctx.task_id,
                        run_id=ctx.run_id,
                        request_id=meta["request_id"],
                        litellm_call_id=call_id,
                        purpose=ctx.purpose,
                        model=m,
                        prompt_tokens=prompt,
                        completion_tokens=completion,
                        total_tokens=total,
                        cost_usd=cost,
                        created_at=time.time(),
                    )
                )
            return resp, notice
        except Exception as e:
            last_err = e
            logger.warning("LLM model %s failed: %s", m, e)
    assert last_err is not None
    raise last_err
