"""LiteLLM helpers — key injection, model resolution, per-channel / thread overrides.

LiteLLM reads provider keys from os.environ, not from arbitrary Python objects.
Call configure() once at startup to sync settings → os.environ.

Override order (highest wins):
  1. Thread override (`@Tango model …`) stored in SQLite
  2. tools.toml [llm] model = "..." in channel dir
  3. LLM_MODEL env / settings.llm_model

Failover: LLM_FALLBACKS is turn-local only (never sticky). Prefer Proxy routing when
settings.llm_use_app_fallbacks is False.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import litellm
import toml

from tagopen.config import settings

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True

_thread_model_cache: dict[tuple[str, str], str] = {}


def configure() -> None:
    """Sync API keys from settings → os.environ so LiteLLM can pick them up."""
    _set_if_nonempty("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    _set_if_nonempty("OPENAI_API_KEY", settings.openai_api_key)
    _set_if_nonempty("OPENAI_API_BASE", settings.openai_api_base)
    _set_if_nonempty("GEMINI_API_KEY", settings.gemini_api_key)
    _set_if_nonempty("GROQ_API_KEY", settings.groq_api_key)
    if settings.litellm_proxy_url:
        # Prefer Proxy as OpenAI-compatible base when configured
        _set_if_nonempty("OPENAI_API_BASE", settings.litellm_proxy_url)
        if settings.litellm_proxy_key:
            os.environ["OPENAI_API_KEY"] = settings.litellm_proxy_key

    logger.info("LLM configured — default model: %s", settings.llm_model)
    _log_available_providers()


def _set_if_nonempty(env_var: str, value: str) -> None:
    if value and not os.environ.get(env_var):
        os.environ[env_var] = value


def _log_available_providers() -> None:
    providers = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("Anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("OpenAI")
    if os.environ.get("GEMINI_API_KEY"):
        providers.append("Gemini")
    if os.environ.get("GROQ_API_KEY"):
        providers.append("Groq")
    if settings.litellm_proxy_url:
        providers.append(f"LiteLLM Proxy ({settings.litellm_proxy_url})")
    if providers:
        logger.info("Available LLM providers: %s", ", ".join(providers))
    else:
        logger.warning("No LLM provider API keys found — set at least one in .env")


def model_allowed(model: str) -> bool:
    allow = settings.model_allowlist
    if not allow:
        return True
    return model in allow


def cache_thread_model(channel_id: str, thread_ts: str, model: str | None) -> None:
    key = (channel_id, thread_ts)
    if model:
        _thread_model_cache[key] = model
    else:
        _thread_model_cache.pop(key, None)


def resolve_model(
    channel_id: str | None = None,
    thread_ts: str | None = None,
    thread_override: str | None = None,
) -> str:
    if thread_override:
        return thread_override
    if channel_id and thread_ts:
        cached = _thread_model_cache.get((channel_id, thread_ts))
        if cached:
            return cached
    if channel_id:
        override = _channel_model_override(channel_id)
        if override:
            return override
    return settings.llm_model


def _channel_model_override(channel_id: str) -> str | None:
    tools_toml = settings.channels_dir / channel_id / "tools.toml"
    if not tools_toml.exists():
        return None
    try:
        config = toml.loads(tools_toml.read_text())
        return config.get("llm", {}).get("model") or None
    except Exception:
        return None


def set_channel_model(channel_id: str, model: str) -> None:
    path = settings.channels_dir / channel_id / "tools.toml"
    config: dict[str, Any] = {}
    if path.exists():
        try:
            config = toml.loads(path.read_text())
        except Exception:
            config = {}
    config.setdefault("llm", {})["model"] = model
    path.parent.mkdir(parents=True, exist_ok=True)
    from tagopen.memory.files import atomic_write_text
    atomic_write_text(path, toml.dumps(config))


def clear_channel_model(channel_id: str) -> None:
    path = settings.channels_dir / channel_id / "tools.toml"
    if not path.exists():
        return
    try:
        config = toml.loads(path.read_text())
    except Exception:
        return
    llm = config.get("llm") or {}
    if "model" in llm:
        del llm["model"]
        if llm:
            config["llm"] = llm
        else:
            config.pop("llm", None)
        from tagopen.memory.files import atomic_write_text
        atomic_write_text(path, toml.dumps(config))


def describe_model_stack(channel_id: str, thread_ts: str | None = None) -> str:
    primary = resolve_model(channel_id, thread_ts)
    channel = _channel_model_override(channel_id)
    thread = _thread_model_cache.get((channel_id, thread_ts or ""), None) if thread_ts else None
    lines = [
        f"*Active model:* `{primary}`",
        f"*Env default:* `{settings.llm_model}`",
        f"*Channel pin:* `{channel or '(none)'}`",
        f"*Thread override:* `{thread or '(none)'}`",
    ]
    if settings.fallback_models and settings.llm_use_app_fallbacks:
        lines.append("*Fallbacks (turn-local):* " + ", ".join(f"`{m}`" for m in settings.fallback_models))
    if settings.model_allowlist:
        lines.append("*Allowlist:* " + ", ".join(f"`{m}`" for m in settings.model_allowlist))
    if settings.litellm_proxy_url:
        lines.append(f"*Proxy:* `{settings.litellm_proxy_url}`")
    lines.append(
        "Switch: `model <id>` · reset thread: `model reset` · pin channel: `model channel <id>`"
    )
    return "\n".join(lines)


async def acompletion(
    channel_id: str | None = None,
    thread_ts: str | None = None,
    thread_override: str | None = None,
    **kwargs,
):
    kwargs.setdefault(
        "model",
        resolve_model(channel_id, thread_ts, thread_override=thread_override),
    )
    return await litellm.acompletion(**kwargs)


async def acompletion_with_failover(
    channel_id: str | None = None,
    thread_ts: str | None = None,
    thread_override: str | None = None,
    **kwargs,
) -> tuple[Any, str | None]:
    """Try primary then LLM_FALLBACKS when app-level fallbacks are enabled."""
    primary = resolve_model(channel_id, thread_ts, thread_override=thread_override)
    chain = [primary]
    if settings.llm_use_app_fallbacks:
        for fb in settings.fallback_models:
            if fb not in chain:
                chain.append(fb)
    last_err: Exception | None = None
    for i, model in enumerate(chain):
        try:
            kwargs["model"] = model
            resp = await litellm.acompletion(**kwargs)
            notice = None
            if i > 0:
                notice = f"↪️ switched to `{model}` (primary `{primary}` failed)"
                logger.warning("LLM failover: %s → %s", primary, model)
            return resp, notice
        except Exception as e:
            last_err = e
            logger.warning("LLM model %s failed: %s", model, e)
    assert last_err is not None
    raise last_err


