"""Operational metrics helpers for stuck tasks, leases, proxy errors."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


async def task_health_snapshot(store, workspace_id: str) -> dict[str, Any]:
    now = time.time()
    async with store.db.execute(
        """SELECT status, COUNT(*) AS n FROM tasks
           WHERE workspace_id = ? GROUP BY status""",
        (workspace_id,),
    ) as cur:
        by_status = {r["status"]: r["n"] for r in await cur.fetchall()}
    async with store.db.execute(
        """SELECT COUNT(*) AS n FROM tasks
           WHERE workspace_id = ?
             AND status IN ('running','planning','verifying')
             AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
        (workspace_id, now),
    ) as cur:
        expired = (await cur.fetchone())["n"]
    async with store.db.execute(
        """SELECT COUNT(*) AS n FROM llm_usage WHERE workspace_id = ? AND created_at > ?""",
        (workspace_id, now - 86400),
    ) as cur:
        llm_24h = (await cur.fetchone())["n"]
    return {
        "by_status": by_status,
        "expired_leases": expired,
        "llm_calls_24h": llm_24h,
        "alerts": _alerts(by_status, expired),
    }


def _alerts(by_status: dict[str, int], expired: int) -> list[str]:
    alerts = []
    if expired:
        alerts.append(f"expired_leases:{expired}")
    if by_status.get("waiting_approval", 0) > 20:
        alerts.append("approval_backlog")
    if by_status.get("failed", 0) > 10:
        alerts.append("elevated_failures")
    return alerts
