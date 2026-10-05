import re
import asyncio
import logging
from typing import List, Dict, Tuple, Any, Optional, Awaitable, cast
from telethon import TelegramClient, errors
from telethon.tl.types import Channel, Chat

from .config import AppConfig

logger = logging.getLogger(__name__)


def clean_channel_identifier(raw: str) -> str:
    """
    Cleans up channel string from channels.conf:
    - https://t.me/channel_name -> channel_name
    - t.me/channel_name -> channel_name
    - @channel_name -> channel_name
    """
    cleaned = raw.strip()
    if cleaned.startswith("https://t.me/"):
        cleaned = cleaned.replace("https://t.me/", "")
    elif cleaned.startswith("http://t.me/"):
        cleaned = cleaned.replace("http://t.me/", "")
    elif cleaned.startswith("t.me/"):
        cleaned = cleaned.replace("t.me/", "")

    # Strip trailing slashes or queries
    cleaned = cleaned.split("?")[0].rstrip("/")
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    return cleaned


class TelegramClientManager:
    """Manages TelegramClient connection, reconnection, and channel entity resolution."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = TelegramClient(
            self.config.session_file,
            self.config.api_id,
            self.config.api_hash,
        )

    async def connect_with_retry(self, shutdown_event: Optional[asyncio.Event] = None) -> bool:
        """Connects to Telegram with automatic retry on failure."""
        retry_count = 0
        while shutdown_event is None or not shutdown_event.is_set():
            try:
                retry_count += 1
                logger.debug("Connecting to Telegram...")
                # Telethon's start() returns a coroutine when an event loop is running,
                # but its static type signature is annotated as TelegramClient instead of Awaitable.
                await cast(Awaitable[Any], self.client.start(self.config.phone))
                if retry_count > 1:
                    logger.info(f"Reconnected successfully after {retry_count - 1} retry attempts.")
                else:
                    logger.info("Connected to Telegram successfully.")
                return True

            except errors.FloodWaitError as fwe:
                logger.error(f"Telegram FloodWait encountered: Must wait {fwe.seconds} seconds.")
                wait_time = fwe.seconds + 2
                if shutdown_event:
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=wait_time)
                        return False
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(wait_time)

            except OSError as net_err:
                logger.warning(
                    f"Network error (attempt #{retry_count}): {net_err}. "
                    f"Retrying in {self.config.retry_wait_seconds}s..."
                )
                if shutdown_event:
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=self.config.retry_wait_seconds)
                        return False
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(self.config.retry_wait_seconds)

            except Exception as e:
                logger.error(
                    f"Connection failed (attempt #{retry_count}): {e}. "
                    f"Retrying in {self.config.retry_wait_seconds}s..."
                )
                if shutdown_event:
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=self.config.retry_wait_seconds)
                        return False
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(self.config.retry_wait_seconds)

        return False

    async def resolve_channels(self) -> Tuple[List[Any], Dict[str, Any], Dict[int, Any]]:
        """
        Resolves channel identifiers into Telethon entities.
        Returns:
            - list of valid entities (for events.NewMessage chats filter)
            - dict of clean_identifier -> entity
            - dict of channel_id -> entity
        """
        resolved_entities: List[Any] = []
        by_name: Dict[str, Any] = {}
        by_id: Dict[int, Any] = {}

        for raw in self.config.channels:
            clean = clean_channel_identifier(raw)
            if not clean:
                continue

            target: Any = clean
            # If numeric string like -1001234567890, convert to int
            if re.match(r"^-?\d+$", clean):
                target = int(clean)

            try:
                entity = await self.client.get_entity(target)
                if isinstance(entity, (Channel, Chat)):
                    resolved_entities.append(entity)
                    by_name[clean.lower()] = entity
                    by_id[entity.id] = entity
                    if getattr(entity, "username", None):
                        by_name[entity.username.lower()] = entity
                    logger.debug(f"Resolved channel: '{raw}' -> '{entity.title}' (ID: {entity.id})")
                else:
                    logger.warning(f"Target '{raw}' is not a channel/group. Skipped.")
            except Exception as e:
                logger.warning(f"Could not resolve channel '{raw}': {e}")

        logger.info(f"Successfully resolved {len(resolved_entities)} of {len(self.config.channels)} channels.")
        return resolved_entities, by_name, by_id
