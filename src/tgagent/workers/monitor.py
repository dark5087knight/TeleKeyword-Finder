"""Sub-Agent worker that actively monitors Telegram channels and evaluates posts semantically."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Set
from telethon import events, TelegramClient
from tgagent.domain.models import DesiredState, Task
from tgagent.llm.service import LLMService
from tgagent.telegram.client import TelegramSessionManager, clean_identifier
from tgagent.telegram.notifier import TelegramNotifier
from tgagent.workers.matcher import TopicMatcher

logger = logging.getLogger("tgagent.workers.monitor")


class SubAgentWorker:
    """Active worker representing a running Sub-Agent."""

    def __init__(
        self,
        task: Task,
        session_mgr: TelegramSessionManager,
        llm_service: LLMService | None = None,
        on_match_callback: Any = None,
    ) -> None:
        self.task = task
        self.session_mgr = session_mgr
        self.llm_service = llm_service
        self.notifier = TelegramNotifier(session_mgr.client)
        self.matcher = TopicMatcher(task.config.topics or task.config.keywords)
        self.on_match_callback = on_match_callback

        self.seen_message_ids: Set[int] = set()
        self.matched_posts_count = 0
        self.matched_posts_summary: list[str] = []
        self._event_handler: Any = None
        self._is_running = False

    async def start(self) -> None:
        """Resolve entities, scan recent messages, and attach real-time event listener."""
        client = self.session_mgr.client
        if not self.session_mgr.is_connected:
            await self.session_mgr.connect()

        resolved_channels = []
        for ch_ref in self.task.config.channels:
            try:
                ch_entity = await self.session_mgr.resolve_entity(ch_ref.handle)
                resolved_channels.append(ch_entity)
                logger.info("[%s] Resolved channel: %s", self.task.id, ch_ref.handle)
            except Exception as e:
                logger.error("[%s] Could not resolve channel %s: %s", self.task.id, ch_ref.handle, e)

        if not resolved_channels:
            logger.error("[%s] No channels could be resolved. Worker cannot start.", self.task.id)
            return

        # Resolve recipient
        try:
            recipient_entity = await self.session_mgr.resolve_entity(self.task.config.recipient)
            logger.info("[%s] Resolved recipient: %s", self.task.id, self.task.config.recipient)
        except Exception as e:
            logger.error("[%s] Could not resolve recipient %s: %s", self.task.id, self.task.config.recipient, e)
            return

        self._is_running = True

        # 1. Unread Catch-up check: ONLY scan unread messages, never already-read historical posts
        dialog_map: dict[int, Any] = {}
        try:
            dialogs = await client.get_dialogs()
            for d in dialogs:
                if d.entity:
                    dialog_map[d.entity.id] = d
        except Exception as e:
            logger.warning("[%s] Could not retrieve dialogs list: %s", self.task.id, e)

        for ch_entity in resolved_channels:
            ch_id = getattr(ch_entity, "id", None)
            ch_title = getattr(ch_entity, "title", str(ch_entity.id))
            ch_handle = getattr(ch_entity, "username", clean_identifier(str(ch_entity.id))) or ""

            dialog = dialog_map.get(ch_id) if ch_id else None
            unread_count = dialog.unread_count if dialog else 0

            if unread_count > 0:
                logger.info("[%s] Processing %d unread message(s) in %s...", self.task.id, unread_count, ch_title)
                try:
                    unread_msgs = await client.get_messages(ch_entity, limit=unread_count)
                    for msg in reversed(unread_msgs):
                        if msg.id in self.seen_message_ids:
                            continue
                        self.seen_message_ids.add(msg.id)
                        await self._evaluate_and_process(msg, ch_title, ch_handle, recipient_entity)

                    # Mark read so they are not re-processed on subsequent runs
                    try:
                        await client.send_read_acknowledge(ch_entity)
                    except Exception:
                        pass
                except Exception as e:
                    logger.error("[%s] Error processing unread messages in %s: %s", self.task.id, ch_title, e)
            else:
                logger.info("[%s] All messages in %s are already read. Listening for new incoming messages only.", self.task.id, ch_title)
                # Seed latest message ID so all past read messages are ignored
                try:
                    latest = await client.get_messages(ch_entity, limit=1)
                    if latest:
                        self.seen_message_ids.add(latest[0].id)
                except Exception:
                    pass

        # 2. Register real-time event listener
        @client.on(events.NewMessage(chats=resolved_channels))
        async def on_new_channel_message(event: Any) -> None:
            if not self._is_running or self.task.desired != DesiredState.ACTIVE:
                return

            msg = event.message
            if msg.id in self.seen_message_ids:
                return
            self.seen_message_ids.add(msg.id)

            chat = await event.get_chat()
            ch_title = getattr(chat, "title", str(chat.id))
            ch_handle = getattr(chat, "username", "") or ""

            await self._evaluate_and_process(msg, ch_title, ch_handle, recipient_entity)

        self._event_handler = on_new_channel_message
        logger.info("[%s] Actively listening for new messages across %d channel(s).", self.task.id, len(resolved_channels))

    async def _evaluate_and_process(
        self,
        msg: Any,
        ch_title: str,
        ch_handle: str,
        recipient_entity: Any,
    ) -> None:
        """Evaluate post text against user criteria using LLM semantic matching."""
        text = msg.text or ""
        if not text.strip():
            return

        criteria = self.task.config.criteria or ", ".join(self.task.config.topics)
        is_match = False
        match_reason = ""

        # Semantic evaluation via LLM
        if self.llm_service:
            is_match, match_reason = await self.llm_service.evaluate_post_relevance(criteria, text)

        # Fallback to topic / keyword matcher if LLM was unavailable or not configured
        if not is_match and not self.llm_service:
            kw_matches = self.matcher.matches(text)
            if kw_matches:
                is_match = True
                match_reason = f"Keywords: {', '.join(kw_matches[:3])}"

        if is_match:
            await self._handle_match(recipient_entity, msg, ch_title, ch_handle, match_reason)

    async def _handle_match(
        self,
        recipient_entity: Any,
        msg: Any,
        ch_title: str,
        ch_handle: str,
        reason: str,
    ) -> None:
        """Process a matching post and deliver to recipient."""
        self.matched_posts_count += 1
        excerpt = (msg.text[:70] if msg.text else "<Media Post>").replace("\n", " ")
        self.matched_posts_summary.append(f"Post #{msg.id} in {ch_title}: {excerpt} ({reason})")

        agent_display_name = f"{self.task.id} ({self.task.config.name})"
        delivered = await self.notifier.send_alert(
            recipient_entity=recipient_entity,
            post_message=msg,
            channel_name=ch_title,
            channel_handle=ch_handle,
            matched_topics=[reason],
            agent_name=agent_display_name,
        )

        msg_notify = (
            f"\n\n[Sub-Agent Notification: Match found in @{ch_handle}! "
            f"Reason: {reason}\n"
            f"Forwarded Post #{msg.id} to {self.task.config.recipient}]"
        )
        print(msg_notify)

        if self.on_match_callback:
            self.on_match_callback(self.task.id, msg.id, ch_handle, self.task.config.recipient)

    async def stop(self) -> None:
        """Unregister event listener and stop worker."""
        self._is_running = False
        if self._event_handler:
            self.session_mgr.client.remove_event_handler(self._event_handler)
            self._event_handler = None
            logger.info("[%s] Worker stopped and event listener removed.", self.task.id)
