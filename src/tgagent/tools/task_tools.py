"""Task management tools for creating, listing, pausing, resuming, and cancelling monitoring tasks."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from langchain_core.tools import BaseTool, tool
from tgagent.state.task_store import TaskStore


def make_task_tools(task_store: TaskStore, monitor_engine: Any = None) -> list[BaseTool]:
    """Create task management tools bound to a TaskStore and optional RealtimeMonitorEngine."""

    @tool
    async def create_monitoring_task(
        channels: list[str],
        criteria: str,
        recipient: str,
        interval_seconds: int = 120,
    ) -> str:
        """Create a new Telegram channel monitoring task and start live monitoring.

        Args:
            channels: List of Telegram channel usernames or handles (e.g. ['@tech_news', '@python_jobs']).
            criteria: Natural language explanation of what posts to track.
            recipient: Telegram username or handle to forward matching posts to (e.g. '@myuser').
            interval_seconds: Polling check interval in seconds (minimum 60).
        """
        try:
            if not channels:
                return "Error: At least one channel must be provided."
            if not criteria.strip():
                return "Error: Monitoring criteria cannot be empty."
            if not recipient.strip():
                return "Error: Recipient must be provided."

            task = task_store.create(
                channels=channels,
                criteria=criteria,
                recipient=recipient,
                interval_seconds=interval_seconds,
            )

            # Start real-time monitoring engine immediately if available
            if monitor_engine is not None:
                bg_task = asyncio.create_task(monitor_engine.start_task_monitor(task))
                task_store.attach_listener_task(task.id, bg_task)

                def _on_task_done(t: asyncio.Task[Any]) -> None:
                    try:
                        err = t.exception()
                        if err:
                            import logging
                            logging.getLogger("tgagent.tools.task_tools").error(
                                "[%s] Error in monitoring task: %s", task.id, err, exc_info=True
                            )
                    except (asyncio.CancelledError, asyncio.InvalidStateError):
                        pass

                bg_task.add_done_callback(_on_task_done)

            ch_list = ", ".join(c.handle for c in task.config.channels)
            return (
                f"Task '{task.id}' created successfully. Monitoring channels: {ch_list} "
                f"for criteria: '{criteria}', forwarding alerts to: {recipient}."
            )
        except Exception as exc:
            return f"Error creating task: {str(exc)}"

    @tool
    async def list_active_tasks() -> str:
        """List all currently active or registered monitoring sub-agent tasks and their metrics."""
        try:
            return task_store.format_summary()
        except Exception as exc:
            return f"Error listing tasks: {str(exc)}"

    @tool
    async def pause_task(task_id: str) -> str:
        """Pause a running monitoring sub-agent.

        Args:
            task_id: The ID of the task to pause (e.g. 'subagent_1').
        """
        try:
            tid = task_id.strip()
            ok = task_store.pause(tid)
            if ok:
                if monitor_engine is not None:
                    monitor_engine.pause_task_monitor(tid)
                return f"Task '{tid}' is now PAUSED."
            return f"Task '{tid}' not found."
        except Exception as exc:
            return f"Error pausing task {task_id}: {str(exc)}"

    @tool
    async def resume_task(task_id: str) -> str:
        """Resume a paused monitoring sub-agent.

        Args:
            task_id: The ID of the task to resume (e.g. 'subagent_1').
        """
        try:
            tid = task_id.strip()
            ok = task_store.resume(tid)
            if ok:
                if monitor_engine is not None:
                    monitor_engine.resume_task_monitor(tid)
                return f"Task '{tid}' has been RESUMED and is actively monitoring."
            return f"Task '{tid}' not found."
        except Exception as exc:
            return f"Error resuming task {task_id}: {str(exc)}"

    @tool
    async def cancel_task(task_id: str) -> str:
        """Permanently cancel and remove a monitoring sub-agent task.

        Args:
            task_id: The ID of the task to cancel (e.g. 'subagent_1').
        """
        try:
            tid = task_id.strip()
            ok = task_store.cancel(tid)
            if ok:
                if monitor_engine is not None:
                    monitor_engine.stop_task_monitor(tid)
                return f"Task '{tid}' has been cancelled and permanently removed."
            return f"Task '{tid}' not found."
        except Exception as exc:
            return f"Error cancelling task {task_id}: {str(exc)}"

    @tool
    async def get_task_status(task_id: str) -> str:
        """Get detailed status, metrics, and recent match history for a specific task.

        Args:
            task_id: The ID of the task to inspect (e.g. 'subagent_1').
        """
        try:
            tid = task_id.strip()
            info = task_store.get_status(tid)
            if not info:
                return f"Task '{tid}' not found."
            return json.dumps(info, indent=2)
        except Exception as exc:
            return f"Error retrieving task status {task_id}: {str(exc)}"

    return [
        create_monitoring_task,
        list_active_tasks,
        pause_task,
        resume_task,
        cancel_task,
        get_task_status,
    ]

