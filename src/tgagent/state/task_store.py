"""In-memory task store managing monitoring tasks and active sub-agent metrics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from tgagent.domain.models import (
    ChannelRef,
    DesiredState,
    RuntimeState,
    Task,
    TaskConfig,
    TaskRuntime,
)

logger = logging.getLogger("tgagent.state.task_store")


class TaskStore:
    """Thread-safe store for monitoring tasks and running sub-agent background listeners."""

    def __init__(self, initial_tasks: dict[str, Task] | None = None) -> None:
        self._tasks: dict[str, Task] = initial_tasks if initial_tasks is not None else {}
        self._counter: int = len(self._tasks) + 1
        self._metrics: dict[str, dict[str, Any]] = {}
        self._background_tasks: dict[str, asyncio.Task[Any]] = {}

        for tid in self._tasks:
            self._metrics[tid] = {
                "matched_count": 0,
                "recent_matches": [],
            }

    def create(
        self,
        channels: list[str],
        criteria: str,
        recipient: str,
        interval_seconds: int = 120,
        name: str = "",
    ) -> Task:
        """Create and register a new monitoring task."""
        from tgagent.telegram.client import clean_identifier
        sanitized_channels = [
            f"@{clean_identifier(c)}"
            for c in channels
            if clean_identifier(c)
        ]

        topics = [w for w in criteria.split() if len(w) > 3][:5]
        task_id = f"subagent_{self._counter}"
        self._counter += 1

        task_name = name or f"Monitor {' '.join((topics or [criteria])[:2])}"

        cfg = TaskConfig(
            name=task_name,
            topics=topics or [criteria],
            criteria=criteria,
            keywords=topics or [criteria],
            channels=[ChannelRef(handle=c) for c in sanitized_channels],
            recipient=recipient.strip(),
            interval_seconds=max(interval_seconds, 60),
        )

        task = Task(
            id=task_id,
            agent_type="channel_monitor",
            owner_id=1,
            config=cfg,
            desired=DesiredState.ACTIVE,
            runtime=TaskRuntime(state=RuntimeState.RUNNING),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._tasks[task_id] = task
        self._metrics[task_id] = {
            "matched_count": 0,
            "recent_matches": [],
        }

        logger.info("Created task %s with channels: %s", task_id, sanitized_channels)
        return task

    def get(self, task_id: str) -> Task | None:
        """Retrieve a task by ID."""
        return self._tasks.get(task_id)

    def list_all(self) -> list[Task]:
        """List all tasks."""
        return list(self._tasks.values())

    def pause(self, task_id: str) -> bool:
        """Pause a running monitoring task."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.desired = DesiredState.PAUSED
        task.runtime.state = RuntimeState.STOPPED
        task.updated_at = datetime.now(timezone.utc)
        self.stop_listener(task_id)
        logger.info("Task %s paused", task_id)
        return True

    def resume(self, task_id: str) -> bool:
        """Resume a paused monitoring task."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.desired = DesiredState.ACTIVE
        task.runtime.state = RuntimeState.RUNNING
        task.updated_at = datetime.now(timezone.utc)
        logger.info("Task %s resumed", task_id)
        return True

    def cancel(self, task_id: str) -> bool:
        """Cancel and remove a monitoring task."""
        if task_id not in self._tasks:
            return False

        self.stop_listener(task_id)
        del self._tasks[task_id]
        if task_id in self._metrics:
            del self._metrics[task_id]

        logger.info("Task %s cancelled and deleted", task_id)
        return True

    def record_match(self, task_id: str, summary_text: str) -> None:
        """Record a matched post finding for a task."""
        if task_id not in self._metrics:
            self._metrics[task_id] = {"matched_count": 0, "recent_matches": []}

        self._metrics[task_id]["matched_count"] += 1
        matches = self._metrics[task_id]["recent_matches"]
        matches.append(summary_text)
        if len(matches) > 10:
            self._metrics[task_id]["recent_matches"] = matches[-10:]

    def attach_listener_task(self, task_id: str, bg_task: asyncio.Task[Any]) -> None:
        """Store reference to background asyncio task (e.g. Telethon event listener loop)."""
        self.stop_listener(task_id)
        self._background_tasks[task_id] = bg_task

    def stop_listener(self, task_id: str) -> None:
        """Cancel background asyncio task for this task if active."""
        bg_task = self._background_tasks.pop(task_id, None)
        if bg_task and not bg_task.done():
            bg_task.cancel()

    def get_status(self, task_id: str) -> dict[str, Any] | None:
        """Get detailed status and statistics for a specific task."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        metrics = self._metrics.get(task_id, {"matched_count": 0, "recent_matches": []})
        return {
            "task_id": task.id,
            "name": task.config.name,
            "desired_state": task.desired.value.upper(),
            "runtime_state": task.runtime.state.value.upper(),
            "channels": [c.handle for c in task.config.channels],
            "criteria": task.config.criteria,
            "recipient": task.config.recipient,
            "interval_seconds": task.config.interval_seconds,
            "created_at": task.created_at.isoformat(),
            "matched_count": metrics["matched_count"],
            "recent_matches": list(metrics["recent_matches"]),
        }

    def format_summary(self) -> str:
        """Build a human-readable summary of all tasks for agent context."""
        if not self._tasks:
            return "No active sub-agents currently running."

        lines = ["Active Sub-Agents:"]
        for tid, t in self._tasks.items():
            channels = ", ".join(c.handle for c in t.config.channels)
            metrics = self._metrics.get(tid, {"matched_count": 0, "recent_matches": []})
            matched_count = metrics["matched_count"]
            recent = metrics["recent_matches"]

            stats = f" | Matches found & delivered: {matched_count}"
            if recent:
                stats += f" (Recent: {'; '.join(recent[-3:])})"

            lines.append(
                f"- Task ID: {tid} | State: {t.desired.value.upper()} | "
                f"Channels: {channels} | Criteria: '{t.config.criteria}' | "
                f"Recipient: {t.config.recipient}{stats}"
            )
        return "\n".join(lines)
