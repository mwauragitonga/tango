"""Global settings loaded from environment / .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_mode: str = "socket"  # socket | http
    slack_signing_secret: str = ""
    slack_client_id: str = ""
    slack_client_secret: str = ""

    # LLM — LiteLLM model string
    llm_model: str = "claude-sonnet-4-6"
    llm_model_allowlist: str = ""
    llm_fallbacks: str = ""
    # When Proxy owns routing, set False to avoid duplicate fallback loops
    llm_use_app_fallbacks: bool = True
    llm_timeout_seconds: float = 120.0
    model_context_window: int = 128_000
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_api_base: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # LiteLLM Proxy
    litellm_proxy_url: str = ""
    litellm_proxy_key: str = ""

    # Web search
    web_search_provider: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    serper_api_key: str = ""
    firecrawl_api_key: str = ""

    hermes_api_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""

    # Storage
    data_dir: Path = Path("./data")
    secrets_dir: Path = Path("./data/secrets")

    # Limits / runtime
    default_max_tokens_per_request: int = 50_000
    default_max_tokens_per_day: int = 500_000
    context_window_messages: int = 50
    memory_max_chars: int = 8_000
    max_tool_rounds: int = 40
    max_tool_rounds_inline: int = 10
    tool_timeout_seconds: float = 60.0
    slack_timeout_seconds: float = 20.0
    progress_interval_seconds: float = 60.0
    saas_mode: bool = False
    enable_run_python: bool = True
    mem0_enabled: bool = False
    mem0_dsn: str = ""
    ambient_enabled: bool = True
    ambient_quiet_hours: str = ""  # e.g. "22-07" local
    ambient_monthly_budget_usd: float = 5.0

    # Temporal (optional SaaS adapter)
    temporal_enabled: bool = False
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"

    # Tenancy
    credential_fernet_key: str = ""

    @property
    def channels_dir(self) -> Path:
        return self.data_dir / "channels"

    @property
    def org_dir(self) -> Path:
        return self.data_dir / "org"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tagopen.db"

    @property
    def model_allowlist(self) -> list[str]:
        return [m.strip() for m in self.llm_model_allowlist.split(",") if m.strip()]

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallbacks.split(",") if m.strip()]


settings = Settings()  # type: ignore[call-arg]
