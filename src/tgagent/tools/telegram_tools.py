"""Telegram tools for interacting with channels, fetching posts, and real-time listening."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, tool
from langchain_core.language_models import BaseChatModel
from telethon import events
from tgagent.domain.models import DesiredState
from tgagent.domain.schemas import PostEvaluationResult
from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager, clean_identifier
from tgagent.telegram.notifier import TelegramNotifier

logger = logging.getLogger("tgagent.tools.telegram")


def make_telegram_tools(
    session_mgr: TelegramSessionManager,
    task_store: TaskStore | None = None,
    classifier_model: BaseChatModel | None = None,
    notifier: TelegramNotifier | None = None,
) -> list[BaseTool]:
    """Create Telegram interaction tools bound to the Telegram session manager."""

    seen_message_ids: set[int] = set()

    @tool
    async def resolve_telegram_entity(identifier: str) -> str:
        """Resolve a Telegram channel, group, or user by username, handle, or link.

        Args:
            identifier: Channel handle (e.g. '@tech_news'), link (e.g. 'https://t.me/tech_news'), or username.
        """
        try:
            if not session_mgr.is_connected:
                connected = await session_mgr.connect()
                if not connected:
                    return "Error: Telegram client is not connected or authorized. Run scripts/login_session.py."

            entity = await session_mgr.resolve_entity(identifier)
            ent_id = getattr(entity, "id", None)
            title = getattr(entity, "title", getattr(entity, "first_name", str(ent_id)))
            username = getattr(entity, "username", "") or ""

            return (
                f"Resolved entity successfully:\n"
                f"- Title: {title}\n"
                f"- ID: {ent_id}\n"
                f"- Username: @{username if username else 'N/A'}"
            )
        except Exception as exc:
            return f"Error resolving entity '{identifier}': {str(exc)}"

    @tool
    async def fetch_channel_posts(channel: str, limit: int = 10) -> str:
        """Fetch the most recent posts from a Telegram channel.

        Args:
            channel: Channel handle or link (e.g. '@tech_news').
            limit: Maximum number of recent posts to retrieve (1 to 50, default 10).
        """
        try:
            if not session_mgr.is_connected:
                connected = await session_mgr.connect()
                if not connected:
                    return "Error: Telegram client is not connected or authorized."

            entity = await session_mgr.resolve_entity(channel)
            client = session_mgr.client
            clamped_limit = max(1, min(limit, 50))
            messages = await client.get_messages(entity, limit=clamped_limit)

            if not messages:
                return f"No messages found in channel '{channel}'."

            output = [f"Retrieved {len(messages)} recent post(s) from {channel}:"]
            for m in messages:
                text_preview = (m.message or "").strip().replace("\n", " ")
                if len(text_preview) > 120:
                    text_preview = text_preview[:117] + "..."
                if not text_preview and m.media:
                    text_preview = "[Media attachment without caption]"
                date_str = m.date.strftime("%Y-%m-%d %H:%M:%S UTC") if m.date else "Unknown date"
                output.append(f"- ID {m.id} ({date_str}): {text_preview}")

            return "\n".join(output)
        except Exception as exc:
            return f"Error fetching posts from '{channel}': {str(exc)}"

    @tool
    async def get_unread_messages(channel: str) -> str:
        """Retrieve unread messages from a Telegram channel dialog.

        Args:
            channel: Channel handle or link (e.g. '@tech_news').
        """
        try:
            if not session_mgr.is_connected:
                connected = await session_mgr.connect()
                if not connected:
                    return "Error: Telegram client is not connected."

            entity = await session_mgr.resolve_entity(channel)
            client = session_mgr.client
            dialogs = await client.get_dialogs()
            ent_id = getattr(entity, "id", None)

            target_dialog = None
            for d in dialogs:
                if d.entity and d.entity.id == ent_id:
                    target_dialog = d
                    break

            unread_count = target_dialog.unread_count if target_dialog else 0
            if unread_count <= 0:
                return f"Channel '{channel}' has 0 unread messages."

            msgs = await client.get_messages(entity, limit=min(unread_count, 20))
            output = [f"Found {unread_count} unread message(s) in {channel} (showing first {len(msgs)}):"]
            for m in reversed(msgs):
                text_preview = (m.message or "").strip().replace("\n", " ")
                if len(text_preview) > 100:
                    text_preview = text_preview[:97] + "..."
                output.append(f"- ID {m.id}: {text_preview}")

            return "\n".join(output)
        except Exception as exc:
            return f"Error checking unread messages for '{channel}': {str(exc)}"

    @tool
    async def register_realtime_listener(task_id: str, channels: list[str]) -> str:
        """Register a real-time event listener for a monitoring task across specified channels.

        Args:
            task_id: The ID of the monitoring task (e.g. 'subagent_1').
            channels: List of channel handles to listen to.
        """
        try:
            if not session_mgr.is_connected:
                connected = await session_mgr.connect()
                if not connected:
                    return "Error: Telegram client is not connected."

            client = session_mgr.client
            resolved_entities = []
            for ch in channels:
                try:
                    ent = await session_mgr.resolve_entity(ch)
                    resolved_entities.append(ent)
                except Exception as e:
                    logger.warning("Could not resolve channel %s: %s", ch, e)

            if not resolved_entities:
                return f"Failed to register listener: None of the channels {channels} could be resolved."

            task = task_store.get(task_id) if task_store else None
            recipient_handle = task.config.recipient if task else "@me"
            criteria = task.config.criteria if task else ""

            recipient_entity = None
            try:
                recipient_entity = await session_mgr.resolve_entity(recipient_handle)
            except Exception as e:
                logger.warning("Recipient %s not resolved yet: %s", recipient_handle, e)

            active_notifier = notifier or TelegramNotifier(client)

            # Define event listener
            @client.on(events.NewMessage(chats=resolved_entities))
            async def on_new_msg(event: Any) -> None:
                try:
                    current_task = task_store.get(task_id) if task_store else None
                    if current_task and current_task.desired != DesiredState.ACTIVE:
                        return

                    msg = event.message
                    if not msg or msg.id in seen_message_ids:
                        return
                    seen_message_ids.add(msg.id)

                    text = (msg.message or "").strip()
                    if not text:
                        return

                    # Semantic evaluation if classifier_model provided
                    is_match = True
                    match_reason = "Real-time match"
                    confidence = 1.0

                    if classifier_model and criteria:
                        try:
                            structured_evaluator = classifier_model.with_structured_output(PostEvaluationResult)
                            prompt_msg = (
                                f"Monitoring Criteria:\n{criteria}\n\n"
                                f"Post Content:\n{text[:1500]}\n\n"
                                "Determine if this post matches the criteria."
                            )
                            res = await structured_evaluator.ainvoke([("user", prompt_msg)])
                            is_match = res.is_relevant
                            match_reason = res.reason
                            confidence = res.confidence
                        except Exception as eval_err:
                            logger.error("Error evaluating realtime post: %s", eval_err)
                            is_match = False

                    if is_match and confidence >= 0.5:
                        chat = await event.get_chat()
                        ch_title = getattr(chat, "title", str(chat.id))
                        ch_handle = getattr(chat, "username", "") or ""

                        rec = recipient_entity or recipient_handle
                        await active_notifier.send_alert(
                            recipient=rec,
                            channel_name=ch_title,
                            channel_handle=ch_handle,
                            message_id=msg.id,
                            post_text=text,
                            match_reason=match_reason,
                            agent_name=task_id,
                        )

                        if task_store:
                            preview = text.replace("\n", " ")[:60]
                            task_store.record_match(task_id, f"[{ch_title}] {preview}...")
                            logger.info("[%s] Realtime match alerted: %s", task_id, preview)

                except Exception as ex:
                    logger.error("[%s] Error in realtime listener handler: %s", task_id, ex)

            return f"Real-time listener registered for task '{task_id}' across {len(resolved_entities)} channel(s)."

        except Exception as exc:
            return f"Error registering real-time listener for {task_id}: {str(exc)}"

    return [
        resolve_telegram_entity,
        fetch_channel_posts,
        get_unread_messages,
        register_realtime_listener,
    ]
