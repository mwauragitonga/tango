"""SaaS tenancy: encrypted workspace credentials, OAuth scaffold, isolation helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tagopen.config import settings
from tagopen.memory.files import atomic_write_text

logger = logging.getLogger(__name__)


def _fernet():
    if not settings.credential_fernet_key:
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(settings.credential_fernet_key.encode())
    except Exception:
        logger.exception("Invalid credential_fernet_key")
        return None


def workspace_secret_path(workspace_id: str) -> Path:
    return settings.secrets_dir / f"{workspace_id}.json.enc"


def store_workspace_credentials(workspace_id: str, creds: dict[str, Any]) -> None:
    """Encrypt bot tokens; never store in channel Markdown."""
    settings.secrets_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(creds).encode()
    f = _fernet()
    path = workspace_secret_path(workspace_id)
    if f:
        atomic_write_text(path, f.encrypt(payload).decode())
    else:
        # Dev-only fallback
        logger.warning("Storing workspace credentials without Fernet (set CREDENTIAL_FERNET_KEY)")
        atomic_write_text(path.with_suffix(".json"), json.dumps(creds))


def load_workspace_credentials(workspace_id: str) -> dict[str, Any] | None:
    f = _fernet()
    enc = workspace_secret_path(workspace_id)
    plain = enc.with_suffix(".json")
    if f and enc.exists():
        return json.loads(f.decrypt(enc.read_text().encode()).decode())
    if plain.exists():
        return json.loads(plain.read_text())
    return None


def assert_tenant_scope(workspace_id: str, row_workspace_id: str) -> None:
    if workspace_id != row_workspace_id:
        raise PermissionError("cross-tenant access denied")


def memory_namespace(workspace_id: str, channel_id: str) -> str:
    return f"org/{workspace_id}/{channel_id}"
