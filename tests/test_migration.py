"""Comprehensive test suite for the LangChain/LangGraph multi-agent migration."""

import asyncio
import json
import pytest

from tgagent.config import AppConfig, LLMConfig
from tgagent.domain.models import DesiredState, RuntimeState
from tgagent.domain.schemas import RouteDecision, PostEvaluationResult, TaskCreationInput
from tgagent.state.task_store import TaskStore
from tgagent.state.checkpointer import create_checkpointer
from tgagent.tools.task_tools import make_task_tools
from tgagent.tools.analysis_tools import make_analysis_tools, COMMON_EXPANSIONS
from tgagent.tools.delivery_tools import make_delivery_tools
from tgagent.agents.supervisor import build_supervisor
from tgagent.orchestrator.interactive import InteractiveChat
from tgagent.telegram.client import TelegramSessionManager
from langchain_core.language_models.fake_chat_models import FakeListChatModel


class BindableFakeChatModel(FakeListChatModel):
    """Fake model implementing bind_tools for testing sub-agents and supervisor."""
    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        return self


def test_task_store_lifecycle():
    """Verify TaskStore CRUD and formatting."""
    store = TaskStore()
    assert "No active" in store.format_summary()

    # Create
    task = store.create(
        channels=["@tech_jobs", "dev_channel"],
        criteria="Looking for remote Python backend positions",
        recipient="@recruiter",
        interval_seconds=180,
    )
    assert task.id == "subagent_1"
    assert task.desired == DesiredState.ACTIVE
    assert task.runtime.state == RuntimeState.RUNNING
    assert len(task.config.channels) == 2
    assert task.config.channels[0].handle == "@tech_jobs"
    assert task.config.channels[1].handle == "@dev_channel"

    # Status & Summary
    status = store.get_status("subagent_1")
    assert status is not None
    assert status["matched_count"] == 0

    store.record_match("subagent_1", "Senior Python engineer at Startup")
    status_updated = store.get_status("subagent_1")
    assert status_updated["matched_count"] == 1
    assert "Senior Python" in status_updated["recent_matches"][0]

    summary = store.format_summary()
    assert "subagent_1" in summary
    assert "@tech_jobs" in summary

    # Pause
    assert store.pause("subagent_1") is True
    assert store.get("subagent_1").desired == DesiredState.PAUSED

    # Resume
    assert store.resume("subagent_1") is True
    assert store.get("subagent_1").desired == DesiredState.ACTIVE

    # Cancel
    assert store.cancel("subagent_1") is True
    assert store.get("subagent_1") is None
    assert "No active" in store.format_summary()


@pytest.mark.asyncio
async def test_task_tools():
    """Verify tool factory binds to TaskStore and functions properly."""
    store = TaskStore()
    tools = make_task_tools(store)
    tool_map = {t.name: t for t in tools}

    assert "create_monitoring_task" in tool_map
    assert "list_active_tasks" in tool_map
    assert "pause_task" in tool_map
    assert "resume_task" in tool_map
    assert "cancel_task" in tool_map
    assert "get_task_status" in tool_map

    # Test create
    create_res = await tool_map["create_monitoring_task"].ainvoke({
        "channels": ["@python_jobs"],
        "criteria": "Django and FastAPI developer jobs",
        "recipient": "@developer",
        "interval_seconds": 120,
    })
    assert "created successfully" in create_res
    assert "subagent_1" in create_res

    # Test list
    list_res = await tool_map["list_active_tasks"].ainvoke({})
    assert "subagent_1" in list_res

    # Test status
    status_res = await tool_map["get_task_status"].ainvoke({"task_id": "subagent_1"})
    data = json.loads(status_res)
    assert data["task_id"] == "subagent_1"
    assert data["recipient"] == "@developer"

    # Test pause
    pause_res = await tool_map["pause_task"].ainvoke({"task_id": "subagent_1"})
    assert "PAUSED" in pause_res

    # Test resume
    resume_res = await tool_map["resume_task"].ainvoke({"task_id": "subagent_1"})
    assert "RESUMED" in resume_res

    # Test cancel
    cancel_res = await tool_map["cancel_task"].ainvoke({"task_id": "subagent_1"})
    assert "cancelled" in cancel_res


