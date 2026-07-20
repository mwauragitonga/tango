"""Global settings loaded from environment / .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Slack
    slack_bot_token: str
    slack_app_token: str

    # LLM — LiteLLM model string, e.g. "gpt-4o", "claude-sonnet-4-6", "gemini/gemini-2.0-flash"
    llm_model: str = "claude-sonnet-4-6"
    # Comma-separated allowlist for @Tango model … (empty = allow any)
    llm_model_allowlist: str = ""
    # Comma-separated turn-local failover models (OpenClaw-style; not sticky)
    llm_fallbacks: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_api_base: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # Web search — auto-picks first configured provider; else ddgs (keyless)
    # Providers: tavily | brave | serper | firecrawl | ddgs
    web_search_provider: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    serper_api_key: str = ""
    firecrawl_api_key: str = ""

    # Optional Contabo Hermes API (for hermes MCP adapter examples only — not SaaS default)
    hermes_api_url: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""

    # Storage
    data_dir: Path = Path("./data")

    # Limits
    default_max_tokens_per_request: int = 50_000
    default_max_tokens_per_day: int = 500_000
    context_window_messages: int = 50
    memory_max_chars: int = 8_000

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
