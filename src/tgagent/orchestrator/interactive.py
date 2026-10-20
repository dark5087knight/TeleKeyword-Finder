"""Interactive terminal chat interface for communicating directly with the Upper Agent via real LLM."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from tgagent.config import AppConfig, load_config
from tgagent.domain.models import (
    ChannelRef,
    DesiredState,
    RuntimeState,
    Task,
    TaskConfig,
    TaskRuntime,
)
from tgagent.llm.service import LLMService
from tgagent.telegram.client import TelegramSessionManager
from tgagent.workers.monitor import SubAgentWorker

logger = logging.getLogger("tgagent.interactive")


class InteractiveChat:
    """Console chat session allowing the user to converse with the Upper Agent via LLM."""

    def __init__(
        self,
        config: AppConfig | None = None,
        tasks: dict[str, Task] | None = None,
        llm_service: LLMService | None = None,
        session_mgr: TelegramSessionManager | None = None,
    ) -> None:
        self.config = config or load_config()
        self.tasks: dict[str, Task] = tasks if tasks is not None else {}
        self.llm_service = llm_service or LLMService(self.config)
        self.session_mgr = session_mgr or TelegramSessionManager(self.config)
        self.workers: dict[str, SubAgentWorker] = {}
        self.conversation_history: list[dict[str, str]] = []
        self.task_counter = 1

    def print_banner(self) -> None:
        banner = """
==============================================================
TeleKeyword Finder - Upper Agent Interactive Console
==============================================================
You are now chatting with the Upper Agent powered by your LLM.
Chat naturally or give monitoring tasks, for example:
  - "Hello, what can you do?"
  - "Is there any running agents?"
  - "Monitor @channel1 for Python and send to @myuser"
  - "Did you find any matches?"
  - "Pause subagent_1"

