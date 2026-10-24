"""Channel Monitor Sub-Agent for interacting with Telegram channels."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from tgagent.config import AppConfig
from tgagent.llm.factory import create_chat_model, create_classifier_model
from tgagent.llm.prompts import CHANNEL_MONITOR_PROMPT
from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager
from tgagent.telegram.notifier import TelegramNotifier
from tgagent.tools.telegram_tools import make_telegram_tools


def build_channel_monitor_agent(
    config: AppConfig,
    session_mgr: TelegramSessionManager,
    task_store: TaskStore | None = None,
    notifier: TelegramNotifier | None = None,
) -> CompiledStateGraph:
    """Build the Channel Monitor sub-agent subgraph.

    Responsible for resolving Telegram channel usernames, fetching recent
    posts, inspecting unread messages, and registering real-time listeners.
    """
    model = create_chat_model(config)
    classifier_model = create_classifier_model(config)
    tools = make_telegram_tools(
        session_mgr=session_mgr,
        task_store=task_store,
        classifier_model=classifier_model,
        notifier=notifier,
    )

    return create_react_agent(
        model=model,
        tools=tools,
        name="channel_monitor",
        prompt=CHANNEL_MONITOR_PROMPT,
    )
