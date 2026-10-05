"""
Core module for Telegram Keyword Monitor & Alert Bot.
"""

from .config import AppConfig, load_app_config
from .matcher import KeywordMatcher
from .storage import SeenMessageStore
from .notifier import AlertNotifier
from .client import TelegramClientManager
from .shutdown import GracefulShutdown

__all__ = [
    "AppConfig",
    "load_app_config",
    "KeywordMatcher",
    "SeenMessageStore",
    "AlertNotifier",
    "TelegramClientManager",
    "GracefulShutdown",
]
