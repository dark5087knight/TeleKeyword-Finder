"""Supervisor Upper Agent orchestrating specialized Sub-Agents with LangGraph."""

from __future__ import annotations

from typing import Any
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph_supervisor import create_supervisor

from tgagent.agents.channel_monitor import build_channel_monitor_agent
from tgagent.agents.delivery_agent import build_delivery_agent
from tgagent.agents.post_analyst import build_post_analyst_agent
from tgagent.agents.task_manager import build_task_manager_agent
from tgagent.config import AppConfig
from tgagent.llm.factory import create_chat_model, create_classifier_model
from tgagent.llm.prompts import SUPERVISOR_SYSTEM_PROMPT
from tgagent.state.checkpointer import create_checkpointer
from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager
from tgagent.telegram.monitor import RealtimeMonitorEngine
from tgagent.telegram.notifier import TelegramNotifier


def build_supervisor(
    config: AppConfig,
    task_store: TaskStore,
    session_mgr: TelegramSessionManager,
    checkpointer: BaseCheckpointSaver | None = None,
    monitor_engine: RealtimeMonitorEngine | None = None,
) -> CompiledStateGraph:
    """Build the complete multi-agent system with Upper Agent Supervisor.

    Orchestrates four specialized sub-agents:
    - task_manager: Task lifecycle management
    - channel_monitor: Telegram channel interaction & listening
    - post_analyst: Semantic post relevance evaluation
    - delivery: Alert notifications dispatching
    """
    active_engine = monitor_engine
    if active_engine is None:
        classifier_m = create_classifier_model(config)
        notifier = TelegramNotifier(session_mgr.client)
        active_engine = RealtimeMonitorEngine(
            session_mgr=session_mgr,
            classifier_model=classifier_m,
            notifier=notifier,
            task_store=task_store,
        )

    # 1. Build each sub-agent as an isolated compiled subgraph
    task_mgr = build_task_manager_agent(config, task_store, monitor_engine=active_engine)
    monitor = build_channel_monitor_agent(config, session_mgr, task_store=task_store)
    analyst = build_post_analyst_agent(config)
    delivery = build_delivery_agent(config, session_mgr)

    # 2. Supervisor model for coordination and user conversation
    supervisor_model = create_chat_model(config)

    # 3. Dynamic prompt injecting current live system state
    def get_supervisor_prompt(state: Any) -> list[BaseMessage]:
        tasks_summary = task_store.format_summary()
        sys_msg = SystemMessage(
            content=f"{SUPERVISOR_SYSTEM_PROMPT}\n\nCURRENT SYSTEM STATE:\n{tasks_summary}\n"
        )
        if isinstance(state, dict):
            msgs = state.get("messages", [])
        elif hasattr(state, "messages"):
            msgs = state.messages
        else:
            msgs = []
        return [sys_msg] + list(msgs)

    # 4. Create the supervisor workflow
    workflow = create_supervisor(
        agents=[task_mgr, monitor, analyst, delivery],
        model=supervisor_model,
        prompt=get_supervisor_prompt,
        supervisor_name="supervisor",
        output_mode="last_message",
    )

    # 5. Compile with checkpointer for conversational memory
    active_checkpointer = checkpointer if checkpointer is not None else create_checkpointer(config)
    return workflow.compile(checkpointer=active_checkpointer)
