import sqlite3
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


from contextlib import contextmanager

class SeenMessageStore:
    """
    Persistent SQLite store to track already-notified messages.
    Prevents duplicate notifications across bot restarts or history catch-ups.
    """

    def __init__(self, db_path: Union[str, Path] = "teljobs.d/seen_messages.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS seen_messages (
                        channel_id TEXT NOT NULL,
                        message_id INTEGER NOT NULL,
                        matched_keyword TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (channel_id, message_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_seen_created 
                    ON seen_messages (created_at)
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize seen messages database: {e}")

    def is_seen(self, channel_id: Union[str, int], message_id: int) -> bool:
        """Check if this message has already been processed and notified."""
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT 1 FROM seen_messages WHERE channel_id = ? AND message_id = ?",
                    (str(channel_id), message_id),
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking seen status for {channel_id}:{message_id}: {e}")
            return False

    def mark_seen(
        self,
        channel_id: Union[str, int],
        message_id: int,
        matched_keyword: Optional[str] = None,
    ) -> None:
        """Mark a message as processed."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO seen_messages (channel_id, message_id, matched_keyword)
                    VALUES (?, ?, ?)
                    """,
                    (str(channel_id), message_id, matched_keyword or ""),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording seen status for {channel_id}:{message_id}: {e}")

    def prune_old_messages(self, days: int = 30) -> int:
        """Remove entries older than the given number of days to keep the database compact."""
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "DELETE FROM seen_messages WHERE created_at < datetime('now', ?)",
                    (f"-{days} days",),
                )
                deleted = cur.rowcount
                conn.commit()
                if deleted > 0:
                    logger.info(f"Pruned {deleted} old records from seen messages database.")
                return deleted
        except Exception as e:
            logger.error(f"Error pruning old messages: {e}")
            return 0
