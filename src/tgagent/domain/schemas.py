"""Pydantic schemas for LangChain tools, structured outputs, and routing decisions.

Replaces deprecated commands.py and regex-based action parsing with structured schemas.
"""

from typing import Literal
from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Supervisor routing output for coordinating sub-agents."""
    next_agent: Literal[
        "task_manager",
        "channel_monitor",
        "post_analyst",
        "delivery",
        "respond_directly",
        "__end__",
    ] = Field(
        description="The sub-agent to delegate to, 'respond_directly' to answer the user without delegation, or '__end__' to complete turn."
    )
    reasoning: str = Field(
        description="Brief explanation of why this routing choice was made."
    )
    context: str = Field(
        default="",
        description="Summarized instruction, extracted entities, or context passed to the delegated sub-agent.",
    )


class PostEvaluationResult(BaseModel):
    """Structured verdict for semantic post relevance against criteria."""
    is_relevant: bool = Field(
        description="True if the post content matches the monitoring criteria, False otherwise."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    reason: str = Field(
        description="Brief explanation justifying why the post matches or does not match."
    )


class TaskCreationInput(BaseModel):
    """Input payload for creating a new monitoring task."""
    channels: list[str] = Field(
        description="List of Telegram channel handles or usernames, e.g. ['@channel1', '@channel2']."
    )
    criteria: str = Field(
        description="Natural language criteria or description of what posts to look for."
    )
    recipient: str = Field(
        description="Telegram recipient username or handle to receive matched post alerts."
    )
    interval_seconds: int = Field(
        default=120,
        ge=60,
        description="Polling check interval in seconds (minimum 60s).",
    )


class AlertDeliveryInput(BaseModel):
    """Input payload for delivering a matched post notification."""
    recipient: str = Field(
        description="Telegram username or chat ID of the recipient."
    )
    channel_name: str = Field(
        description="Display title of the channel."
    )
    channel_handle: str = Field(
        description="Channel username handle, e.g. @tech_news."
    )
    message_id: int = Field(
        description="Telegram message ID in the source channel."
    )
    post_text: str = Field(
        description="Text content of the discovered post."
    )
    match_reason: str = Field(
        description="Reasoning of why this post matched the monitoring criteria."
    )
    agent_name: str = Field(
        default="",
        description="Optional name or ID of the sub-agent task that found the post.",
    )