def test_keyword_prefilter():
    """Verify TopicMatcher logic ported into keyword_prefilter tool."""
    fake_model = BindableFakeChatModel(responses=[""])
    tools = make_analysis_tools(fake_model)
    prefilter = next(t for t in tools if t.name == "keyword_prefilter")

    # Direct match
    res1 = json.loads(prefilter.invoke({"topics": ["python"], "post_text": "We need a Python developer"}))
    assert res1["matched"] is True

    # Expansion match (software -> developer/engineer)
    res2 = json.loads(prefilter.invoke({"topics": ["software"], "post_text": "Hiring a lead engineer today"}))
    assert res2["matched"] is True

    # No match
    res3 = json.loads(prefilter.invoke({"topics": ["python"], "post_text": "Cooking recipe with tomatoes"}))
    assert res3["matched"] is False


@pytest.mark.asyncio
async def test_delivery_tools_format():
    """Verify format_post_notification without sending."""
    cfg = AppConfig()
    session_mgr = TelegramSessionManager(cfg)
    tools = make_delivery_tools(session_mgr)
    format_tool = next(t for t in tools if t.name == "format_post_notification")

    formatted = await format_tool.ainvoke({
        "channel_name": "Tech Jobs",
        "channel_handle": "@techjobs",
        "message_id": 1234,
        "post_text": "Senior Backend Developer needed. Remote.",
        "match_reason": "Matches Python backend criteria",
        "agent_name": "subagent_1",
    })

    assert "Agent: subagent_1" in formatted
    assert "Channel: Tech Jobs (@techjobs)" in formatted
    assert "https://t.me/techjobs/1234" in formatted
    assert "Senior Backend Developer needed" in formatted


def test_supervisor_compilation(monkeypatch):
    """Verify build_supervisor creates and compiles a valid LangGraph with all sub-agents."""
    cfg = AppConfig(
        llm=LLMConfig(provider="openai", api_key="test_key_for_compilation"),
    )
    store = TaskStore()
    session_mgr = TelegramSessionManager(cfg)

    from tgagent.llm import factory
    fake_model = BindableFakeChatModel(responses=["Hello user"])
    monkeypatch.setattr(factory, "create_chat_model", lambda *args, **kwargs: fake_model)
    monkeypatch.setattr(factory, "create_classifier_model", lambda *args, **kwargs: fake_model)

    graph = build_supervisor(cfg, store, session_mgr)
    assert graph is not None

    nodes = graph.nodes
    assert "supervisor" in nodes
    assert "task_manager" in nodes
    assert "channel_monitor" in nodes
    assert "post_analyst" in nodes
    assert "delivery" in nodes


def test_interactive_chat_initialization(monkeypatch):
    """Verify InteractiveChat instantiates supervisor and task store seamlessly."""
    cfg = AppConfig(
        llm=LLMConfig(provider="openai", api_key="test_key_for_compilation"),
    )
    from tgagent.llm import factory
    fake_model = BindableFakeChatModel(responses=["Hello user"])
    monkeypatch.setattr(factory, "create_chat_model", lambda *args, **kwargs: fake_model)
    monkeypatch.setattr(factory, "create_classifier_model", lambda *args, **kwargs: fake_model)

    chat = InteractiveChat(config=cfg)
    assert chat.task_store is not None
    assert chat.graph is not None
    assert chat.thread_id == "interactive_session"


