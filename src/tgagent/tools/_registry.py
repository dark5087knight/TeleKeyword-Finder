"""Tool registry and grouping helpers for TeleKeyword Finder multi-agent system."""

from __future__ import annotations

from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from tgagent.state.task_store import TaskStore
from tgagent.telegram.client import TelegramSessionManager
from tgagent.telegram.notifier import TelegramNotifier
from tgagent.tools.analysis_tools import make_analysis_tools
from tgagent.tools.delivery_tools import make_delivery_tools
from tgagent.tools.task_tools import make_task_tools
from tgagent.tools.telegram_tools import make_telegram_tools


class ToolRegistry:
    """Central registry and grouping helper for all agent tools."""

    def __init__(
        self,
        task_store: TaskStore | None = None,
        session_mgr: TelegramSessionManager | None = None,
        classifier_model: BaseChatModel | None = None,
        notifier: TelegramNotifier | None = None,
        monitor_engine: Any = None,
    ) -> None:
        self.task_store = task_store
        self.session_mgr = session_mgr
        self.classifier_model = classifier_model
        self.notifier = notifier
        self.monitor_engine = monitor_engine

    def get_task_tools(self) -> list[BaseTool]:
        """Return all tools allocated to the Task Manager sub-agent."""
        if not self.task_store:
            raise ValueError("TaskStore instance required to initialize task tools.")
        return make_task_tools(self.task_store, monitor_engine=self.monitor_engine)

    def get_telegram_tools(self) -> list[BaseTool]:
        """Return all tools allocated to the Channel Monitor sub-agent."""
        if not self.session_mgr:
            raise ValueError("TelegramSessionManager instance required to initialize telegram tools.")
        return make_telegram_tools(
            session_mgr=self.session_mgr,
            task_store=self.task_store,
            classifier_model=self.classifier_model,
            notifier=self.notifier,
        )

    def get_analysis_tools(self) -> list[BaseTool]:
        """Return all tools allocated to the Post Analyst sub-agent."""
        if not self.classifier_model:
            raise ValueError("Classifier ChatModel instance required to initialize analysis tools.")
        return make_analysis_tools(self.classifier_model)

    def get_delivery_tools(self) -> list[BaseTool]:
        """Return all tools allocated to the Delivery sub-agent."""
        if not self.session_mgr:
            raise ValueError("TelegramSessionManager instance required to initialize delivery tools.")
        return make_delivery_tools(self.session_mgr, notifier=self.notifier)

    def get_all_tools(self) -> dict[str, list[BaseTool]]:
        """Return all tools organized by agent domain."""
        result: dict[str, list[BaseTool]] = {}
        if self.task_store:
            result["task_manager"] = self.get_task_tools()
        if self.session_mgr:
            result["channel_monitor"] = self.get_telegram_tools()
            result["delivery"] = self.get_delivery_tools()
        if self.classifier_model:
            result["post_analyst"] = self.get_analysis_tools()
        return result
