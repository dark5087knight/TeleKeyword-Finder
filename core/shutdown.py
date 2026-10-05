import sys
import signal
import asyncio
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """
    Coordinates graceful application shutdown across platforms.
    Handles SIGINT / SIGTERM signals and optional keyboard exit keys.
    """

    def __init__(self, exit_key: str = "esc", enable_keyboard: bool = True):
        self.exit_key = exit_key.lower()
        self.enable_keyboard = enable_keyboard
        self.event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._kb_thread: Optional[threading.Thread] = None

    def trigger(self, reason: str = "Shutdown requested") -> None:
        """Trigger the shutdown event in a thread-safe manner."""
        logger.info(f"{reason}. Initiating graceful shutdown...")
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self.event.set)
        else:
            self.event.set()

    def setup(self) -> None:
        """Register OS signals and start background keyboard listener if enabled."""
        self._loop = asyncio.get_running_loop()

        # Handle SIGINT and SIGTERM
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                # signal.signal works on Windows and Unix for SIGINT and SIGTERM
                signal.signal(sig, lambda s, f: self.trigger(f"Signal {s} received"))
            except Exception as e:
                logger.debug(f"Could not bind signal {sig}: {e}")

        if self.enable_keyboard:
            self._start_keyboard_thread()

    def _start_keyboard_thread(self) -> None:
        def listener():
            # Try keyboard package if available
            try:
                import keyboard
                logger.info(f"Press '{self.exit_key.upper()}' or Ctrl+C to safely exit...")
                keyboard.wait(self.exit_key)
                self.trigger(f"'{self.exit_key.upper()}' key pressed")
                return
            except (ImportError, Exception):
                pass

            # Fallback to stdin Enter key in interactive console
            if sys.stdin and sys.stdin.isatty():
                try:
                    logger.info("Press [ENTER] or Ctrl+C to safely exit...")
                    sys.stdin.readline()
                    self.trigger("Enter pressed")
                except Exception:
                    pass

        self._kb_thread = threading.Thread(target=listener, daemon=True)
        self._kb_thread.start()

    async def wait(self) -> None:
        """Wait until shutdown is signaled."""
        await self.event.wait()

    @property
    def is_triggered(self) -> bool:
        return self.event.is_set()
