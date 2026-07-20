"""Layered tool policy: safe defaults → workspace → channel → task approval."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from tagopen.tasks.models import ToolRisk

logger = logging.getLogger(__name__)

# Tools that are always read / safe by default
_READ_TOOLS = {
    "web_search",
    "search_channel_history",
    "list_tools",
    "skills_list",
    "skill_view",
    "task_status",
    "task_plan",
    "task_update",
    "task_pause",
    "task_resume",
    "task_cancel",
    "task_complete",
    "list_schedules",
}

_WRITE_TOOLS = {
    "memory_append",
    "memory_replace",
    "schedule_task",
    "pause_schedule",
    "resume_schedule",
    "delete_schedule",
}

_DESTRUCTIVE_PATTERNS = (
    re.compile(r"delete", re.I),
    re.compile(r"drop_", re.I),
    re.compile(r"destroy", re.I),
    re.compile(r"rm\b", re.I),
)


@dataclass
class ToolPolicyDecision:
    allowed: bool
    risk: ToolRisk
    requires_approval: bool
    reason: str = ""


def classify_risk(tool_name: str, channel_policy: dict[str, Any] | None = None) -> ToolRisk:
    policy = channel_policy or {}
    overrides = policy.get("tool_risk") or {}
    if tool_name in overrides:
        return ToolRisk(overrides[tool_name])
    if tool_name in _READ_TOOLS or tool_name.startswith("mcp_") and "lookup" in tool_name:
        return ToolRisk.READ
    if tool_name == "run_python":
        return ToolRisk.WRITE
    if tool_name in _WRITE_TOOLS:
        return ToolRisk.WRITE
    for pat in _DESTRUCTIVE_PATTERNS:
        if pat.search(tool_name):
            return ToolRisk.DESTRUCTIVE
    # MCP defaults: write unless allowlisted as read
    read_allow = set(policy.get("read_tools") or [])
    if tool_name in read_allow:
        return ToolRisk.READ
    write_allow = set(policy.get("write_tools") or [])
    if tool_name in write_allow:
        return ToolRisk.WRITE
    if tool_name.startswith("mcp_"):
        return ToolRisk.WRITE
    return ToolRisk.READ


def decide(
    tool_name: str,
    *,
    channel_policy: dict[str, Any] | None = None,
    preauthorized: bool = False,
    saas_mode: bool = False,
) -> ToolPolicyDecision:
    policy = channel_policy or {}
    deny = set(policy.get("deny_tools") or [])
    if tool_name in deny:
        return ToolPolicyDecision(False, ToolRisk.DESTRUCTIVE, False, "denied by channel policy")

    if tool_name == "run_python" and (saas_mode or policy.get("disable_run_python")):
        return ToolPolicyDecision(False, ToolRisk.WRITE, False, "run_python disabled until sandbox healthy")

    risk = classify_risk(tool_name, policy)
    if risk == ToolRisk.READ:
        return ToolPolicyDecision(True, risk, False)
    if preauthorized:
        return ToolPolicyDecision(True, risk, False, "pre-authorized")
    if risk == ToolRisk.DESTRUCTIVE:
        return ToolPolicyDecision(True, risk, True, "destructive requires approval")
    # WRITE
    auto_write = bool(policy.get("auto_approve_writes"))
    return ToolPolicyDecision(True, risk, not auto_write, "write requires approval" if not auto_write else "")


def args_hash(args: dict[str, Any]) -> str:
    blob = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def result_hash(result: Any) -> str:
    blob = str(result)[:8000]
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
