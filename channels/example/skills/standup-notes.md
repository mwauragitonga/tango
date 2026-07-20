---
name: standup-notes
description: Turn messy channel chatter into a short standup summary
status: active
---

## When to use this

Someone asks for a standup, daily summary, or "what did we decide?" digest.

## Steps

1. Call `search_channel_history` for yesterday / today keywords if needed.
2. Group into *Shipped*, *In progress*, *Blockers*.
3. Keep it under 12 bullets; tag people with @names from the roster.
4. Do not invent work that was not mentioned.

## Known gotchas

- Prefer channel MEMORY.md decisions over speculative status.