Type 'exit' or 'quit' at any time to shut down.
--------------------------------------------------------------"""
        print(banner)

    def _get_tasks_summary(self) -> str:
        """Build a plain-text summary of current tasks for LLM context."""
        if not self.tasks:
            return "No active sub-agents currently running."

        lines = ["Active Sub-Agents:"]
        for tid, t in self.tasks.items():
            channels = ", ".join(c.handle for c in t.config.channels)
            topics = ", ".join(t.config.topics)
            worker = self.workers.get(tid)
            match_stats = " | Matches found & delivered: 0"
            if worker:
                match_stats = f" | Matches found & delivered: {worker.matched_posts_count}"
                if worker.matched_posts_summary:
                    match_stats += f" (Recent: {'; '.join(worker.matched_posts_summary[-3:])})"

            lines.append(
                f"- Task ID: {tid} | State: {t.desired.value.upper()} | "
                f"Channels: {channels} | Topics: {topics} | Recipient: {t.config.recipient}{match_stats}"
            )
        return "\n".join(lines)

    async def handle_turn(self, user_input: str) -> str:
        """Process a message through the LLM and execute any triggered actions."""
        text = user_input.strip()
        if not text:
            return "Please enter a message or question for the Upper Agent."

        # Add user turn to conversation history
        self.conversation_history.append({"role": "user", "content": text})

        # Keep history to last 12 messages for efficiency
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]

        # Call LLM
        summary = self._get_tasks_summary()
        raw_response = await self.llm_service.chat_turn(self.conversation_history, summary)

        # Parse and execute any backend actions emitted by the LLM
        cleaned_response = self._process_actions(raw_response)

        # Add assistant turn to history
        self.conversation_history.append({"role": "assistant", "content": cleaned_response})

        return cleaned_response

    def _process_actions(self, response: str) -> str:
        """Detect and execute any ACTION blocks emitted by the LLM."""
        # 1. Check for CREATE_TASK
        if "ACTION: CREATE_TASK" in response:
            channels = []
            topics = []
            criteria = ""
            recipient = "@me"

            ch_match = re.search(r"CHANNELS:\s*(.+)", response)
            if ch_match:
                raw_chs = [c.strip() for c in ch_match.group(1).split(",")]
                channels = [c if c.startswith("@") else f"@{c}" for c in raw_chs if c]

            crit_match = re.search(r"CRITERIA:\s*(.+)", response)
            if crit_match:
                criteria = crit_match.group(1).strip()

            top_match = re.search(r"TOPICS:\s*(.+)", response)
            if top_match:
                topics = [t.strip() for t in top_match.group(1).split(",") if t.strip()]

            if not criteria and topics:
                criteria = ", ".join(topics)
            elif criteria and not topics:
                topics = [w for w in criteria.split() if len(w) > 3]

            rec_match = re.search(r"RECIPIENT:\s*([@\w_]+)", response)
            if rec_match:
                recipient = rec_match.group(1).strip()

            if channels and (criteria or topics):
                task_id = f"subagent_{self.task_counter}"
                self.task_counter += 1

                cfg = TaskConfig(
                    name=f"Monitor {' '.join((topics or [criteria])[:2])}",
                    topics=topics or [criteria],
                    criteria=criteria,
                    keywords=topics or [criteria],
                    channels=[ChannelRef(handle=c) for c in channels],
                    recipient=recipient,
                    interval_seconds=120,
                )

                task = Task(
                    id=task_id,
                    agent_type="channel_monitor",
                    owner_id=1,
                    config=cfg,
                    desired=DesiredState.ACTIVE,
                    runtime=TaskRuntime(state=RuntimeState.WAITING),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                self.tasks[task_id] = task

                # Launch active SubAgentWorker to monitor Telegram with LLM semantic evaluation
                worker = SubAgentWorker(task, self.session_mgr, llm_service=self.llm_service)
                self.workers[task_id] = worker
                asyncio.create_task(worker.start())

                # Strip raw action block from message
                clean_text = re.sub(
                    r"ACTION:\s*CREATE_TASK.*?(?=($|\n\n))",
                    "",
                    response,
                    flags=re.DOTALL,
                ).strip()

                return (
                    f"{clean_text}\n\n"
                    f"[System Notification: Sub-Agent '{task_id}' spawned successfully. "
                    f"Actively monitoring {len(channels)} channel(s) using criteria: '{criteria}', forwarding to {recipient}.]"
                )

        # 2. Check for PAUSE_TASK
        pause_match = re.search(r"ACTION:\s*PAUSE_TASK\s+([\w_]+)", response)
        if pause_match:
            tid = pause_match.group(1).strip()
            if tid in self.tasks:
                self.tasks[tid].desired = DesiredState.PAUSED
                self.tasks[tid].runtime.state = RuntimeState.STOPPED
                if tid in self.workers:
                    self.workers[tid].task.desired = DesiredState.PAUSED
                clean_text = re.sub(r"ACTION:\s*PAUSE_TASK[^\n]*", "", response).strip()
                return f"{clean_text}\n\n[System Notification: Sub-Agent '{tid}' is now PAUSED.]"

        # 3. Check for RESUME_TASK
        resume_match = re.search(r"ACTION:\s*RESUME_TASK\s+([\w_]+)", response)
        if resume_match:
            tid = resume_match.group(1).strip()
            if tid in self.tasks:
                self.tasks[tid].desired = DesiredState.ACTIVE
                self.tasks[tid].runtime.state = RuntimeState.WAITING
                if tid in self.workers:
                    self.workers[tid].task.desired = DesiredState.ACTIVE
                clean_text = re.sub(r"ACTION:\s*RESUME_TASK[^\n]*", "", response).strip()
                return f"{clean_text}\n\n[System Notification: Sub-Agent '{tid}' has RESUMED.]"

        # 4. Check for CANCEL_TASK
        cancel_match = re.search(r"ACTION:\s*CANCEL_TASK\s+([\w_]+)", response)
        if cancel_match:
            tid = cancel_match.group(1).strip()
            if tid in self.tasks:
                del self.tasks[tid]
                if tid in self.workers:
                    asyncio.create_task(self.workers[tid].stop())
                    del self.workers[tid]
                clean_text = re.sub(r"ACTION:\s*CANCEL_TASK[^\n]*", "", response).strip()
                return f"{clean_text}\n\n[System Notification: Sub-Agent '{tid}' has been TERMINATED.]"

        return response.strip()

    async def run_loop(self) -> None:
        """Run the interactive console prompt loop."""
        self.print_banner()

        # Connect Telethon in background
        try:
            await self.session_mgr.connect()
        except Exception as e:
            logger.warning("Could not pre-connect Telethon: %s", e)

        while True:
            try:
                loop = asyncio.get_running_loop()
                print("\nYou: ", end="", flush=True)
                user_msg = await loop.run_in_executor(None, sys.stdin.readline)

                if not user_msg:
                    break

                cleaned = user_msg.strip()
                if cleaned.lower() in ("exit", "quit", "q"):
                    print("\nUpper Agent: Goodbye! Shutting down system.")
                    break

                if not cleaned:
                    continue

                response = await self.handle_turn(cleaned)
                print(f"\nUpper Agent:\n{response}")

            except (KeyboardInterrupt, EOFError):
                print("\nUpper Agent: Session terminated.")
                break

        # Cleanup on exit
        for worker in self.workers.values():
            await worker.stop()
        await self.session_mgr.disconnect()
