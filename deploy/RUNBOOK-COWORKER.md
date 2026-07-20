# Stuck tasks / lease expiry / budget / proxy failover runbook

## Stuck task

1. `sqlite3 data/workspaces/<team>/messages.db "SELECT id,status,lease_owner,lease_expires_at,updated_at FROM tasks WHERE status NOT IN ('completed','failed','cancelled');"`
2. Post `status` in the Slack thread or `@Tango status`
3. If lease expired: worker auto-requeues to `resume_pending` on tick; or `resume`
4. If waiting_approval: `approve <id>` / `deny <id>`
5. Last resort: `cancel` then re-file objective

## Budget

1. Check Proxy team/key spend vs soft alert
2. Tango `llm_usage` daily reconcile (`deploy/litellm-proxy/reconcile-spend.sh`)
3. Raise budget via control-plane only (master key); rotate worker virtual key if leaked

## Proxy failover

1. Health: `curl -sf http://127.0.0.1:4000/health/liveliness`
2. If down: set `LLM_USE_APP_FALLBACKS=true` temporarily and point `OPENAI_API_BASE` back to provider
3. Do not rotate `LITELLM_SALT_KEY`

## Slack mid-run UX (Contabo)

- Mentions: `thinking_face` → first token `speech_balloon` → tool emoji → clear on finish
- Long replies: chunked via `tagopen/slack_post.py`
- Disable streaming: `LLM_STREAM=false` in `.env`, then `systemctl restart open-claude-tag`
- Canary channel: `#all-toshius-klay` (`C09P2TTBYV8`)

## Rollback

1. `systemctl stop open-claude-tag`
2. Restore `messages.db` + channel Markdown from backup
3. Redeploy previous git SHA
4. `systemctl start open-claude-tag`
