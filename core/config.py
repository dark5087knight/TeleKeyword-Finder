import os
import sys
import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = [
    Path("config.d/config.yaml"),
    Path("teljobs.d/config.yaml"),
    Path("config.yaml"),
]

EXAMPLE_CONFIG_PATH = Path("config.d/config.yaml.example")


def load_lines(file_path: str | Path, required: bool = True) -> List[str]:
    """
    Load non-empty, non-comment lines from a file.
    Supports utf-8 and utf-8-sig (Windows BOM).
    Filters out comments (# ...) and empty lines.
    """
    path = Path(file_path)
    if not path.exists():
        if required:
            logger.warning(f"File not found: {path}")
        return []

    lines: List[str] = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
    return lines


@dataclass
class AppConfig:
    api_id: int
    api_hash: str
    phone: str

    channels: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)

    channels_file: str = "config.d/channels.conf"
    keywords_file: str = "config.d/keywords.conf"
    exclude_keywords_file: str = "config.d/exclude_keywords.conf"
    send_to_users_file: str = "config.d/send_to_users.conf"
    session_file: str = "session_file"
    seen_db_file: str = "config.d/seen_messages.db"
    logs_dir: str = "logs"
    log_file: str = "telegram_bot.log"

    log_level: str = "DEBUG"
    console_log_level: str = "INFO"
    max_log_size: int = 5 * 1024 * 1024
    backup_count: int = 5

    forward_original: bool = False
    attach_media: bool = True
    auto_read: bool = True

    retry_wait_seconds: int = 15
    join_delay_seconds: int = 5

    keyboard_enabled: bool = True
    exit_key: str = "esc"

    raw_yaml: Dict[str, Any] = field(default_factory=dict)


def load_dotenv_if_present(dotenv_path: str | Path = ".env") -> None:
    """
    Loads environment variables from a .env file into os.environ.
    Uses python-dotenv if installed, otherwise uses a built-in fallback parser.
    """
    try:
        import dotenv
        dotenv.load_dotenv(dotenv_path)
        return
    except ImportError:
        pass

    path = Path(dotenv_path)
    if not path.is_file():
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        logger.debug(f"Could not read .env file at {path}: {e}")


