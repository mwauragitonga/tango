# LiteLLM Proxy (SaaS multi-tenant milestone)

**Contabo / P1:** keep the in-process LiteLLM **SDK** (`tagopen/llm.py`).

**SaaS preview (P3+):** run [LiteLLM Proxy](https://docs.litellm.ai/docs/simple_proxy) as a gateway for virtual keys, per-tenant budgets, rate limits, and centralized spend logs.

## Why

- SDK alone cannot enforce shared budgets/keys across Slack workspaces.
- Proxy adds Postgres-backed keys/spend and optional Redis for distributed rate limits.
- Tango keeps calling an OpenAI-compatible API; only `OPENAI_API_BASE` / key change.

## Scaffolding in this repo

See [`deploy/litellm-proxy/`](../deploy/litellm-proxy/):

```bash
cd deploy/litellm-proxy
cp .env.example .env   # set LITELLM_MASTER_KEY, provider keys
docker compose up -d
# Proxy: http://127.0.0.1:4000
```

Point Tango (or a SaaS worker) at the proxy:

```bash
OPENAI_API_BASE=http://127.0.0.1:4000
OPENAI_API_KEY=<virtual-key-or-master>
LLM_MODEL=openai/kimi-k2.7-code   # still a LiteLLM model id / proxy alias
```

## Ops notes

- Run 2+ proxy replicas behind a load balancer in production; share Postgres + Redis.
- Do not put Contabo Hermes behind this proxy for SaaS tenants.
- Escape hatch: native provider SDKs if a LiteLLM transform lags a critical API.
