"""Test doubles and fakes for testing without real Telegram or LLM connections."""

from datetime import datetime, timezone, timedelta
from typing import Any, TypeVar
from pydantic import BaseModel

from tgagent.domain.models import DiscoveredPost

T = TypeVar("T", bound=BaseModel)


class FakeClock:
    """Controllable virtual clock for deterministic time testing."""

    def __init__(self, start_time: datetime | None = None) -> None:
        self._current = start_time or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current += timedelta(seconds=seconds)


class FakeLLM:
    """Fake LLM Provider for unit testing."""

    def __init__(self) -> None:
        self.call_history: list[dict[str, Any]] = []
        self.structured_responses: list[Any] = []
        self.text_responses: list[str] = []
        self.should_fail_auth: bool = False
        self.should_rate_limit: bool = False

    def enqueue_structured_response(self, response: Any) -> None:
        self.structured_responses.append(response)

    def enqueue_text_response(self, response: str) -> None:
        self.text_responses.append(response)

    async def generate_structured(
        self,
        *,
        system: str,
        messages: list[Any],
        schema: type[T],
        model: str,
        options: Any = None,
    ) -> T:
        self.call_history.append({
            "type": "structured",
            "system": system,
            "messages": messages,
            "schema": schema,
            "model": model,
        })
        if self.should_fail_auth:
            from tgagent.domain.errors import LLMAuthError
            raise LLMAuthError("Invalid API key")
        if self.should_rate_limit:
            from tgagent.domain.errors import LLMRateLimited
            raise LLMRateLimited(retry_after=30)

        if not self.structured_responses:
            raise RuntimeError("No fake structured response queued")

        resp = self.structured_responses.pop(0)
        if isinstance(resp, schema):
            return resp
        if isinstance(resp, dict):
            return schema(**resp)
        return resp

    async def generate_text(
        self,
        *,
        system: str,
        messages: list[Any],
        model: str,
        options: Any = None,
    ) -> str:
        self.call_history.append({
            "type": "text",
            "system": system,
            "messages": messages,
            "model": model,
        })
        if not self.text_responses:
            return "Fake default text response"
        return self.text_responses.pop(0)

    async def validate_credentials(self, model: str) -> None:
        if self.should_fail_auth:
            from tgagent.domain.errors import LLMAuthError
            raise LLMAuthError("Invalid API key")


class FakeChannelSource:
    """Fake Telegram channel reader for testing post discovery."""

    def __init__(self) -> None:
        self.posts_by_channel: dict[int, list[DiscoveredPost]] = {}
        self.fetch_calls: list[dict[str, Any]] = []

    def seed_posts(self, channel_id: int, posts: list[DiscoveredPost]) -> None:
        self.posts_by_channel[channel_id] = posts

    async def fetch_new_posts(
        self,
        channel_id: int,
        min_id: int = 0,
        limit: int = 100,
    ) -> list[DiscoveredPost]:
        self.fetch_calls.append({"channel_id": channel_id, "min_id": min_id, "limit": limit})
        all_posts = self.posts_by_channel.get(channel_id, [])
        return [p for p in all_posts if p.message_id > min_id][:limit]


class FakeNotifier:
    """Fake Telegram Bot notifier for testing deliveries."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.should_fail: bool = False

    async def send_message(
        self,
        chat_id: int,
        text: str,
        permalink: str | None = None,
    ) -> bool:
        if self.should_fail:
            return False
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "permalink": permalink,
        })
        return True


class FakeLLMService:
    """Fake LLM Service for deterministic interactive chat testing."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses: list[str] = responses or []
        self.call_history: list[dict[str, Any]] = []

    async def chat_turn(
        self,
        conversation_history: list[dict[str, str]],
        active_tasks_summary: str,
    ) -> str:
        self.call_history.append({
            "history": conversation_history,
            "summary": active_tasks_summary,
        })
        if self.responses:
            return self.responses.pop(0)

        last_user = conversation_history[-1]["content"] if conversation_history else ""
        if "monitor" in last_user.lower():
            return (
                "Understood. I will monitor these channels for you.\n"
                "ACTION: CREATE_TASK\n"
                "CHANNELS: @python_jobs, @remote_dev\n"
                "TOPICS: python backend\n"
                "RECIPIENT: @analyst"
            )
        if "pause" in last_user.lower():
            return "I am pausing the task.\nACTION: PAUSE_TASK subagent_1"
        if "resume" in last_user.lower():
            return "Resuming the task.\nACTION: RESUME_TASK subagent_1"
        if "cancel" in last_user.lower():
            return "Cancelling task.\nACTION: CANCEL_TASK subagent_1"
        if "list" in last_user.lower() or "how many" in last_user.lower():
            return f"Here is the status:\n{active_tasks_summary}"
        return f"Upper Agent conversational response to: {last_user}"

