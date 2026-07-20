"""Token-aware context engine with durable compaction."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, replace
from uuid import uuid4

from tagopen.agent.context import build_system_prompt
from tagopen.agent.skill_lifecycle import format_match_hint
from tagopen.config import settings
from tagopen.memory.store import MessageStore
from tagopen.tasks.models import Task

logger = logging.getLogger(__name__)


@dataclass
class ContextUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    context_window: int = 128_000


@dataclass
class ContextEngine:
    """Hermes-inspired pluggable context contract, simplified for Tango."""

    usage: ContextUsage = field(default_factory=ContextUsage)
    compact_threshold: float = 0.70

    def update_usage(self, prompt_tokens: int, completion_tokens: int = 0, total: int = 0) -> None:
        self.usage.prompt_tokens = prompt_tokens
        self.usage.completion_tokens = completion_tokens
        self.usage.total_tokens = total or (prompt_tokens + completion_tokens)

    def should_compact(self) -> bool:
        if self.usage.context_window <= 0:
            return False
        return self.usage.prompt_tokens >= int(self.usage.context_window * self.compact_threshold)

    async def build_context(
        self,
        *,
        channel_id: str,
        user_map: dict[str, str],
        tool_schemas: list[dict] | None,
        store: MessageStore,
        thread_ts: str,
        current_user: str,
        current_text: str,
        task: Task | None = None,
        memories: list[str] | None = None,
        compaction_summaries: list[str] | None = None,
    ) -> tuple[str, list[dict]]:
        system = build_system_prompt(channel_id, user_map, tool_schemas=tool_schemas)
        hint = format_match_hint(channel_id, current_text)
        if hint:
            system += "\n\n---\n\n" + hint
        if task:
            system += (
                "\n\n---\n\n## Active durable task\n\n"
                f"{task.to_summary()}\n\n"
                "Use task_plan / task_update / task_complete tools. "
                "Do not claim completion until task_complete succeeds."
            )
        if memories:
            system += "\n\n---\n\n## Retrieved memories\n\n" + "\n".join(f"- {m}" for m in memories[:12])
        if compaction_summaries:
            system += (
                "\n\n---\n\n## Compacted earlier context\n\n"
                + "\n\n".join(compaction_summaries[-3:])
            )

        recent = await store.get_recent_messages(
            limit=settings.context_window_messages,
            thread_ts=thread_ts,
        )
        messages: list[dict] = []
        for row in recent:
            role = "assistant" if row["role"] == "assistant" else "user"
            content = row["content"] or ""
            if role == "user":
                ts_str = str(row["ts"])[:16].replace("T", " ")
                name = row["display_name"] or row["user_id"] or "user"
                content = f"[{ts_str} @{name}] {content}"
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": f"[@{current_user}] {current_text}"})
        return system, messages

    async def compact(
        self,
        *,
        messages: list[dict],
        task: Task | None,
        llm_complete,
        ctx,
        task_store=None,
    ) -> tuple[list[dict], str]:
        """Summarize older turns; keep system-level protections in the summary text."""
        if len(messages) < 10:
            return messages, ""
        keep_tail = messages[-6:]
        to_summarize = messages[:-6]
        blob = json.dumps(to_summarize, default=str)[:40_000]
        protect = ""
        if task:
            protect = (
                f"Objective: {task.objective}\n"
                f"Acceptance: {task.acceptance_criteria}\n"
                f"Plan: {json.dumps([s.to_dict() for s in task.steps])}\n"
            )
        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the conversation for future turns. Preserve objectives, "
                    "acceptance criteria, active plan, decisions, unresolved tool results, "
                    "and open questions. Be concise."
                ),
            },
            {
                "role": "user",
                "content": f"Protected facts:\n{protect}\n\nConversation JSON:\n{blob}",
            },
        ]
        try:
            summary_ctx = replace(ctx, purpose="summary")
            resp, _ = await llm_complete(summary_ctx, messages=prompt)
            summary = resp.choices[0].message.content or ""
        except Exception:
            logger.exception("Compaction LLM failed")
            summary = f"(compaction failed) Kept objective: {task.objective if task else 'n/a'}"

        if task_store is not None and task is not None:
            await task_store.db.execute(
                """INSERT INTO compaction_summaries (
                     id, workspace_id, channel_id, thread_ts, task_id, summary, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"cmp_{uuid4().hex}",
                    task.workspace_id,
                    task.channel_id,
                    task.thread_ts,
                    task.id,
                    summary,
                    time.time(),
                ),
            )
            await task_store.db.commit()

        return keep_tail, summary
