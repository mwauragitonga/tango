# Slack app manifests — Tango SaaS

Two Slack apps (do **not** reuse Contabo Socket Mode credentials):

| Variant | Purpose | Distribution |
|---------|---------|--------------|
| **SaaS preview** | Invite-only OAuth installs; ship without App Directory review | Manage Distribution → **Distribute App** (shareable install URL), do **not** submit to Directory |
| **App Directory** | Public listing | Submit for review with minimum justifiable scopes |

Runtime for both SaaS variants: `SLACK_MODE=http` (Events API + OAuth). Contabo stays on Socket Mode (`SLACK_MODE=socket`).

Code paths: `tagopen/gateway/app.py`, `tagopen/tenancy/http_app.py`, `tagopen/gateway/users.py`.

---

## URL patterns (placeholders)

Replace `api.example.com` with the SaaS API host.

| Endpoint | Method | Role |
|----------|--------|------|
| `https://api.example.com/slack/oauth/start` | GET | Kick off OAuth (`oauth_start` in `http_app.py`) |
| `https://api.example.com/slack/oauth/callback` | GET | OAuth redirect (must be listed in manifest `redirect_urls`) |
| `https://api.example.com/slack/events` | POST | Events Request URL (url_verification + events); Bolt handler |

Staging + prod: list **both** callback URLs under `oauth_config.redirect_urls` and verify **both** Events Request URLs in the Slack UI (or use separate Slack apps per env).

Interactivity is **off** today — HITL is plain-text `approve <id>` / `deny <id>` in threads (`gateway/app.py`). Enable interactivity only when Block Kit buttons ship.

---

## Contabo (Socket Mode) vs SaaS customers

| | Contabo (self-hosted) | SaaS customers |
|--|----------------------|----------------|
| Slack connection | **Socket Mode** ON; App-Level Token `xapp-…` (`connections:write`) | **Socket Mode OFF**; HTTP Events API |
| Tokens in `.env` | `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` | `SLACK_SIGNING_SECRET` + `SLACK_CLIENT_ID` + `SLACK_CLIENT_SECRET`; per-workspace `xoxb` from OAuth store |
| Public URL | Not required | Required (`/slack/events`, OAuth callback) |
| Install | Manual Install to Workspace | OAuth (`/slack/oauth/start`) |
| nginx | None for Slack | Terminate TLS → Tango HTTP |
| Hermes MCP bridge | Optional Contabo-only | **Never** |
| Slack app | Dedicated Contabo app (keep as-is) | **Separate** SaaS app(s) — preview and/or Directory |

---

## Scope table

| Scope | Why Tango needs it | Preview | Directory |
|-------|-------------------|---------|-----------|
| `app_mentions:read` | Receive `@Tango` (`app_mention`) | include | include |
| `chat:write` | Replies, progress, approve/deny responses (`chat.postMessage`) | include | include |
| `channels:history` | Public channel/thread context; required with `message.channels` | include | include |
| `channels:read` | Channel metadata; `conversations.members` for attribution (`users.py`) | include | include |
| `groups:history` | Private channel/thread context + `message.groups` | include | include |
| `groups:read` | Private channel metadata / `conversations.members` | include | include |
| `reactions:write` | Status reactions add/remove on mentions | include | include |
| `users:read` | Display names via `users.info` | include | include |
| `files:read` | Download user-uploaded images/docs on `@Tango` turns ([MULTIMODAL.md](./MULTIMODAL.md)) | include | include |
| `channels:join` | `conversations.join` without `/invite` (Contabo convenience) | include | **exclude** — `/invite @Tango` is enough; reviewers prefer less privilege |
| `reactions:read` | Not used | exclude | exclude |
| `files:write`, `im:*`, `mpim:*`, `commands`, `users:read.email` | Not used (inbound-only media; no Slack file uploads yet) | exclude | exclude |
| User (non-bot) scopes | Not used | exclude | exclude |

### Bot events

| Event | Why | Preview | Directory |
|-------|-----|---------|-----------|
| `app_mention` | Primary intake | include | include |
| `message.channels` | Thread `approve`/`deny`/`resume` without second @mention (public) | include | include |
| `message.groups` | Same HITL in private channels | include | include |

Directory justification for `message.*`: human-in-the-loop tool approval is text in the same thread; requiring another `@Tango` for every approve/deny breaks the coworker UX. Handler ignores non-thread, bot, and subtype noise.

---

## 1) SaaS preview manifest (unlisted / invite-only)

