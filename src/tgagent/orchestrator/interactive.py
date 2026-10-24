"""Interactive terminal chat interface for communicating directly with the Upper Agent via LangGraph."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from tgagent.agents.supervisor import build_supervisor
from tgagent.config import AppConfig, load_config
from tgagent.domain.models import Task
from tgagent.state.checkpointer import create_checkpointer
from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager

logger = logging.getLogger("tgagent.orchestrator.interactive")


class InteractiveChat:
    """Console chat session allowing the user to converse with the Upper Agent Supervisor."""

    def __init__(
        self,
        config: AppConfig | None = None,
        task_store: TaskStore | None = None,
        session_mgr: TelegramSessionManager | None = None,
        tasks: dict[str, Task] | None = None,
        thread_id: str = "interactive_session",
    ) -> None:
        self.config = config or load_config()
        self.task_store = task_store or TaskStore(initial_tasks=tasks)
        self.session_mgr = session_mgr or TelegramSessionManager(self.config)
        self.thread_id = thread_id
        self.checkpointer = create_checkpointer(self.config)

        # Build the complete multi-agent graph
        self.graph = build_supervisor(
            config=self.config,
            task_store=self.task_store,
            session_mgr=self.session_mgr,
            checkpointer=self.checkpointer,
        )

    def print_banner(self) -> None:
        banner = """
==============================================================
TeleKeyword Finder - Upper Agent Interactive Console
==============================================================
You are now chatting with the Upper Agent powered by LangGraph.
Chat naturally or give monitoring tasks, for example:
  - "Hello, what can you do?"
  - "Are there any running sub-agents?"
  - "Monitor @channel1 for Python jobs and send to @myuser"
  - "Pause subagent_1"
  - "Resume subagent_1"
  - "Cancel subagent_1"

Type 'exit' or 'quit' at any time to shut down.
--------------------------------------------------------------"""
        print(banner)

    async def handle_turn(self, user_input: str) -> str:
        """Process user input through the supervisor graph and return the synthesized response."""
        text = user_input.strip()
        if not text:
            return "Please enter a message or question for the Upper Agent."

        try:
            result = await self.graph.ainvoke(
                {"messages": [("user", text)]},
                config={"configurable": {"thread_id": self.thread_id}},
            )

            messages = result.get("messages", [])
            if not messages:
                return "No response received from the agent system."

            # Find the last message with meaningful content
            last_msg = None
            for m in reversed(messages):
                cnt = getattr(m, "content", "")
                if (isinstance(cnt, str) and cnt.strip()) or (isinstance(cnt, list) and any(cnt)):
                    last_msg = m
                    break

            if last_msg is None:
                last_msg = messages[-1]

            content = getattr(last_msg, "content", "")

            # If content is a list of blocks (e.g. Claude/Gemini structured text)
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                return "\n".join(text_parts).strip()

            return str(content).strip()

        except Exception as exc:
            logger.error("Error during agent graph execution: %s", exc, exc_info=True)
            return f"An error occurred while processing your request: {str(exc)}"

    async def run_loop(self) -> None:
        """Terminal interactive chat loop with real-time response rendering."""
        self.print_banner()

        # Connect Telegram client in background if credentials present
        if self.config.telegram.bot_token or self.config.telegram.api_id:
            try:
                connected = await self.session_mgr.connect()
                if connected:
                    logger.info("Telegram session connected.")
                else:
                    print("\n[Notice: Telegram session not logged in. Monitoring tools will require login.]")
            except Exception as e:
                logger.warning("Could not connect Telegram session on startup: %s", e)

        # Ensure UTF-8 console output for Windows terminal support (Arabic & multilingual)
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        while True:
            try:
                print("\nYou: ", end="", flush=True)
                user_msg = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                print("\nExiting session...")
                break

            if not user_msg:
                break

            cleaned = user_msg.strip()
            if not cleaned:
                continue

            if cleaned.lower() in ("exit", "quit"):
                print("Upper Agent: Goodbye!")
                break

            response = await self.handle_turn(cleaned)
            print(f"\nUpper Agent:\n{response}")
