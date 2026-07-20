"""Chunk long Slack replies and post them as ordered thread messages."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from tagopen.config import settings
from tagopen.slack_format import to_slack_mrkdwn

DEFAULT_MAX_CHARS = 3500
_CONTINUED = "…(continued)"

_FENCE_RE = re.compile(r"```[^\n]*\n[\s\S]*?(?:```|$)")
_HR_RE = re.compile(r"(?m)^---\s*$")


def chunk_slack_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split *text* into Slack-safe chunks.

    Prefers splits on blank lines between fenced ``` blocks and on ``---``
    section breaks. Avoids splitting inside a fence when possible; oversized
    fences are hard-split with a ``…(continued)`` marker.
    """
    if text is None:
        return [""]
    if len(text) <= max_chars:
        return [text]

    units = _split_units(text)
    chunks: list[str] = []
    current = ""

    for unit in units:
        for piece in _ensure_fits(unit, max_chars):
            if not current:
                current = piece
                continue
            if current.endswith("\n"):
                candidate = f"{current}\n{piece}" if not piece.startswith("\n") else current + piece
            else:
                candidate = f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(current)
                current = piece

    if current:
        chunks.append(current)
    return chunks or [""]


def _split_units(text: str) -> list[str]:
    """Tokenize into fence blocks and prose paragraphs (split on --- / blank lines)."""
    units: list[str] = []
    pos = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > pos:
            units.extend(_split_prose(text[pos : m.start()]))
        units.append(m.group(0).rstrip())
        pos = m.end()
    if pos < len(text):
        units.extend(_split_prose(text[pos:]))
    return [u for u in units if u.strip() != "" or u.startswith("```")]


def _split_prose(prose: str) -> list[str]:
    if not prose:
        return []
    # Split on --- section breaks; keep the marker with the following segment.
    parts: list[str] = []
    last = 0
    for m in _HR_RE.finditer(prose):
        before = prose[last : m.start()]
        parts.extend(_split_blank_lines(before))
        last = m.start()
    parts.extend(_split_blank_lines(prose[last:]))
    return [p for p in parts if p.strip() != ""]


def _split_blank_lines(text: str) -> list[str]:
    if not text:
        return []
    return [p for p in re.split(r"\n\s*\n", text) if p != ""]


def _ensure_fits(unit: str, max_chars: int) -> list[str]:
    if len(unit) <= max_chars:
        return [unit]
    if unit.lstrip().startswith("```"):
        return _hard_split_fence(unit, max_chars)
    return _hard_split_plain(unit, max_chars)


def _hard_split_fence(fence: str, max_chars: int) -> list[str]:
    m = re.match(r"^(```[^\n]*)\n([\s\S]*?)(?:\n```)?\s*$", fence)
    if not m:
        return _hard_split_plain(fence, max_chars)

    open_fence = m.group(1)
    body_lines = m.group(2).split("\n")
    pieces: list[str] = []
    buf: list[str] = []
    first = True
    idx = 0

    def render(lines: list[str], *, cont_start: bool, cont_end: bool) -> str:
        body = list(lines)
        if cont_start:
            body = [_CONTINUED, *body]
        if cont_end:
            body = [*body, _CONTINUED]
        return f"{open_fence}\n" + "\n".join(body) + "\n```"

    while idx < len(body_lines):
        cont_start = not first
        while idx < len(body_lines):
            trial = buf + [body_lines[idx]]
            cont_end = idx + 1 < len(body_lines)
            if len(render(trial, cont_start=cont_start, cont_end=cont_end)) <= max_chars:
                buf = trial
                idx += 1
                continue
            break

        if not buf:
            # One line alone exceeds the budget — character-cut it.
            line = body_lines[idx]
            lo, hi = 1, len(line)
            best = 1
            while lo <= hi:
                mid = (lo + hi) // 2
                rest_after = mid < len(line) or idx + 1 < len(body_lines)
                if len(render([line[:mid]], cont_start=cont_start, cont_end=rest_after)) <= max_chars:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            head, tail = line[:best], line[best:]
            rest = ([tail] if tail else []) + body_lines[idx + 1 :]
            pieces.append(
                render([head], cont_start=cont_start, cont_end=bool(rest))
            )
            body_lines = rest
            idx = 0
            first = False
            continue

        cont_end = idx < len(body_lines)
        pieces.append(render(buf, cont_start=cont_start, cont_end=cont_end))
        buf = []
        first = False

    if buf:
        pieces.append(render(buf, cont_start=not first and bool(pieces), cont_end=False))
    return pieces or _hard_split_plain(fence, max_chars)


def _hard_split_plain(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            pieces.append(remaining)
            break
        window = remaining[:max_chars]
        cut = window.rfind("\n\n")
        if cut < max_chars // 4:
            cut = window.rfind("\n")
        if cut < max_chars // 4:
            cut = max_chars
        chunk = remaining[:cut].rstrip("\n")
        remaining = remaining[cut:].lstrip("\n")
        if remaining:
            marker = "\n" + _CONTINUED
            if len(chunk) + len(marker) > max_chars:
                chunk = chunk[: max(0, max_chars - len(marker))] + marker
            else:
                chunk = chunk + marker
            if not remaining.startswith(_CONTINUED):
                remaining = _CONTINUED + "\n" + remaining
        pieces.append(chunk)
    return pieces


async def post_thread_messages(
    client: Any,
    *,
    channel: str,
    thread_ts: str,
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> None:
    """Chunk *text* and post each piece sequentially in the thread."""
    chunks = chunk_slack_text(text, max_chars=max_chars)
    for chunk in chunks:
        await asyncio.wait_for(
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=to_slack_mrkdwn(chunk),
            ),
            timeout=settings.slack_timeout_seconds,
        )
