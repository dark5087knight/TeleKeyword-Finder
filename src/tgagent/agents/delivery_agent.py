"""Delivery Sub-Agent for formatting and dispatching alerts to recipients."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from tgagent.config import AppConfig
from tgagent.llm.factory import create_chat_model
from tgagent.llm.prompts import DELIVERY_AGENT_PROMPT
from tgagent.telegram.client import TelegramSessionManager
from tgagent.telegram.notifier import TelegramNotifier
from tgagent.tools.delivery_tools import make_delivery_tools


def build_delivery_agent(
    config: AppConfig,
    session_mgr: TelegramSessionManager,
    notifier: TelegramNotifier | None = None,
) -> CompiledStateGraph:
    """Build the Delivery sub-agent subgraph.

    Responsible for formatting alerts and delivering matched post notifications
    to recipients via Telegram.
    """
    model = create_chat_model(config)
    tools = make_delivery_tools(session_mgr, notifier=notifier)

    return create_react_agent(
        model=model,
        tools=tools,
        name="delivery",
        prompt=DELIVERY_AGENT_PROMPT,
    )
