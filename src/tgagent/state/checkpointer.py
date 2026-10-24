"""Checkpointer factory for LangGraph conversation persistence."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from tgagent.config import AppConfig


def create_checkpointer(config: AppConfig | None = None) -> BaseCheckpointSaver:
    """Create a checkpointer for conversational and agent state persistence.
    
    Defaults to MemorySaver for fast in-memory execution.
    Can be swapped to SqliteSaver or other persistent backends.
    """
    return MemorySaver()
