from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any  

from tgagent.config import AppConfig, load_config
from tgagent.orchestrator.interactive import InteractiveChat
from tgagent.security.redaction import setup_logging

logger = logging.getLogger("tgagent.main")


class Application:
    """Central application coordinator managing startup, interactive chat, and shutdown."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self._shutdown_event = asyncio.Event()
        self._is_running = False
        self.chat = InteractiveChat()

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        """Start application services and initialize background engine."""
        setup_logging(self.config.log_level)
        logger.info("Starting tgagent v0.1.0...")

        self._is_running = True
        logger.info(
            "tgagent started successfully (limits: max_tasks_per_user=%d, max_concurrency=%d)",
            self.config.limits.max_tasks_per_user,
            self.config.limits.max_concurrent_executions,
        )

    async def stop(self) -> None:
        """Execute graceful shutdown sequence."""
        if not self._is_running:
            return

        logger.info("Initiating graceful shutdown sequence...")
        self._is_running = False
        self._shutdown_event.set()
        logger.info("tgagent stopped cleanly.")

    async def run_until_stopped(self) -> None:
        """Run background services until stop() is called."""
        await self.start()
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    async def run_interactive(self) -> None:
        """Launch the background engine and start the interactive terminal chat."""
        await self.start()
        try:
            await self.chat.run_loop()
        finally:
            await self.stop()


def handle_signals(app: Application, loop: asyncio.AbstractEventLoop) -> None:
    """Attach graceful shutdown signal handlers if supported on the platform."""
    def _trigger_stop() -> None:
        logger.info("Received termination signal.")
        asyncio.create_task(app.stop())

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _trigger_stop)
            except (NotImplementedError, RuntimeError):
                pass


async def main() -> None:
    """CLI entry point for python -m tgagent, launching the interactive chat."""
    app = Application()
    loop = asyncio.get_running_loop()
    handle_signals(app, loop)

    try:
        await app.run_interactive()
    except (KeyboardInterrupt, asyncio.CancelledError):
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
