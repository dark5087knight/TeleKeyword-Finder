"""Command schemas representing the closed tool set emitted by the LLM Orchestrator.

These schemas are validated by Pydantic and executed strictly by deterministic code.
"""

from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field


class CreateTask(BaseModel):
    action: Literal["create_task"] = "create_task"
    name: str | None = None
    topics: list[str]
    channels: list[str]
    recipient: str
    interval_seconds: int | None = None


class UpdateTask(BaseModel):
    action: Literal["update_task"] = "update_task"
    task_ref: str
    add_channels: list[str] = Field(default_factory=list)
    remove_channels: list[str] = Field(default_factory=list)
    topics: list[str] | None = None
    recipient: str | None = None
    interval_seconds: int | None = None


class TaskCommand(BaseModel):
    action: Literal[
        "pause_task",
        "resume_task",
        "cancel_task",
        "task_status",
        "diagnose_task",
    ]
    task_ref: str


class ListTasks(BaseModel):
    action: Literal["list_tasks"] = "list_tasks"


class Clarify(BaseModel):
    action: Literal["clarify"] = "clarify"
    question: str


Command = Annotated[
    Union[CreateTask, UpdateTask, TaskCommand, ListTasks, Clarify],
    Field(discriminator="action"),
]


class AgentTurn(BaseModel):
    commands: list[Command] = Field(min_length=1, max_length=5)
