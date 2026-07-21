# Multimodal attachments (Hermes-style)

Tango borrows Hermes Agent’s **download → cache → typed inject** pipeline. It does **not** wrap Hermes or treat every file as native multimodal tokens.

```text
Slack upload → files:read download → data/media/<workspace>/<channel>/
  → image  → native image_url parts  OR  vision_analyze text (auto)
  → small UTF-8 text/csv/json → inline (≤ MEDIA_INLINE_TEXT_MAX_BYTES)
  → PDF/Office/xlsx → path note + read_attachment
```

## Config

| Env | Default | Meaning |
|-----|---------|---------|
| `IMAGE_INPUT_MODE` | `auto` | `auto` \| `native` \| `text` |
| `LLM_VISION_CAPABILITY` | `auto` | Force `true`/`false`, or heuristic from model id |
| `LLM_VISION_MODELS` | _(empty)_ | Optional comma allowlist of vision model ids |
| `VISION_MODEL` | _(empty)_ | Aux model for text-mode image describe |
| `MEDIA_MAX_BYTES` | `20971520` | Per-file download cap (~20 MB Slack-ish) |
| `MEDIA_INLINE_TEXT_MAX_BYTES` | `102400` | Max UTF-8 inline (~100 KiB) |

With Contabo’s default `openai/kimi-k2.7-code`, `auto` usually picks **text** mode (aux `VISION_MODEL` or a vision fallback). Set `LLM_VISION_CAPABILITY=true` only if the active model truly accepts image parts.

## Slack ingress

- `app_mention` — primary; reads `event.files`
- Thread `message` with subtype `file_share` — allowed when the text still `@mention`s the bot (other subtypes stay ignored)

## Slack scopes

Bot scope **`files:read`** is required to download `url_private` / `url_private_download`. See [SLACK-SAAS-MANIFEST.md](./SLACK-SAAS-MANIFEST.md). Reinstall / re-authorize Contabo and SaaS apps after adding the scope.

`files:write` is **not** required for inbound handling (outbound deliverable uploads are out of scope for this pass).

## Tools

- **`read_attachment`** — read/extract from paths under `data/media/` only (PDF best-effort if pymupdf/pypdf installed).

## Session semantics

Native image pixels are **turn-scoped**: durable checkpoints strip `image_url` parts and keep text + attachment path metadata (Hermes-like). Re-attach pixels from cache on the first worker build when still present.

## Code map

| Path | Role |
|------|------|
| `tagopen/media/prepare.py` | Download + classify + route |
| `tagopen/media/routing.py` | native vs text decision |
| `tagopen/media/vision.py` | aux describe |
| `tagopen/media/read_attachment.py` | tool impl |
| `tagopen/gateway/router.py` | wires Slack `files` into the agent loop |
