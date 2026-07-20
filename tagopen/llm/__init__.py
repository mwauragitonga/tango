"""LLM package — model resolution and attributed gateway."""

from tagopen.llm.client import (
    acompletion,
    acompletion_with_failover,
    cache_thread_model,
    clear_channel_model,
    configure,
    describe_model_stack,
    model_allowed,
    resolve_model,
    set_channel_model,
)
from tagopen.llm.gateway import LLMRequestContext, complete

__all__ = [
    "LLMRequestContext",
    "acompletion",
    "acompletion_with_failover",
    "cache_thread_model",
    "clear_channel_model",
    "complete",
    "configure",
    "describe_model_stack",
    "model_allowed",
    "resolve_model",
    "set_channel_model",
]
