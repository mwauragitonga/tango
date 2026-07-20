#!/usr/bin/env bash
# Provision a workspace virtual key via LiteLLM control plane (master key only here).
# Usage: ./provision-workspace-key.sh <workspace_id> <team_alias>
set -euo pipefail
WS="${1:?workspace_id}"
TEAM="${2:-team-$WS}"
BASE="${LITELLM_PROXY_URL:-http://127.0.0.1:4000}"
MASTER="${LITELLM_MASTER_KEY:?}"

# Create team (= one Slack workspace)
curl -sS -X POST "$BASE/team/new" \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d "{\"team_alias\":\"$TEAM\",\"max_budget\":100,\"budget_duration\":\"30d\",\"models\":[\"tango-primary\",\"tango-fast\",\"tango-reasoning\",\"tango-summary\",\"kimi-k2.7-code\",\"gpt-5.4\"]}"

# Create service-account style key for the worker
curl -sS -X POST "$BASE/key/generate" \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d "{\"team_id\":\"$TEAM\",\"key_alias\":\"tango-worker-$WS\",\"max_budget\":50,\"budget_duration\":\"30d\",\"metadata\":{\"workspace_id\":\"$WS\",\"environment\":\"prod\",\"plan\":\"coworker\"}}"

echo
echo "Store the returned key in the secret manager; never put the master key in Tango workers."
