"""Post Analyst Sub-Agent for evaluating relevance of Telegram posts."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from tgagent.config import AppConfig
from tgagent.llm.factory import create_classifier_model
from tgagent.llm.prompts import POST_ANALYST_PROMPT
from tgagent.tools.analysis_tools import make_analysis_tools


def build_post_analyst_agent(config: AppConfig) -> CompiledStateGraph:
    """Build the Post Analyst sub-agent subgraph.

    Responsible for evaluating Telegram posts against monitoring criteria,
    running batch evaluations, and fast keyword pre-filtering.
    """
    model = create_classifier_model(config)
    tools = make_analysis_tools(model)

    return create_react_agent(
        model=model,
        tools=tools,
        name="post_analyst",
        prompt=POST_ANALYST_PROMPT,
    )
