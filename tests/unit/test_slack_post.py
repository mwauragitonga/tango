"""Unit tests for Slack chunked posting."""

from __future__ import annotations

from tagopen.slack_post import chunk_slack_text


def test_short_text_is_noop():
    text = "hello world"
    assert chunk_slack_text(text, max_chars=3500) == [text]


def test_split_between_fences():
    fence_a = "```python\n" + ("a = 1\n" * 40) + "```"
    fence_b = "```python\n" + ("b = 2\n" * 40) + "```"
    text = f"## a.py\n\n{fence_a}\n\n## b.py\n\n{fence_b}"
    # Force a small budget so the two fences cannot share a chunk.
    max_chars = max(len(fence_a), len(fence_b)) + 40
    chunks = chunk_slack_text(text, max_chars=max_chars)
    assert len(chunks) >= 2
    # Prefer not to split inside either fence.
    for c in chunks:
        opens = c.count("```")
        assert opens % 2 == 0, f"unbalanced fences in chunk: {c[:80]!r}"


def test_split_on_section_break():
    left = "Section one\n" + ("word " * 200)
    right = "Section two\n" + ("more " * 200)
    text = f"{left}\n\n---\n\n{right}"
    max_chars = max(len(left), len(right)) + 20
    chunks = chunk_slack_text(text, max_chars=max_chars)
    assert len(chunks) >= 2
    assert any("Section one" in c for c in chunks)
    assert any("Section two" in c for c in chunks)


def test_oversize_fence_hard_splits_with_continued():
    body = "x" * 5000
    text = f"```\n{body}\n```"
    chunks = chunk_slack_text(text, max_chars=800)
    assert len(chunks) >= 2
    assert any("…(continued)" in c for c in chunks)
    for c in chunks:
        assert c.strip().startswith("```")
        assert c.strip().endswith("```")