Create via [api.slack.com/apps](https://api.slack.com/apps) → **From an app manifest**. After create: **Manage Distribution** → activate distribution **without** App Directory submission; share the install link with invitees only.

```yaml
display_information:
  name: Tango
  description: Channel-native AI coworker for Slack. @mention in a channel for shared team context, thread progress, and human-in-the-loop tool approvals.
  background_color: "#1a1a2e"
  long_description: |
    Tango is a multiplayer AI teammate that lives in your Slack channels—not a private DM assistant.
    Invite @Tango, then @mention it so the whole channel shares one agent context, durable tasks,
    and approve/deny gates for write tools. Model-agnostic (LiteLLM) with optional MCP tools per channel.

    This preview app is invite-only (not listed in the Slack App Directory).

features:
  bot_user:
    display_name: Tango
    always_online: true

oauth_config:
  redirect_urls:
    - https://api.example.com/slack/oauth/callback
    # - https://api-staging.example.com/slack/oauth/callback
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - channels:history
      - channels:read
      - channels:join
      - groups:history
      - groups:read
      - reactions:write
      - users:read
      - files:read

settings:
  event_subscriptions:
    request_url: https://api.example.com/slack/events
    bot_events:
      - app_mention
      - message.channels
      - message.groups
  interactivity:
    is_enabled: false
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

**After paste:** verify Events Request URL (Slack must reach `POST /slack/events` and complete `url_verification`). Copy **Signing Secret**, **Client ID**, **Client Secret** into SaaS env. Align OAuth authorize `scope=` with the bot list above (see `tenancy/http_app.py`). Re-install the Contabo Socket Mode app after adding `files:read`.

---

## 2) App Directory submission manifest (minimum justifiable)

Same product surface, **without** `channels:join`. Use a **separate** Slack app from preview so Directory review does not inherit experimental scopes.

```yaml
display_information:
  name: Tango
  description: Channel-native AI coworker for Slack—shared team context, thread tasks, and human-in-the-loop tool approvals.
  background_color: "#1a1a2e"
  long_description: |
    Tango is a channel-scoped AI coworker for Slack. Teams invite @Tango into a channel, @mention it
    to ask questions or start work, and continue in-thread—including plain-text approve/deny for
    sensitive tool actions. One shared agent identity per channel; attribution by Slack display name.

    Tango does not read DMs or post outside channels you invite it to. Private channels are supported
    when the bot is a member. Optional MCP integrations are configured by your workspace admin.

features:
  bot_user:
    display_name: Tango
    always_online: true

oauth_config:
  redirect_urls:
    - https://api.example.com/slack/oauth/callback
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - channels:history
      - channels:read
      - groups:history
      - groups:read
      - reactions:write
      - users:read
      - files:read

settings:
  event_subscriptions:
    request_url: https://api.example.com/slack/events
    bot_events:
      - app_mention
      - message.channels
      - message.groups
  interactivity:
    is_enabled: false
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

---

## App Directory review checklist

### Required assets / pages

- [ ] **Privacy policy URL** (public HTTPS) — what message/metadata you store, retention, subprocessors (LLM provider, hosting), no training on customer data if that is your policy, how to request deletion
- [ ] **Support URL** — docs or email/`mailto:` / status page; must work without login for reviewers
- [ ] **App icon** — 512×512 PNG; matches `display_information.name`
- [ ] **Short + long description** — match manifest; avoid “we scrape your workspace”
- [ ] **Landing / install page** — explains invite `@Tango`, `@mention` usage, private-channel support, data handling

### Demo video (typical Slack expectations)

- [ ] 2–5 min, no NDAs; use a **throwaway demo workspace**
- [ ] Show: install OAuth → invite to channel → `@Tango` Q&A → thread reply → `approve`/`deny` HITL if you claim it
- [ ] Show private channel only if you request `groups:*`
- [ ] Narrate **why** each sensitive scope/event (`message.channels` / `groups:history`) is needed
- [ ] Do **not** show Contabo Socket Mode, Hermes, or OpenClaw

### Security questionnaire tips

- [ ] Events verified with **signing secret** (`SLACK_SIGNING_SECRET`); reject unsigned payloads
- [ ] Tokens encrypted at rest (workspace credential store); least-privilege scopes
- [ ] Socket Mode **disabled** for the Directory app
- [ ] No user token scopes; bot-only
- [ ] Tenant isolation by Slack `team_id` / workspace id
- [ ] Retention / export / delete endpoints (even if stubbed for review, describe the real path)
- [ ] LLM: data sent to inference provider; state your training / retention stance
- [ ] Rate limits / abuse controls on Events URL
- [ ] If MCP tools call external systems: admin allowlists, HITL for writes

### Scope/event Q&A (prepare answers)

| Reviewer question | Answer sketch |
|-------------------|---------------|
| Why `message.channels` / `message.groups`? | Thread-only HITL (`approve`/`deny`) and resume; ignore top-level channel noise and bot messages |
| Why `groups:*`? | Same coworker UX in private channels the bot is invited to |
| Why not `channels:join`? | Omitted on Directory; users `/invite @Tango` |
| Why `reactions:write`? | Ephemeral status reactions while processing a mention |
| Why `users:read`? | Display names for multiplayer attribution — not email |
| Why `files:read`? | Download images/docs attached to `@Tango` mentions into a workspace cache; no `files:write` |

### Process

- [ ] Separate Slack app from Contabo + from preview (clean scope history)
- [ ] Production Request URL + Redirect URL verified green
- [ ] Submit **App Directory** → complete questionnaire + video + policy/support links
- [ ] Expect questions on message subscriptions and private-channel scopes; reply with the table above

---

## OAuth `scope` query string (keep in sync)

Preview authorize scopes (matches preview manifest):

```text
app_mentions:read,chat:write,channels:history,channels:read,channels:join,groups:history,groups:read,reactions:write,users:read,files:read
```

Directory authorize scopes:

```text
app_mentions:read,chat:write,channels:history,channels:read,groups:history,groups:read,reactions:write,users:read,files:read
```

Update `tagopen/tenancy/http_app.py` `oauth_start` `scope=` to match the app you ship (preview vs Directory). A mismatch causes silent missing_scope at runtime.
