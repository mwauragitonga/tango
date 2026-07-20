"""Atomic Markdown file helpers for channel memory / config."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def locked_update(path: Path, mutator) -> str:
    """Acquire exclusive lock, read, mutate, write atomically. Returns new content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            updated = mutator(current)
            atomic_write_text(path, updated)
            return updated
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def memory_append(path: Path, entry: str) -> None:
    entry = entry.strip()
    if not entry:
        return

    def mutator(current: str) -> str:
        return current.rstrip() + f"\n- {entry}\n"

    locked_update(path, mutator)


def memory_replace(path: Path, old: str, new: str) -> None:
    def mutator(current: str) -> str:
        return current.replace(old, new)

    locked_update(path, mutator)
