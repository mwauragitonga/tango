# Changelog (Tango fork)

## Unreleased / 2026-07-20

Fork of [Anil-matcha/open-claude-tag](https://github.com/Anil-matcha/open-claude-tag) as **Tango** (`toshiusklay/tango`).

### Fixes

- **Crash:** import `asyncio` in `tagopen/gateway/router.py` (was `NameError` when creating session locks).
- **Slack mrkdwn:** convert CommonMark `**bold**` / headings / links / `~~strike~~` before `chat_postMessage` (`tagopen/slack_format.py`, used from `agent/loop.py`).
- **Reply hygiene:** strip echoed `[timestamp @agent]` / `[@name]` prefixes; do not prefix assistant history as `@agent` in `context.py` (that taught the model to leak prefixes into Slack).
- **sqlite3.Row:** use Row indexing (not `.get`) when attributing user history.
