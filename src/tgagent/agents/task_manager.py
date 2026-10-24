"""Task Manager Sub-Agent for managing monitoring tasks lifecycle."""

from __future__ import annotations

from typing import Any
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from tgagent.config import AppConfig
from tgagent.llm.factory import create_chat_model
from tgagent.llm.prompts import TASK_MANAGER_PROMPT
from tgagent.state.task_store import TaskStore
from tgagent.tools.task_tools import make_task_tools


def build_task_manager_agent(
    config: AppConfig,
    task_store: TaskStore,
    monitor_engine: Any = None,
) -> CompiledStateGraph:
    """Build the Task Manager sub-agent subgraph.

    Responsible for creating, pausing, resuming, cancelling, listing,
    and retrieving status of Telegram channel monitoring tasks.
    """
    model = create_chat_model(config)
    tools = make_task_tools(task_store, monitor_engine=monitor_engine)

    return create_react_agent(
        model=model,
        tools=tools,
        name="task_manager",
        prompt=TASK_MANAGER_PROMPT,
    )
