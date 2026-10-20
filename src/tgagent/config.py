"""Configuration loader validating environment variables and settings.toml.

Uses Pydantic v2 and Python 3.11 standard library tomllib.
"""

import os
import tomllib
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AccessConfig(BaseModel):
    admin_user_ids: list[int] = Field(default_factory=list)
    require_admin_approval: bool = True


class LimitsConfig(BaseModel):
    max_tasks_per_user: int = 5
    max_channels_per_task: int = 10
    min_interval_seconds: int = 60
    max_concurrent_executions: int = 3
    max_concurrent_executions_per_user: int = 1
    execution_timeout_seconds: int = 180
    max_deliveries_per_run: int = 10
    daily_llm_calls_per_user: int = 2000
    max_posts_per_channel_per_run: int = 100


class SchedulerConfig(BaseModel):
    tick_seconds: float = 1.0
    jitter_seconds: int = 10
    backoff_base_seconds: int = 60
    backoff_max_seconds: int = 900
    suspend_after_failures: int = 5


class TelegramConfig(BaseModel):
    bot_token: str = ""
    api_id: int | None = None
    api_hash: str = ""
    reading_account: str = "default"
    session_path: str = "data/default.session"
    mtproto_requests_per_second: float = 1.0


class ProviderConfig(BaseModel):
    base_url: str = ""
    host: str = ""


class LLMConfig(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    control_model: str = "gpt-4o-mini"
    classifier_model: str = "gpt-4o-mini"
    control_timeout_seconds: int = 30
    classifier_timeout_seconds: int = 20
    max_retries: int = 2
    repair_retries: int = 1
    max_post_chars_for_llm: int = 1500
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class AppConfig(BaseModel):
    access: AccessConfig = Field(default_factory=AccessConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    secrets_master_key: str = ""
    db_path: str = "data/tgagent.db"
    log_level: str = "INFO"


def load_config(
    env_file: str | Path = ".env",
    settings_file: str | Path = "settings.toml",
    fallback_settings_file: str | Path = "settings.example.toml",
) -> AppConfig:
    """Load and merge configuration from .env and settings.toml."""
    # 1. Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    # 2. Load TOML settings
    settings_path = Path(settings_file)
    if not settings_path.exists():
        settings_path = Path(fallback_settings_file)

    toml_data: dict[str, Any] = {}
    if settings_path.exists():
        with open(settings_path, "rb") as f:
            toml_data = tomllib.load(f)

    # 3. Read env overrides
    bot_token = os.getenv("BOT_TOKEN", "")
    tg_api_id_raw = os.getenv("TG_API_ID") or os.getenv("TELEGRAM_API_ID")
    tg_api_id = int(tg_api_id_raw) if tg_api_id_raw and tg_api_id_raw.isdigit() else None
    tg_api_hash = os.getenv("TG_API_HASH") or os.getenv("TELEGRAM_API_HASH", "")
    secrets_master_key = os.getenv("SECRETS_MASTER_KEY", "")
    db_path = os.getenv("DB_PATH", toml_data.get("db_path", "data/tgagent.db"))
    log_level = os.getenv("LOG_LEVEL", toml_data.get("log_level", "INFO"))

    # 4. Construct typed sections
    access_cfg = AccessConfig(**toml_data.get("access", {}))
    limits_cfg = LimitsConfig(**toml_data.get("limits", {}))
    scheduler_cfg = SchedulerConfig(**toml_data.get("scheduler", {}))

    tg_toml = toml_data.get("telegram", {})
    # Auto-detect existing session file if present
    default_session_path = tg_toml.get("session_path", "data/default.session")
    if Path("session_file.session").exists() or Path("session_file").exists():
        default_session_path = "session_file"

    session_path = os.getenv("SESSION_PATH", default_session_path)

    telegram_cfg = TelegramConfig(
        bot_token=bot_token or tg_toml.get("bot_token", ""),
        api_id=tg_api_id if tg_api_id is not None else tg_toml.get("api_id"),
        api_hash=tg_api_hash or tg_toml.get("api_hash", ""),
        reading_account=tg_toml.get("reading_account", "default"),
        session_path=session_path,
        mtproto_requests_per_second=tg_toml.get("mtproto_requests_per_second", 1.0),
    )

    llm_toml = toml_data.get("llm", {})
    providers_raw = llm_toml.get("providers", {})
    providers = {k: ProviderConfig(**v) for k, v in providers_raw.items()}

    # Auto-detect provider if Groq key is present
    default_provider = "groq" if (os.getenv("GROQ_API_TOKEN") or os.getenv("GROQ_API_KEY")) else "openai"
    llm_provider = os.getenv("LLM_PROVIDER", llm_toml.get("provider", default_provider)).lower()

    # Read API key with provider-specific fallbacks
    llm_api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("GROQ_API_TOKEN")
        or os.getenv("GROQ_API_KEY")
        or os.getenv(f"{llm_provider.upper()}_API_KEY")
        or os.getenv(f"{llm_provider.upper()}_API_TOKEN")
        or llm_toml.get("api_key", "")
    ).strip()

    # Smart model defaults per provider
    default_control = "llama-3.3-70b-versatile" if llm_provider == "groq" else "gpt-4o-mini"
    default_classifier = "llama-3.1-8b-instant" if llm_provider == "groq" else "gpt-4o-mini"

    control_model = os.getenv("LLM_CONTROL_MODEL", llm_toml.get("control_model", default_control))
    classifier_model = os.getenv("LLM_CLASSIFIER_MODEL", llm_toml.get("classifier_model", default_classifier))

    llm_cfg = LLMConfig(
        provider=llm_provider,
        api_key=llm_api_key,
        control_model=control_model,
        classifier_model=classifier_model,
        control_timeout_seconds=llm_toml.get("control_timeout_seconds", 30),
        classifier_timeout_seconds=llm_toml.get("classifier_timeout_seconds", 20),
        max_retries=llm_toml.get("max_retries", 2),
        repair_retries=llm_toml.get("repair_retries", 1),
        max_post_chars_for_llm=llm_toml.get("max_post_chars_for_llm", 1500),
        providers=providers,
    )

    return AppConfig(
        access=access_cfg,
        limits=limits_cfg,
        scheduler=scheduler_cfg,
        telegram=telegram_cfg,
        llm=llm_cfg,
        secrets_master_key=secrets_master_key,
        db_path=db_path,
        log_level=log_level,
    )
