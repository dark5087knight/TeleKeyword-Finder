"""Telegram alert delivery service for forwarding matched posts to recipients."""

from __future__ import annotations

import html
import logging
from typing import Any
from telethon import TelegramClient

logger = logging.getLogger("tgagent.telegram.notifier")


class TelegramNotifier:
    """Dispatches matched channel posts directly to Telegram recipients."""

    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def send_alert(
        self,
        recipient_entity: Any,
        post_message: Any,
        channel_name: str,
        channel_handle: str,
        matched_topics: list[str],
        agent_name: str = "",
    ) -> bool:
        """Format and send post alert to recipient, preserving media attachments."""
        msg_id = getattr(post_message, "id", 0)
        post_text = getattr(post_message, "text", "") or ""

        # Construct clickable link
        clean_handle = channel_handle.lstrip("@")
        post_link = f"https://t.me/{clean_handle}/{msg_id}" if clean_handle else None

        # Build notification header
        agent_line = f"Agent: {agent_name}\n" if agent_name else ""
        reason_label = "Match Reason" if matched_topics else "Topic"
        topics_str = ", ".join(matched_topics)
        link_line = f"\nLink: {post_link}" if post_link else ""
        header = (
            f"{agent_line}"
            f"Channel: {channel_name} (@{clean_handle})\n"
            f"{reason_label}: {topics_str}{link_line}\n"
            f"{'─' * 30}\n"
        )

        full_message = f"{header}{post_text}"
        if len(full_message) > 4000:
            full_message = full_message[:3950] + "\n...[truncated]"

        try:
            # Check for media (photo, document, etc.)
            media = getattr(post_message, "media", None)
            from telethon.tl.types import MessageMediaWebPage, MessageMediaEmpty
            has_real_media = media and not isinstance(media, (MessageMediaWebPage, MessageMediaEmpty))

            if has_real_media:
                await self.client.send_file(
                    recipient_entity,
                    file=media,
                    caption=full_message,
                )
            else:
                await self.client.send_message(
                    recipient_entity,
                    message=full_message,
                )

            logger.info("Successfully delivered alert for post #%d to recipient.", msg_id)
            return True

        except Exception as e:
            logger.error("Failed to send alert to recipient: %s", e)
            return False
