# LiteLLM Proxy scaffold (SaaS P3+)

Not used by Contabo `open-claude-tag.service` today (SDK in-process).

```bash
cp .env.example .env
# fill keys
docker compose up -d
curl -s http://127.0.0.1:4000/health/liveliness
```

See [docs/LITELLM-PROXY.md](../../docs/LITELLM-PROXY.md).