def load_app_config(config_path: Optional[str | Path] = None) -> AppConfig:
    """
    Load configuration from YAML file and apply environment variable overrides.
    """
    load_dotenv_if_present()
    resolved_path: Optional[Path] = None

    if config_path:
        p = Path(config_path)
        if p.exists():
            resolved_path = p
    else:
        for p in DEFAULT_CONFIG_PATHS:
            if p.exists():
                resolved_path = p
                break

    data: Dict[str, Any] = {}
    if resolved_path:
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[ERROR] Failed to parse config at {resolved_path}: {e}")
            sys.exit(1)
    else:
        # Check if environment variables are set before failing
        if not (os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH") and os.getenv("TELEGRAM_PHONE")):
            print("\n" + "=" * 70)
            print("[ERROR] Configuration file 'config.d/config.yaml' not found!")
            print("=" * 70)
            if EXAMPLE_CONFIG_PATH.exists():
                print(f"A template is available at: {EXAMPLE_CONFIG_PATH}")
                print(f"Run: copy {EXAMPLE_CONFIG_PATH} config.d\\config.yaml")
                print("Then open config.d/config.yaml and insert your Telegram API credentials.")
            else:
                print("Please create 'config.d/config.yaml' with your Telegram credentials.")
            print("=" * 70 + "\n")
            sys.exit(1)

    tg_sec = data.get("telegram", {})
    paths_sec = data.get("paths", {})
    bot_sec = data.get("bot", {})
    log_sec = data.get("logging", {})
    retry_sec = data.get("retry", {})
    kb_sec = data.get("keyboard", {})

    # Credentials with env var overrides
    env_api_id = os.getenv("TELEGRAM_API_ID")
    raw_api_id = env_api_id if env_api_id else tg_sec.get("api_id")
    try:
        api_id = int(raw_api_id) if raw_api_id not in (None, "", "#") else 0
    except (ValueError, TypeError):
        api_id = 0

    api_hash = os.getenv("TELEGRAM_API_HASH") or tg_sec.get("api_hash", "")
    phone = os.getenv("TELEGRAM_PHONE") or tg_sec.get("phone", "")

    if not api_id or not api_hash or api_hash == "#" or not phone or phone == "#":
        print("\n" + "=" * 70)
        print("[ERROR] Telegram API credentials (api_id, api_hash, phone) are missing or invalid!")
        print("Please configure them in 'config.d/config.yaml' or set environment variables:")
        print("  - TELEGRAM_API_ID")
        print("  - TELEGRAM_API_HASH")
        print("  - TELEGRAM_PHONE")
        print("=" * 70 + "\n")
        sys.exit(1)

    # Resolve paths
    channels_file = paths_sec.get("channels_file", "config.d/channels.conf")
    keywords_file = paths_sec.get("keywords_file", "config.d/keywords.conf")
    exclude_keywords_file = paths_sec.get("exclude_keywords_file", "config.d/exclude_keywords.conf")
    send_to_users_file = bot_sec.get("send_to_users_file", paths_sec.get("send_to_users_file", "config.d/send_to_users.conf"))
    session_file = paths_sec.get("session_file", "session_file")
    seen_db_file = paths_sec.get("seen_db_file", "config.d/seen_messages.db")
    logs_dir = paths_sec.get("logs_dir", "logs")
    log_file = paths_sec.get("log_file", "telegram_bot.log")

    # Load list files (stripping comments and empty lines)
    channels = load_lines(channels_file, required=True)
    keywords = load_lines(keywords_file, required=True)
    exclude_keywords = load_lines(exclude_keywords_file, required=False)
    recipients = load_lines(send_to_users_file, required=True)

    config = AppConfig(
        api_id=api_id,
        api_hash=str(api_hash).strip(),
        phone=str(phone).strip(),
        channels=channels,
        keywords=keywords,
        exclude_keywords=exclude_keywords,
        recipients=recipients,
        channels_file=channels_file,
        keywords_file=keywords_file,
        exclude_keywords_file=exclude_keywords_file,
        send_to_users_file=send_to_users_file,
        session_file=session_file,
        seen_db_file=seen_db_file,
        logs_dir=logs_dir,
        log_file=log_file,
        log_level=log_sec.get("level", "DEBUG"),
        console_log_level=log_sec.get("console_level", "INFO"),
        max_log_size=log_sec.get("max_log_size", 5 * 1024 * 1024),
        backup_count=log_sec.get("backup_count", 5),
        forward_original=bot_sec.get("forward_original", False),
        attach_media=bot_sec.get("attach_media", True),
        auto_read=bot_sec.get("auto_read", True),
        retry_wait_seconds=retry_sec.get("retry_wait_seconds", 15),
        join_delay_seconds=retry_sec.get("join_delay_seconds", 5),
        keyboard_enabled=kb_sec.get("enabled", True),
        exit_key=kb_sec.get("exit_key", "esc"),
        raw_yaml=data,
    )

    setup_logging(config)
    return config


def setup_logging(config: AppConfig) -> None:
    """Setup root/app logger with rotating file handler and console handler."""
    os.makedirs(config.logs_dir, exist_ok=True)

    root_logger = logging.getLogger()
    # Avoid duplicate handlers if called multiple times
    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.setLevel(getattr(logging, config.log_level.upper(), logging.DEBUG))

    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %I:%M:%S %p",
    )
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")

    # File Handler
    log_path = os.path.join(config.logs_dir, config.log_file)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.max_log_size,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, config.log_level.upper(), logging.DEBUG))
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, config.console_log_level.upper(), logging.INFO))
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
