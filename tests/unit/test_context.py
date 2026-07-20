"""Context engine compaction threshold and protection."""

from __future__ import annotations

from tagopen.context.engine import ContextEngine, ContextUsage


def test_should_compact():
    eng = ContextEngine(usage=ContextUsage(prompt_tokens=90_000, context_window=100_000))
    assert eng.should_compact()
    eng2 = ContextEngine(usage=ContextUsage(prompt_tokens=10_000, context_window=100_000))
    assert not eng2.should_compact()
