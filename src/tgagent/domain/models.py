from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Protocol
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DesiredState(StrEnum):
    """What the user wants the task state to be."""
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class RuntimeState(StrEnum):
    """What the execution plane is doing with the task right now."""
    STOPPED = "stopped"
    WAITING = "waiting"
    RUNNING = "running"
    BACKING_OFF = "backing_off"
    ERRORED = "errored"


class ExecutionStatus(StrEnum):
    """Status of an individual task execution run."""
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class DeliveryStatus(StrEnum):
    """Status of a post delivery to a recipient."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Role(StrEnum):
    """Access control role for registered users."""
    ADMIN = "admin"
    USER = "user"


class AgentName(StrEnum):
    """Names of agents in the multi-agent system."""
    SUPERVISOR = "supervisor"
    TASK_MANAGER = "task_manager"
    CHANNEL_MONITOR = "channel_monitor"
    POST_ANALYST = "post_analyst"
    DELIVERY = "delivery"


# ---------------------------------------------------------------------------
# User & Auth Models
# ---------------------------------------------------------------------------

@dataclass
class UserLimits:
    max_tasks: int = 5
    max_channels_per_task: int = 10
    max_concurrent_executions: int = 1
    daily_llm_calls: int = 2000


@dataclass
class User:
    telegram_user_id: int
    role: Role
    limits: UserLimits
    default_llm_profile_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    approved_at: datetime | None = None


@dataclass
class Recipient:
    owner_id: int
    alias: str
    chat_id: int
    verified_at: datetime = field(default_factory=utc_now)


@dataclass
class LLMProfile:
    id: str
    owner_id: int
    provider: Literal["openai", "groq", "gemini", "anthropic", "ollama"]
    control_model: str
    classifier_model: str
    secret_ref: str
    schema_mode: Literal["json_schema", "json_object", "prompt_only"] = "json_schema"
    last_validated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Agent & Task Definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentDefinition:
    agent_type: str
    description: str
    config_model: type[BaseModel]


class ChannelRef(BaseModel, frozen=True):
    handle: str
    channel_id: int | None = None


class TaskConfig(BaseModel, frozen=True):
    version: int = 1
    name: str
    topics: list[str]
    criteria: str
    keywords: list[str]
    exclude_keywords: list[str] = Field(default_factory=list)
    channels: list[ChannelRef]
    recipient: str
    interval_seconds: int = Field(ge=60)
    prefilter: Literal["keywords", "none"] = "keywords"
    delivery: Literal["immediate", "digest"] = "immediate"
    summarize: bool = False
    min_confidence: float = 0.6
    max_deliveries_per_run: int = 10
    initial_lookback_posts: int = 0


@dataclass
class TaskRuntime:
    state: RuntimeState = RuntimeState.STOPPED
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    checkpoints: dict[int, int] = field(default_factory=dict)
    unavailable_channels: dict[int, str] = field(default_factory=dict)


@dataclass
class Task:
    id: str
    agent_type: str
    owner_id: int
    config: TaskConfig
    desired: DesiredState
    runtime: TaskRuntime
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Pipeline & Execution Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscoveredPost:
    channel_id: int
    channel_handle: str
    message_id: int
    grouped_id: int | None
    posted_at: datetime
    text: str
    permalink: str | None
    has_media: bool
    text_hash: str


@dataclass
class PostDecision:
    channel_id: int
    message_id: int
    stage: Literal["filter", "keyword", "llm"]
    verdict: Literal["dropped", "relevant", "not_relevant", "error"]
    reason: str


@dataclass
class TaskExecution:
    id: str
    task_id: str
    config_version: int
    trigger: Literal["schedule", "manual"]
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    status: ExecutionStatus = ExecutionStatus.RUNNING
    fetched: int = 0
    filtered_out: int = 0
    evaluated: int = 0
    relevant: int = 0
    delivered: int = 0
    failed_deliveries: int = 0
    llm_calls: int = 0
    channel_errors: dict[int, str] = field(default_factory=dict)
    decisions: list[PostDecision] = field(default_factory=list)
    error: str | None = None


@dataclass
class DeliveryRecord:
    id: str
    task_id: str
    recipient: str
    channel_id: int
    message_id: int
    status: DeliveryStatus
    attempts: int = 0
    created_at: datetime = field(default_factory=utc_now)
    sent_at: datetime | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Storage Protocols
# ---------------------------------------------------------------------------

class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...
    async def get(self, task_id: str) -> Task | None: ...
    async def list(self, *, owner_id: int | None = None) -> list[Task]: ...
    async def update_config(self, task_id: str, config: TaskConfig) -> Task: ...
    async def set_desired_state(self, task_id: str, s: DesiredState) -> Task: ...
    async def update_runtime(self, task_id: str, **changes) -> Task: ...
    async def save_checkpoint(self, task_id: str, channel_id: int, message_id: int) -> None: ...
    async def append_execution(self, ex: TaskExecution) -> None: ...
    async def recent_executions(self, task_id: str, limit: int = 20) -> list[TaskExecution]: ...
    async def reserve_delivery(self, rec: DeliveryRecord) -> bool: ...
    async def finish_delivery(
        self,
        task_id: str,
        channel_id: int,
        message_id: int,
        status: DeliveryStatus,
        error: str | None = None,
    ) -> None: ...


class UserRepository(Protocol):
    async def get_user(self, telegram_user_id: int) -> User | None: ...
    async def upsert_user(self, user: User) -> None: ...
    async def list_profiles(self, owner_id: int) -> list[LLMProfile]: ...
    async def upsert_profile(self, profile: LLMProfile) -> None: ...
    async def list_recipients(self, owner_id: int) -> list[Recipient]: ...
    async def upsert_recipient(self, r: Recipient) -> None: ...


class SecretStore(Protocol):
    async def put(self, ref: str, secret: str) -> None: ...
    async def get(self, ref: str) -> str: ...
    async def delete(self, ref: str) -> None: ...
