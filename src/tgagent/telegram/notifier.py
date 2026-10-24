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
        recipient_entity: Any = None,
        post_message: Any = None,
        channel_name: str = "",
        channel_handle: str = "",
        matched_topics: list[str] | None = None,
        agent_name: str = "",
        recipient: Any = None,
        message_id: int = 0,
        post_text: str = "",
        match_reason: str = "",
    ) -> bool:
        """Format and send post alert to recipient, preserving media attachments."""
        target_recipient = recipient_entity if recipient_entity is not None else recipient
        if target_recipient is None:
            logger.error("No recipient provided to send_alert.")
            return False

        if isinstance(target_recipient, str):
            clean_rec = target_recipient.strip()
            if clean_rec.lower() in ("me", "@me", "self", "@self"):
                target_recipient = "me"
            elif clean_rec.startswith("@"):
                target_recipient = clean_rec[1:]
            else:
                target_recipient = clean_rec

        # Extract message ID and text
        if post_message is not None:
            msg_id = getattr(post_message, "id", message_id)
            text_content = getattr(post_message, "text", post_text) or getattr(post_message, "message", post_text) or ""
            media = getattr(post_message, "media", None)
        else:
            msg_id = message_id
            text_content = post_text
            media = None

        # Extract reason/topics
        reasons = list(matched_topics) if matched_topics else []
        if match_reason and match_reason not in reasons:
            reasons.append(match_reason)
        if not reasons:
            reasons = ["Relevant to criteria"]

        # Construct clickable link
        clean_handle = channel_handle.lstrip("@")
        post_link = f"https://t.me/{clean_handle}/{msg_id}" if clean_handle and msg_id else None

        # Build notification header
        agent_line = f"Agent: {agent_name}\n" if agent_name else ""
        reason_label = "Match Reason" if len(reasons) == 1 else "Topics"
        topics_str = ", ".join(reasons)
        link_line = f"\nLink: {post_link}" if post_link else ""
        header = (
            f"{agent_line}"
            f"Channel: {channel_name} (@{clean_handle})\n"
            f"{reason_label}: {topics_str}{link_line}\n"
            f"{'─' * 30}\n"
        )

        full_message = f"{header}{text_content.strip()}"
        if len(full_message) > 4000:
            full_message = full_message[:3950] + "\n...[truncated]"

        try:
            from telethon.tl.types import MessageMediaEmpty, MessageMediaWebPage
            has_real_media = media and not isinstance(media, (MessageMediaWebPage, MessageMediaEmpty))

            if has_real_media:
                await self.client.send_file(
                    target_recipient,
                    file=media,
                    caption=full_message,
                )
            else:
                await self.client.send_message(
                    target_recipient,
                    message=full_message,
                )

            logger.info("Successfully delivered alert for post #%d to recipient.", msg_id)
            return True

        except Exception as e:
            logger.error("Failed to send alert to recipient: %s", e)
            return False
