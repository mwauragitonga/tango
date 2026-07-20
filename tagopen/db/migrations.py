"""SQLite schema migrations for Tango coworker runtime."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT NOT NULL,
            thread_ts    TEXT,
            channel_id   TEXT NOT NULL,
            role         TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            display_name TEXT NOT NULL,
            content      TEXT NOT NULL,
            tool_calls   INTEGER DEFAULT 0,
            created_at   REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            display_name,
            content='messages',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content, display_name)
            VALUES (new.id, new.content, new.display_name);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content, display_name)
            VALUES ('delete', old.id, old.content, old.display_name);
        END;

        CREATE TABLE IF NOT EXISTS thread_models (
            channel_id  TEXT NOT NULL,
            thread_ts   TEXT NOT NULL,
            model       TEXT NOT NULL,
            updated_at  REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
            PRIMARY KEY (channel_id, thread_ts)
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS slack_events (
            workspace_id TEXT NOT NULL,
            event_key    TEXT NOT NULL,
            task_id      TEXT,
            created_at   REAL NOT NULL DEFAULT (unixepoch('now', 'subsec')),
            PRIMARY KEY (workspace_id, event_key)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id                   TEXT PRIMARY KEY,
            workspace_id         TEXT NOT NULL,
            channel_id           TEXT NOT NULL,
            thread_ts            TEXT NOT NULL,
            requester_user_id    TEXT NOT NULL,
            objective            TEXT NOT NULL,
            acceptance_criteria  TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL,
            steps_json           TEXT NOT NULL DEFAULT '[]',
            current_step_id      TEXT,
            next_action          TEXT NOT NULL DEFAULT '',
            blocker              TEXT NOT NULL DEFAULT '',
            turns_used           INTEGER NOT NULL DEFAULT 0,
            max_turns            INTEGER NOT NULL DEFAULT 40,
            lease_owner          TEXT,
            lease_expires_at     REAL,
            checkpoint_json      TEXT NOT NULL DEFAULT '{}',
            created_at           REAL NOT NULL,
            updated_at           REAL NOT NULL,
            completed_at         REAL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_thread ON tasks(workspace_id, channel_id, thread_ts);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, lease_expires_at);

        CREATE TABLE IF NOT EXISTS task_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id    TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload    TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
        );

        CREATE TABLE IF NOT EXISTS tool_executions (
            id                TEXT PRIMARY KEY,
            task_id           TEXT,
            workspace_id      TEXT NOT NULL,
            channel_id        TEXT NOT NULL,
            thread_ts         TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            args_hash         TEXT NOT NULL,
            result_hash       TEXT NOT NULL,
            risk              TEXT NOT NULL,
            success           INTEGER NOT NULL,
            latency_ms        REAL NOT NULL,
            error_class       TEXT NOT NULL DEFAULT '',
            requester_user_id TEXT NOT NULL DEFAULT '',
            approver_user_id  TEXT NOT NULL DEFAULT '',
            created_at        REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id                TEXT PRIMARY KEY,
            task_id           TEXT NOT NULL,
            tool_name         TEXT NOT NULL,
            args_json         TEXT NOT NULL,
            status            TEXT NOT NULL,
            requester_user_id TEXT NOT NULL DEFAULT '',
            approver_user_id  TEXT NOT NULL DEFAULT '',
            created_at        REAL NOT NULL,
            resolved_at       REAL
        );

        CREATE TABLE IF NOT EXISTS llm_usage (
            id               TEXT PRIMARY KEY,
            workspace_id     TEXT NOT NULL,
            channel_id       TEXT NOT NULL,
            thread_ts        TEXT NOT NULL,
            task_id          TEXT,
            run_id           TEXT,
            request_id       TEXT NOT NULL,
            litellm_call_id  TEXT NOT NULL DEFAULT '',
            purpose          TEXT NOT NULL,
            model            TEXT NOT NULL,
            prompt_tokens    INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens     INTEGER NOT NULL DEFAULT 0,
            cost_usd         REAL NOT NULL DEFAULT 0,
            created_at       REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id            TEXT PRIMARY KEY,
            workspace_id  TEXT NOT NULL,
            channel_id    TEXT NOT NULL,
            cron          TEXT NOT NULL,
            description   TEXT NOT NULL,
            enabled       INTEGER NOT NULL DEFAULT 1,
            next_run_at   REAL,
            last_run_at   REAL,
            created_by    TEXT NOT NULL DEFAULT '',
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memories (
            id           TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            channel_id   TEXT NOT NULL,
            kind         TEXT NOT NULL,
            content      TEXT NOT NULL,
            provenance   TEXT NOT NULL DEFAULT '',
            author       TEXT NOT NULL DEFAULT '',
            confidence   REAL NOT NULL DEFAULT 0.7,
            supersedes   TEXT,
            created_at   REAL NOT NULL,
            updated_at   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_stats (
            channel_id   TEXT NOT NULL,
            skill_name   TEXT NOT NULL,
            uses         INTEGER NOT NULL DEFAULT 0,
            successes    INTEGER NOT NULL DEFAULT 0,
            failures     INTEGER NOT NULL DEFAULT 0,
            last_used    REAL,
            status       TEXT NOT NULL DEFAULT 'active',
            version      INTEGER NOT NULL DEFAULT 1,
            checksum     TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (channel_id, skill_name)
        );

        CREATE TABLE IF NOT EXISTS compaction_summaries (
            id            TEXT PRIMARY KEY,
            workspace_id  TEXT NOT NULL,
            channel_id    TEXT NOT NULL,
            thread_ts     TEXT NOT NULL,
            task_id       TEXT,
            summary       TEXT NOT NULL,
            source_from_id INTEGER,
            source_to_id   INTEGER,
            created_at    REAL NOT NULL
        );
        """,
    ),
]


async def apply_migrations(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version INTEGER PRIMARY KEY,
                   applied_at REAL NOT NULL DEFAULT (unixepoch('now', 'subsec'))
               )"""
        )
        await db.commit()
        async with db.execute("SELECT version FROM schema_migrations") as cur:
            applied = {int(row[0]) for row in await cur.fetchall()}
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            logger.info("Applying schema migration v%s to %s", version, db_path)
            await db.executescript(sql)
            await db.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
            await db.commit()