def test_tool_registry():
    """Verify ToolRegistry groups and provisions tools correctly."""
    from tgagent.tools import ToolRegistry

    cfg = AppConfig()
    store = TaskStore()
    session_mgr = TelegramSessionManager(cfg)
    fake_model = BindableFakeChatModel(responses=[""])

    registry = ToolRegistry(
        task_store=store,
        session_mgr=session_mgr,
        classifier_model=fake_model,
    )

    task_tools = registry.get_task_tools()
    assert len(task_tools) == 6

    tg_tools = registry.get_telegram_tools()
    assert len(tg_tools) == 4

    analysis_tools = registry.get_analysis_tools()
    assert len(analysis_tools) == 3

    delivery_tools = registry.get_delivery_tools()
    assert len(delivery_tools) == 2

    all_tools = registry.get_all_tools()
    assert set(all_tools.keys()) == {"task_manager", "channel_monitor", "post_analyst", "delivery"}


def test_llm_factory_all_providers():
    """Verify create_chat_model and create_classifier_model work for all configured providers."""
    from tgagent.llm.factory import create_chat_model, create_classifier_model

    for provider in ["openai", "groq", "gemini", "anthropic", "ollama"]:
        cfg = AppConfig(llm=LLMConfig(provider=provider, api_key="sk-test-key-12345"))
        chat_model = create_chat_model(cfg)
        classifier_model = create_classifier_model(cfg)

        assert chat_model is not None
        assert classifier_model is not None


def test_domain_schemas_validation():
    """Verify Pydantic validation on domain schemas."""
    route = RouteDecision(
        next_agent="task_manager",
        reasoning="User wants to create a new task",
        context="channels: @ch1",
    )
    assert route.next_agent == "task_manager"

    eval_res = PostEvaluationResult(
        is_relevant=True,
        confidence=0.95,
        reason="Direct keyword and context match",
    )
    assert eval_res.is_relevant is True
    assert eval_res.confidence == 0.95

    task_input = TaskCreationInput(
        channels=["@jobs"],
        criteria="FastAPI developer",
        recipient="@alice",
        interval_seconds=120,
    )
    assert len(task_input.channels) == 1
    assert task_input.interval_seconds == 120


@pytest.mark.asyncio
async def test_batch_evaluate_posts_tool():
    """Verify batch_evaluate_posts tool runs multiple evaluations."""
    fake_model = BindableFakeChatModel(responses=["MATCH: YES\nCONFIDENCE: 0.9\nREASON: Matching python role"])
    tools = make_analysis_tools(fake_model)
    batch_tool = next(t for t in tools if t.name == "batch_evaluate_posts")

    res_str = await batch_tool.ainvoke({
        "criteria": "Looking for python jobs",
        "posts": ["Post 1: Python developer needed", "Post 2: Cooking recipe"],
    })
    res = json.loads(res_str)
    assert res["total_evaluated"] == 2
    assert "results" in res


@pytest.mark.asyncio
async def test_realtime_monitor_engine_evaluate():
    """Verify RealtimeMonitorEngine post evaluation with LLM and keyword matching on Arabic content."""
    from tgagent.telegram.monitor import RealtimeMonitorEngine

    fake_model = BindableFakeChatModel(responses=["MATCH: YES\nREASON: Contains airplane wordplay and joke punchline"])
    cfg = AppConfig()
    session_mgr = TelegramSessionManager(cfg)
    engine = RealtimeMonitorEngine(session_mgr=session_mgr, classifier_model=fake_model)

    arabic_post = "طيارة تطير وقعت ليش\nطير حطلها رجل"

    # Test LLM semantic match
    is_match, reason = await engine.evaluate_post(criteria="نكت وضحك", text=arabic_post)
    assert is_match is True
    assert "joke" in reason.lower() or "punchline" in reason.lower()

    # Test keyword fallback
    engine_no_llm = RealtimeMonitorEngine(session_mgr=session_mgr, classifier_model=None)
    is_kw_match, kw_reason = await engine_no_llm.evaluate_post(criteria="طيارة", text=arabic_post)
    assert is_kw_match is True
    assert "طيارة" in kw_reason

    # Test non-matching content
    is_nomatch, _ = await engine_no_llm.evaluate_post(criteria="وظائف بايثون", text=arabic_post)
    assert is_nomatch is False

