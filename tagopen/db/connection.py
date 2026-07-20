"""Workspace SQLite connection helpers."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from tagopen.db.migrations import apply_migrations


async def open_workspace_db(db_path: Path) -> aiosqlite.Connection:
    await apply_migrations(db_path)
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db
