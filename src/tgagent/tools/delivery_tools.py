"""Delivery tools for formatting and dispatching alerts to Telegram recipients."""

from __future__ import annotations

import logging
from typing import Any
from langchain_core.tools import BaseTool, tool
from tgagent.telegram.client import TelegramSessionManager, clean_identifier
from tgagent.telegram.notifier import TelegramNotifier

logger = logging.getLogger("tgagent.tools.delivery")


def make_delivery_tools(
    session_mgr: TelegramSessionManager,
    notifier: TelegramNotifier | None = None,
) -> list[BaseTool]:
    """Create alert delivery tools bound to the Telegram session manager."""

    @tool
    async def format_post_notification(
        channel_name: str,
        channel_handle: str,
        message_id: int,
        post_text: str,
        match_reason: str,
        agent_name: str = "",
    ) -> str:
        """Format a channel post into a clean alert notification string without sending it.

        Args:
            channel_name: Display title of the channel.
            channel_handle: Channel handle or username (e.g. '@tech_news').
            message_id: Telegram message ID.
            post_text: Text content of the post.
            match_reason: Explanation of why the post matched criteria.
            agent_name: Optional name or ID of the detecting sub-agent.
        """
        clean_handle = clean_identifier(channel_handle)
        post_link = f"https://t.me/{clean_handle}/{message_id}" if clean_handle else ""

        agent_line = f"Agent: {agent_name}\n" if agent_name else ""
        link_line = f"\nLink: {post_link}" if post_link else ""

        header = (
            f"{agent_line}"
            f"Channel: {channel_name} (@{clean_handle})\n"
            f"Match Reason: {match_reason}{link_line}\n"
            f"{'─' * 30}\n"
        )

        full_message = f"{header}{post_text.strip()}"
        if len(full_message) > 4000:
            full_message = full_message[:3950] + "\n...[truncated]"

        return full_message

    @tool
    async def send_alert_to_recipient(
        recipient: str,
        channel_name: str,
        channel_handle: str,
        message_id: int,
        post_text: str,
        match_reason: str,
        agent_name: str = "",
    ) -> str:
        """Send a matched post notification directly to a Telegram recipient.

        Args:
            recipient: Telegram username or handle to receive the alert (e.g. '@myuser').
            channel_name: Display title of the source channel.
            channel_handle: Handle of the channel (e.g. '@tech_news').
            message_id: Message ID of the post.
            post_text: Content of the post.
            match_reason: Explanation of why the post matched criteria.
            agent_name: Optional name or ID of the monitoring sub-agent.
        """
        try:
            if not session_mgr.is_connected:
                connected = await session_mgr.connect()
                if not connected:
                    return "Error: Telegram client is not connected or authorized."

            recipient_entity = await session_mgr.resolve_entity(recipient)

            formatted = await format_post_notification.ainvoke({
                "channel_name": channel_name,
                "channel_handle": channel_handle,
                "message_id": message_id,
                "post_text": post_text,
                "match_reason": match_reason,
                "agent_name": agent_name,
            })

            client = session_mgr.client
            await client.send_message(recipient_entity, message=formatted)

            return (
                f"Alert for post #{message_id} from {channel_name} successfully delivered to {recipient}."
            )
        except Exception as exc:
            logger.error("Failed to deliver alert to %s: %s", recipient, exc)
            return f"Error delivering alert to {recipient}: {str(exc)}"

    return [
        format_post_notification,
        send_alert_to_recipient,
    ]
