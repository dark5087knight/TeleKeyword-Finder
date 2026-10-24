"""Real-time Telegram monitoring engine managing background Telethon listeners."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Set
from telethon import events
from langchain_core.language_models import BaseChatModel

from tgagent.domain.models import DesiredState, Task
from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager, clean_identifier
from tgagent.telegram.notifier import TelegramNotifier

logger = logging.getLogger("tgagent.telegram.monitor")


class RealtimeMonitorEngine:
    """Manages active Telethon event listeners and real-time post evaluation."""

    def __init__(
        self,
        session_mgr: TelegramSessionManager,
        classifier_model: BaseChatModel | None = None,
        notifier: TelegramNotifier | None = None,
        task_store: TaskStore | None = None,
    ) -> None:
        self.session_mgr = session_mgr
        self.classifier_model = classifier_model
        self.notifier = notifier or TelegramNotifier(session_mgr.client)
        self.task_store = task_store
        self._handlers: dict[str, Any] = {}
        self._seen_ids: dict[str, Set[int]] = {}
        self._poll_tasks: dict[str, asyncio.Task[Any]] = {}

    async def evaluate_post(self, criteria: str, text: str) -> tuple[bool, str]:
        """Semantically evaluate post text against criteria with LLM and keyword fallbacks."""
        clean_text = (text or "").strip()
        if not clean_text:
            return False, "Empty post content"

        # 1. Semantic evaluation via classifier model
        if self.classifier_model and criteria.strip():
            try:
                prompt = (
                    "You are an expert content verification system. Your job is to strictly evaluate whether a Telegram post genuinely matches the user's monitoring intent.\n\n"
                    f"USER MONITORING INTENT / CRITERIA:\n{criteria}\n\n"
                    f"POST CONTENT TO EVALUATE:\n{clean_text[:1500]}\n\n"
                    "CRITICAL EVALUATION RULES:\n"
                    "1. SUBSTANCE OVER KEYWORDS:\n"
                    "   - The post must ACTUALLY BE an instance of what the user is seeking, NOT just mention a keyword.\n"
                    "   - For example:\n"
                    "     * If user wants 'jokes' or 'funny content': The post must contain an actual joke (with setup/punchline, comedic dialogue, riddle, or humorous story). Merely saying the word 'joke' or typing laughter ('hahaha', 'lol', 'ههههه') is NOT a joke -> MATCH: NO.\n"
                    "     * If user wants 'jobs in Baghdad': The post must be an actual job vacancy/offer located in or for Baghdad. A post merely mentioning 'Baghdad' or discussing news in Baghdad without an actual job opening -> MATCH: NO.\n"
                    "2. CHATTER & REACTIONS ARE NOT MATCHES:\n"
                    "   - One-word posts (e.g. 'joke', 'job', 'hiring', 'funny'), short reactions, laughter ('hahaha', 'ههههه'), emojis, or greetings are NEVER matches -> MATCH: NO.\n"
                    "3. CONJUNCTIVE CONSTRAINTS:\n"
                    "   - All conditions in the user criteria must be satisfied together.\n"
                    "4. STRICT FILTERING:\n"
                    "   - When in doubt, reject. Only declare a match if the post genuinely delivers the requested content.\n\n"
                    "Reply strictly in this format:\n"
                    "MATCH: YES or NO\n"
                    "REASON: concise explanation"
                )
                res = await self.classifier_model.ainvoke([("user", prompt)])
                content = str(res.content)
                is_match = "MATCH: YES" in content.upper() or "MATCH:YES" in content.upper()

                reason = "Relevant to user criteria" if is_match else "Does not match criteria substance"
                m_reason = re.search(r"REASON:\s*(.+)", content, re.IGNORECASE)
                if m_reason:
                    reason = m_reason.group(1).strip()

                # Return LLM verdict directly. Never fall back to keywords when LLM successfully evaluated.
                return is_match, reason
            except Exception as e:
                logger.warning("Classifier LLM call failed, falling back to emergency heuristics: %s", e)

        # 2. Emergency fallback heuristics (only if LLM call failed or unavailable)
        # Never match one-word chatter, laughter, or empty reactions
        words_in_post = clean_text.split()
        if len(words_in_post) <= 2:
            return False, "Post is too short or is a single-word label/reaction"

        laughter_patterns = [r"^([hha]{3,}|[لهه]{3,}|lol|rofl|lmao)$"]
        if any(re.match(p, clean_text, re.IGNORECASE) for p in laughter_patterns):
            return False, "Reaction/laughter only"

        criteria_words = [w.strip().lower() for w in re.split(r"[\s,;،]+", criteria) if len(w.strip()) >= 3]
        post_lower = clean_text.lower()
        matched_words = [w for w in criteria_words if w in post_lower]
        if matched_words:
            return True, f"Emergency heuristic matched: {', '.join(matched_words)}"

        return False, "No match"

    async def start_task_monitor(self, task: Task) -> bool:
        """Resolve channel/recipient entities, process unread posts, and attach live listener."""
        try:
            if not self.session_mgr.is_connected:
                connected = await self.session_mgr.connect()
                if not connected:
                    logger.warning("[%s] Telegram client is not connected or authorized.", task.id)
                    return False

            client = self.session_mgr.client

            # 1. Resolve channels
            resolved_channels = []
            for ch_ref in task.config.channels:
                try:
                    ch_ent = await self.session_mgr.resolve_entity(ch_ref.handle)
                    resolved_channels.append(ch_ent)
                    logger.info("[%s] Resolved channel: %s", task.id, ch_ref.handle)
                except Exception as e:
                    logger.error("[%s] Could not resolve channel %s: %s", task.id, ch_ref.handle, e)

            if not resolved_channels:
                logger.error("[%s] No channels could be resolved. Listener not attached.", task.id)
                return False

            # 2. Resolve recipient
            recipient_handle = task.config.recipient
            recipient_entity = None
            try:
                recipient_entity = await self.session_mgr.resolve_entity(recipient_handle)
                logger.info("[%s] Resolved recipient: %s", task.id, recipient_handle)
            except Exception as e:
                logger.warning("[%s] Recipient entity not resolved directly, using handle %s: %s", task.id, recipient_handle, e)

            if task.id not in self._seen_ids:
                self._seen_ids[task.id] = set()
            seen_ids = self._seen_ids[task.id]

            # 3. Startup check: By default, ONLY scan unread (not seen) messages.
            # Do NOT scan old already-seen messages unless explicitly requested.
            dialog_map: dict[int, Any] = {}
            try:
                dialogs = await client.get_dialogs()
                for d in dialogs:
                    if getattr(d, "entity", None):
                        eid = getattr(d.entity, "id", None)
                        if eid is not None:
                            dialog_map[eid] = d
                    did = getattr(d, "id", None)
                    if did is not None:
                        dialog_map[did] = d
            except Exception as ex:
                logger.warning("[%s] Could not retrieve dialogs list: %s", task.id, ex)

            scan_history = any(
                k in task.config.criteria.lower()
                for k in ["scan history", "old messages", "past posts", "all messages", "history", "رسائل قديمة", "ارشيف", "سابق"]
            )

            for ch_ent in resolved_channels:
                ch_id = getattr(ch_ent, "id", None)
                ch_title = getattr(ch_ent, "title", str(ch_ent.id))
                ch_handle = getattr(ch_ent, "username", clean_identifier(str(ch_ent.id))) or ""

                dialog = None
                if ch_id:
                    dialog = dialog_map.get(ch_id) or dialog_map.get(-ch_id)
                unread_count = dialog.unread_count if dialog else 0

                try:
                    if scan_history:
                        # User explicitly asked to scan past messages
                        logger.info("[%s] Explicit history scan requested. Checking past posts in %s...", task.id, ch_title)
                        msgs = await client.get_messages(ch_ent, limit=30)
                        for m in reversed(msgs):
                            if m.id in seen_ids:
                                continue
                            seen_ids.add(m.id)
                            text = (getattr(m, "message", "") or getattr(m, "text", "") or "").strip()
                            if not text:
                                continue
                            is_match, reason = await self.evaluate_post(task.config.criteria, text)
                            if is_match:
                                await self._dispatch_alert(
                                    task=task,
                                    msg=m,
                                    text=text,
                                    ch_title=ch_title,
                                    ch_handle=ch_handle,
                                    recipient_entity=recipient_entity or recipient_handle,
                                    reason=reason,
                                )

                    elif unread_count > 0:
                        # Only scan unread (not seen) messages
                        logger.info("[%s] Catching up %d unread (not seen) message(s) in %s...", task.id, unread_count, ch_title)
                        msgs = await client.get_messages(ch_ent, limit=min(unread_count, 30))
                        for m in reversed(msgs):
                            if m.id in seen_ids:
                                continue
                            seen_ids.add(m.id)
                            text = (getattr(m, "message", "") or getattr(m, "text", "") or "").strip()
                            if not text:
                                continue
                            is_match, reason = await self.evaluate_post(task.config.criteria, text)
                            if is_match:
                                await self._dispatch_alert(
                                    task=task,
                                    msg=m,
                                    text=text,
                                    ch_title=ch_title,
                                    ch_handle=ch_handle,
                                    recipient_entity=recipient_entity or recipient_handle,
                                    reason=reason,
                                )
                        # Acknowledge read so they are not re-processed on subsequent runs
                        try:
                            await client.send_read_acknowledge(ch_ent)
                        except Exception:
                            pass

                    else:
                        # By default, all messages in channel are already seen.
                        # Seed latest message ID so all past seen messages are ignored.
                        logger.info("[%s] All messages in %s are already seen. Listening for new incoming messages only.", task.id, ch_title)
                        try:
                            latest = await client.get_messages(ch_ent, limit=1)
                            if latest:
                                seen_ids.add(latest[0].id)
                        except Exception:
                            pass

                except Exception as err:
                    logger.error("[%s] Error checking messages in %s: %s", task.id, ch_title, err)

            # 4. Attach real-time NewMessage listener
            @client.on(events.NewMessage(chats=resolved_channels))
            async def on_new_channel_message(event: Any) -> None:
                try:
                    current_task = self.task_store.get(task.id) if self.task_store else task
                    if current_task and current_task.desired != DesiredState.ACTIVE:
                        return

                    msg = event.message
                    if not msg or msg.id in seen_ids:
                        return
                    seen_ids.add(msg.id)

                    text = (getattr(msg, "message", "") or getattr(msg, "text", "") or "").strip()
                    if not text:
                        return

                    criteria = current_task.config.criteria if current_task else task.config.criteria
                    is_match, reason = await self.evaluate_post(criteria, text)

                    if is_match:
                        chat = getattr(event, "chat", None) or await event.get_chat()
                        ch_title = getattr(chat, "title", str(chat.id))
                        ch_handle = getattr(chat, "username", "") or ""
                        target_rec = recipient_entity or recipient_handle

                        await self._dispatch_alert(
                            task=current_task or task,
                            msg=msg,
                            text=text,
                            ch_title=ch_title,
                            ch_handle=ch_handle,
                            recipient_entity=target_rec,
                            reason=reason,
                        )

                except Exception as ex:
                    logger.error("[%s] Error in real-time message handler: %s", task.id, ex)

            # 5. Start periodic background recheck loop using task.config.interval_seconds
            async def periodic_recheck_loop() -> None:
                interval = max(int(getattr(task.config, "interval_seconds", 1) or 1), 1)
                logger.info("[%s] Periodic safety-net recheck active every %ds.", task.id, interval)
                while True:
                    try:
                        await asyncio.sleep(interval)
                        current_task = self.task_store.get(task.id) if self.task_store else task
                        if not current_task or current_task.desired != DesiredState.ACTIVE:
                            continue

                        # Check each resolved channel for any new posts that weren't caught by push events
                        for ch_ent in resolved_channels:
                            ch_title = getattr(ch_ent, "title", str(ch_ent.id))
                            ch_handle = getattr(ch_ent, "username", clean_identifier(str(ch_ent.id))) or ""

                            try:
                                recent = await client.get_messages(ch_ent, limit=5)
                                for m in reversed(recent):
                                    if m.id in seen_ids:
                                        continue
                                    seen_ids.add(m.id)
                                    text = (getattr(m, "message", "") or getattr(m, "text", "") or "").strip()
                                    if not text:
                                        continue

                                    criteria = current_task.config.criteria
                                    is_match, reason = await self.evaluate_post(criteria, text)
                                    if is_match:
                                        target_rec = recipient_entity or recipient_handle
                                        await self._dispatch_alert(
                                            task=current_task,
                                            msg=m,
                                            text=text,
                                            ch_title=ch_title,
                                            ch_handle=ch_handle,
                                            recipient_entity=target_rec,
                                            reason=reason,
                                        )
                            except Exception as ch_err:
                                err_str = str(ch_err)
                                if "FloodWait" in err_str:
                                    logger.warning("[%s] Telegram FloodWait encountered during periodic check: %s. Backing off temporarily.", task.id, ch_err)
                                    await asyncio.sleep(5)
                                else:
                                    logger.warning("[%s] Error in periodic channel check for %s: %s", task.id, ch_title, ch_err)

                    except asyncio.CancelledError:
                        break
                    except Exception as loop_err:
                        logger.error("[%s] Error in periodic recheck loop: %s", task.id, loop_err)

            # Store handler and launch periodic polling task
            self.stop_task_monitor(task.id)
            self._handlers[task.id] = on_new_channel_message
            self._poll_tasks[task.id] = asyncio.create_task(periodic_recheck_loop())

            configured_interval = max(int(getattr(task.config, "interval_seconds", 1) or 1), 1)
            logger.info(
                "[%s] Actively listening for new messages across %d channel(s) (with %ds periodic safety check).",
                task.id,
                len(resolved_channels),
                configured_interval,
            )
            return True

        except Exception as exc:
            logger.error("[%s] Error initializing real-time monitor: %s", task.id, exc)
            return False

    async def _dispatch_alert(
        self,
        task: Task,
        msg: Any,
        text: str,
        ch_title: str,
        ch_handle: str,
        recipient_entity: Any,
        reason: str,
    ) -> None:
        """Deliver matched post alert to recipient and notify user."""
        try:
            delivered = await self.notifier.send_alert(
                recipient_entity=recipient_entity,
                post_message=msg,
                channel_name=ch_title,
                channel_handle=ch_handle,
                matched_topics=[reason],
                agent_name=task.id,
            )

            if self.task_store:
                preview = text.replace("\n", " ")[:60]
                self.task_store.record_match(task.id, f"[{ch_title}] {preview}...")

            # Real-time console notification for terminal user
            msg_notify = (
                f"\n\n[Sub-Agent Notification: Match found in @{ch_handle}! "
                f"Reason: {reason}\n"
                f"Forwarded Post #{msg.id} to {task.config.recipient}]\n"
                f"You: "
            )
            try:
                print(msg_notify, end="", flush=True)
            except Exception:
                try:
                    safe_notify = msg_notify.encode("ascii", "backslashreplace").decode("ascii")
                    print(safe_notify, end="", flush=True)
                except Exception:
                    pass

        except Exception as ex:
            logger.error("[%s] Error delivering alert: %s", task.id, ex)

    def stop_task_monitor(self, task_id: str) -> None:
        """Unregister event listener and clean up monitoring state for a task."""
        handler = self._handlers.pop(task_id, None)
        if handler and self.session_mgr.is_connected:
            try:
                self.session_mgr.client.remove_event_handler(handler)
                logger.info("[%s] Real-time event listener removed.", task_id)
            except Exception as e:
                logger.warning("[%s] Could not cleanly remove event handler: %s", task_id, e)

        poll_t = self._poll_tasks.pop(task_id, None)
        if poll_t and not poll_t.done():
            poll_t.cancel()
            logger.info("[%s] Periodic recheck task cancelled.", task_id)

    def pause_task_monitor(self, task_id: str) -> None:
        """Pause monitoring for a task (handler will ignore events)."""
        logger.info("[%s] Task monitoring paused.", task_id)

    def resume_task_monitor(self, task_id: str) -> None:
        """Resume monitoring for a task."""
        logger.info("[%s] Task monitoring resumed.", task_id)
