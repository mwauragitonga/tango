"""Convert common Markdown to Slack mrkdwn for chat_postMessage."""

from __future__ import annotations

import html
import re


def strip_reply_artifacts(text: str) -> str:
    """Remove echoed history prefixes the model sometimes copies into replies."""
    if not text:
        return text
    cleaned = text.strip()
    # Drop leading [ts @name] / [@name] prefixes (one or more).
    while True:
        updated = re.sub(r"^\[[^\]]*@[^\]]+\]\s*", "", cleaned, count=1)
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned.strip()


def decode_html_entities(text: str) -> str:
    """Decode &amp; / &#x27; / &quot; etc. (search snippets and model copies often leak these)."""
    if not text:
        return text
    # Run twice in case of double-encoding (&amp;#x27; → &#x27; → ')
    once = html.unescape(text)
    return html.unescape(once)


def to_slack_mrkdwn(text: str) -> str:
    """Best-effort CommonMark -> Slack mrkdwn.

    Slack uses *bold* (single asterisk), not **bold**. Leaving ** unconverted
    shows literal asterisks in the client.
    """
    if not text:
        return text

    text = strip_reply_artifacts(text)
    text = decode_html_entities(text)

    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"@@SLACKFMT{len(placeholders) - 1}@@"

    # Protect fenced and inline code first
    text = re.sub(r"```[\s\S]*?```", _stash, text)
    text = re.sub(r"`[^`\n]+`", _stash, text)

    # Links [label](url) -> <url|label>
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r"<\2|\1>",
        text,
    )

    # Bare URLs that still contain &amp; → &
    text = re.sub(
        r"(https?://[^\s>|]+)",
        lambda m: decode_html_entities(m.group(1)),
        text,
    )

    # Headings -> bold line (and drop leftover lone # noise)
    text = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"*\1*", text)
    text = re.sub(r"(?m)^#{1,6}\s*$", "", text)

    # Strike ~~text~~ -> ~text~ (Slack)
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # Bold **text** / __text__ -> *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"*\1*", text)

    # Collapse accidental triple+ blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    def _restore(match: re.Match[str]) -> str:
        return placeholders[int(match.group(1))]

    text = re.sub(r"@@SLACKFMT(\d+)@@", _restore, text)
    return text.strip()
