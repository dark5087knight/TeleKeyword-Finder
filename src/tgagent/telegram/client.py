"""Telegram client manager using Telethon."""

from __future__ import annotations

import logging
import re
from typing import Any
from telethon import TelegramClient
from tgagent.config import AppConfig

logger = logging.getLogger("tgagent.telegram.client")


def clean_identifier(raw: str) -> str:
    """Clean channel/user string (e.g. https://t.me/ch -> ch, @ch -> ch, @t.me/ch -> ch)."""
    text = (raw or "").strip()
    while text.startswith("@"):
        text = text[1:].strip()
    if text.startswith("https://t.me/"):
        text = text[13:]
    elif text.startswith("http://t.me/"):
        text = text[12:]
    elif text.startswith("t.me/"):
        text = text[5:]
    while text.startswith("@"):
        text = text[1:].strip()
    text = text.split("?")[0].rstrip("/")
    return text


class TelegramSessionManager:
    """Manages the lifecycle of the shared Telethon client."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        session_file = config.telegram.session_path or "session_file"
        try:
            from pathlib import Path
            Path(session_file).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        api_id = config.telegram.api_id or 12345
        api_hash = config.telegram.api_hash or "dummy_hash"

        self.client = TelegramClient(session_file, api_id, api_hash)
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self) -> bool:
        """Connect to Telegram and verify authorization."""
        if self._is_connected:
            return True

        logger.info("Connecting Telethon client using session: %s", self.config.telegram.session_path)
        await self.client.connect()

        if not await self.client.is_user_authorized():
            logger.warning("Telethon client is not authorized. Please run scripts/login_session.py.")
            return False

        self._is_connected = True
        me = await self.client.get_me()
        logger.info("Telethon connected successfully as %s (@%s)", getattr(me, "first_name", ""), getattr(me, "username", ""))
        return True

    async def resolve_entity(self, identifier: str) -> Any:
        """Resolve a channel or username entity."""
        cleaned = clean_identifier(identifier)
        if cleaned.lower() in ("me", "self"):
            return await self.client.get_me()
        try:
            if cleaned.lstrip("-").isdigit():
                return await self.client.get_entity(int(cleaned))
        except Exception:
            pass
        return await self.client.get_entity(cleaned)

    async def disconnect(self) -> None:
        """Cleanly disconnect client."""
        if self._is_connected:
            await self.client.disconnect()
            self._is_connected = False
            logger.info("Telethon client disconnected.")
