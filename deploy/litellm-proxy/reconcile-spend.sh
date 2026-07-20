#!/usr/bin/env bash
# Daily spend reconciliation stub: compare Tango llm_usage vs LiteLLM SpendLogs.
set -euo pipefail
echo "Export Tango llm_usage for date and diff against Proxy SpendLogs by request_id."
echo "Wire to your Postgres/SQLite export job; failures alert on missing attribution."
