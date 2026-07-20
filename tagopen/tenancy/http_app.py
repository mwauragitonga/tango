"""HTTP Events API + OAuth install flow for multi-workspace SaaS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from tagopen.config import settings
from tagopen.tenancy.credentials import store_workspace_credentials

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)


async def start_http(bolt_app: "AsyncApp") -> None:
    """Run Bolt with HTTP adapter (Events API) plus minimal OAuth routes via aiohttp."""
    from aiohttp import web
    from slack_bolt.adapter.aiohttp import AsyncSlackRequestHandler

    if not settings.slack_signing_secret:
        raise RuntimeError("SLACK_SIGNING_SECRET required for HTTP mode")

    handler = AsyncSlackRequestHandler(bolt_app)

    async def slack_events(request: web.Request) -> web.Response:
        return await handler.handle(request)

    async def oauth_start(request: web.Request) -> web.Response:
        params = urlencode(
            {
                "client_id": settings.slack_client_id,
                "scope": "app_mentions:read,chat:write,channels:history,groups:history,users:read",
                "redirect_uri": str(request.url.origin()) + "/slack/oauth/callback",
            }
        )
        raise web.HTTPFound(f"https://slack.com/oauth/v2/authorize?{params}")

    async def oauth_callback(request: web.Request) -> web.Response:
        code = request.rel_url.query.get("code")
        if not code:
            return web.Response(text="missing code", status=400)
        # Exchange via Slack Web API
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient()
        resp = await client.oauth_v2_access(
            client_id=settings.slack_client_id,
            client_secret=settings.slack_client_secret,
            code=code,
        )
        team = resp.get("team") or {}
        workspace_id = team.get("id") or "unknown"
        store_workspace_credentials(
            workspace_id,
            {
                "bot_token": resp.get("access_token"),
                "team_name": team.get("name"),
                "bot_user_id": (resp.get("bot_user_id") or ""),
            },
        )
        return web.Response(text=f"Installed for workspace {workspace_id}")

    async def admin_health(request: web.Request) -> web.Response:
        from tagopen.tools.mcp_client import mcp_health

        return web.json_response({"ok": True, "mcp": mcp_health()})

    aio = web.Application()
    aio.router.add_post("/slack/events", slack_events)
    aio.router.add_get("/slack/oauth/start", oauth_start)
    aio.router.add_get("/slack/oauth/callback", oauth_callback)
    aio.router.add_get("/admin/health", admin_health)
    # Retention/export stubs
    aio.router.add_post("/admin/workspaces/{wid}/export", _export_stub)
    aio.router.add_post("/admin/workspaces/{wid}/delete", _delete_stub)

    runner = web.AppRunner(aio)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(getattr(settings, "http_port", 3000) or 3000))
    await site.start()
    logger.info("Tango HTTP Events + OAuth listening")
    # Block forever
    import asyncio

    await asyncio.Event().wait()


async def _export_stub(request):
    from aiohttp import web

    wid = request.match_info["wid"]
    return web.json_response({"workspace_id": wid, "status": "export_queued"})


async def _delete_stub(request):
    from aiohttp import web

    wid = request.match_info["wid"]
    return web.json_response({"workspace_id": wid, "status": "deletion_queued"})
