"""Tool policy and skill validation tests."""

from __future__ import annotations

from tagopen.agent.skill_lifecycle import semantic_skill_candidates, validate_skill_content
from tagopen.tasks.models import ToolRisk
from tagopen.tools.policy import decide


def test_policy_layers():
    d = decide("web_search")
    assert d.risk == ToolRisk.READ and not d.requires_approval
    d = decide("memory_append")
    assert d.requires_approval
    d = decide("memory_append", channel_policy={"auto_approve_writes": True})
    assert not d.requires_approval
    d = decide("run_python", saas_mode=True)
    assert not d.allowed


def test_skill_validation(tmp_path, monkeypatch):
    ok, _ = validate_skill_content(
        "---\nname: demo\ndescription: Does a reusable thing for demos and docs\n---\n\n"
        "## When to use\nUse for demo walkthroughs.\n\n## Steps\n1. One\n2. Two\n3. Three\n"
    )
    assert ok
    bad, reason = validate_skill_content("---\nname: x\ndescription: y\n---\napi_key: sk-secret\n")
    assert not bad
