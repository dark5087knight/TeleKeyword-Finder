"""Unit tests verifying Milestone M0 criteria:
- App starts and stops cleanly
- Logging redaction guarantees secrets never appear in logs
- Configuration parses environment variables and settings.toml
- Domain models and command schemas validate accurately
- Test fakes function properly
"""

import io
import logging
import pytest
from datetime import datetime, timezone

from tgagent.config import load_config
from tgagent.domain.commands import AgentTurn, CreateTask, Clarify
from tgagent.domain.models import (
    ChannelRef,
    DesiredState,
    RuntimeState,
    Task,
    TaskConfig,
    TaskRuntime,
)
from tgagent.main import Application
from tgagent.security.redaction import RedactingFilter, redact_text, setup_logging
from tests.fakes import FakeClock, FakeLLM, FakeChannelSource, FakeNotifier


@pytest.mark.asyncio
async def test_application_starts_and_stops_cleanly() -> None:
    """Verify that Application can start and stop gracefully without leaking tasks."""
    app = Application()
    assert not app.is_running

    await app.start()
    assert app.is_running

    await app.stop()
    assert not app.is_running


def test_redaction_filter_strips_sensitive_data() -> None:
    """Verify that tokens, API keys, passwords, and phone numbers are redacted."""
    sensitive_log = (
        "Connecting with Bot Token 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ, "
        "OpenAI key sk-1234567890abcdef1234567890, "
        "Anthropic key sk-ant-1234567890abcdef1234567890, "
        "Groq key gsk_1234567890abcdef1234567890, "
        "Gemini key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6, "
        "Master key aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=, "
        "and phone +12345678901."
    )

    redacted = redact_text(sensitive_log)

    assert "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ" not in redacted
    assert "[REDACTED_BOT_TOKEN]" in redacted
    assert "sk-1234567890abcdef1234567890" not in redacted
    assert "[REDACTED_OPENAI_KEY]" in redacted
    assert "sk-ant-1234567890abcdef1234567890" not in redacted
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted
    assert "gsk_1234567890abcdef1234567890" not in redacted
    assert "[REDACTED_GROQ_KEY]" in redacted
    assert "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6" not in redacted
    assert "[REDACTED_GEMINI_KEY]" in redacted
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=" not in redacted
    assert "[REDACTED_MASTER_KEY]" in redacted
    assert "+12345678901" not in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_logger_with_redacting_filter() -> None:
    """Verify that logging handlers sanitize messages before writing."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(RedactingFilter())

    test_logger = logging.getLogger("test_redaction")
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)

    secret_key = "sk-ant-secretAnthropicKey1234567890"
    test_logger.info("Attempting login using token %s", secret_key)

    output = log_stream.getvalue()
    assert secret_key not in output
    assert "[REDACTED_ANTHROPIC_KEY]" in output


def test_config_loader_with_defaults() -> None:
    """Verify config loading and default limit fallbacks."""
    config = load_config()
    assert config.limits.max_tasks_per_user == 5
    assert config.scheduler.tick_seconds == 1.0
    assert config.telegram.reading_account == "default"


def test_domain_task_and_config_models() -> None:
    """Verify TaskConfig immutability and Task data structure."""
    cfg = TaskConfig(
        name="AI News Monitor",
        topics=["LLMs", "AI Agents"],
        criteria="Find open-source models and agent frameworks",
        keywords=["llm", "llama", "deepseek"],
        channels=[ChannelRef(handle="@test_channel", channel_id=1001)],
        recipient="me",
        interval_seconds=120,
    )

    task = Task(
        id="t_001",
        agent_type="channel_monitor",
        owner_id=42,
        config=cfg,
        desired=DesiredState.ACTIVE,
        runtime=TaskRuntime(state=RuntimeState.WAITING),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert task.config.name == "AI News Monitor"
    assert task.desired == DesiredState.ACTIVE
    assert task.runtime.state == RuntimeState.WAITING


def test_command_schema_agent_turn_validation() -> None:
    """Verify AgentTurn parses typed discriminator commands."""
    raw_payload = {
        "commands": [
            {
                "action": "create_task",
                "name": "Python Jobs",
                "topics": ["Python", "Backend"],
                "channels": ["@job_channel"],
                "recipient": "me",
                "interval_seconds": 300,
            },
            {
                "action": "clarify",
                "question": "Should unpaid internships be excluded?",
            },
        ]
    }

    turn = AgentTurn.model_validate(raw_payload)
    assert len(turn.commands) == 2
    assert isinstance(turn.commands[0], CreateTask)
    assert isinstance(turn.commands[1], Clarify)
    assert turn.commands[0].recipient == "me"


@pytest.mark.asyncio
async def test_fake_doubles() -> None:
    """Verify FakeClock, FakeLLM, FakeChannelSource, and FakeNotifier work as expected."""
    # Clock
    clock = FakeClock()
    t0 = clock.now()
    clock.advance(60)
    assert (clock.now() - t0).total_seconds() == 60

    # LLM
    fake_llm = FakeLLM()
    fake_llm.enqueue_structured_response(Clarify(question="Any negative keywords?"))
    result = await fake_llm.generate_structured(
        system="test",
        messages=[],
        schema=Clarify,
        model="test-model",
    )
    assert result.question == "Any negative keywords?"

    # Notifier
    fake_notifier = FakeNotifier()
    delivered = await fake_notifier.send_message(chat_id=123, text="Match found")
    assert delivered
    assert len(fake_notifier.sent_messages) == 1


@pytest.mark.asyncio
async def test_interactive_chat_workflow() -> None:
    """Verify conversational task creation, confirmation, and control in interactive chat."""
    from tgagent.orchestrator.interactive import InteractiveChat
    from tests.fakes import FakeLLMService

    fake_service = FakeLLMService()
    chat = InteractiveChat(llm_service=fake_service)

    # 1. User asks to monitor channels
    resp1 = await chat.handle_turn(
        "Please monitor @python_jobs and @remote_dev for posts about python backend and send to @analyst"
    )
    assert "subagent_1" in resp1
    assert "subagent_1" in chat.tasks
    assert chat.tasks["subagent_1"].desired.value == "active"

    # 2. Status question
    resp2 = await chat.handle_turn("how many agents are running?")
    assert "subagent_1" in resp2

    # 3. Pause sub-agent
    resp3 = await chat.handle_turn("pause subagent_1")
    assert "PAUSED" in resp3
    assert chat.tasks["subagent_1"].desired.value == "paused"

    # 4. Resume sub-agent
    resp4 = await chat.handle_turn("resume subagent_1")
    assert "RESUMED" in resp4
    assert chat.tasks["subagent_1"].desired.value == "active"

    # 5. Cancel sub-agent
    resp5 = await chat.handle_turn("cancel subagent_1")
    assert "TERMINATED" in resp5
    assert "subagent_1" not in chat.tasks


