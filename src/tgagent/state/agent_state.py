"""State definitions for LangGraph multi-agent orchestration."""

from typing import Annotated, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Core state for TeleKeyword Finder Upper Agent supervisor and sub-agents."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    active_tasks_summary: str
    next_agent: str
