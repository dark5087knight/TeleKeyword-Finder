"""LLM Service connecting to providers (Groq, OpenAI, Gemini, Anthropic, Ollama).

Powers the Upper Agent's conversational intelligence and Sub-Agent semantic post evaluation.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from groq import AsyncGroq
from tgagent.config import AppConfig

logger = logging.getLogger("tgagent.llm")


SYSTEM_PROMPT_TEMPLATE = """You are the Upper Agent of TeleKeyword Finder.
You are the central coordinator that converses directly with the user to manage Telegram channel monitoring tasks.
You orchestrate Sub-Agents. Each Sub-Agent is a worker responsible for monitoring specific Telegram channels and comparing new posts against the user's explanation to forward matches to a Telegram recipient.

CURRENT SYSTEM STATE:
{active_tasks_summary}

RULES & INSTRUCTIONS:
1. NEVER use any emojis under any circumstances. Keep output clean and professional.
2. You can chat freely and naturally. Greet the user, answer questions, provide advice, or explain how the system works.
3. If the user asks if there are running tasks or sub-agents, answer based on the CURRENT SYSTEM STATE above.
4. When the user wants to monitor channels:
   - The user will explain or describe what they want to track in natural language (for example: "job ads about software engineering and IT roles").
   - IMPORTANT: DO NOT ASK THE USER FOR SPECIFIC KEYWORDS! The system uses semantic LLM evaluation to compare posts against the user's explanation directly.
   - When you have the channels, the user's explanation of what to track, and the recipient:
     Confirm that you understand their explanation and output the following action block at the end of your response:
     ACTION: CREATE_TASK
     CHANNELS: @channel1, @channel2
     CRITERIA: <full explanation of what the user wants to track>
     RECIPIENT: @username
5. When the user wants to pause, resume, or cancel a sub-agent:
   - If the task exists in the state, confirm and output:
     ACTION: PAUSE_TASK <task_id>
     or
     ACTION: RESUME_TASK <task_id>
     or
     ACTION: CANCEL_TASK <task_id>
6. If the user asks to list tasks, summarize them and optionally output:
     ACTION: LIST_TASKS
"""


class LLMService:
    """Async service managing LLM provider calls for chat and semantic post evaluation."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._groq_client: AsyncGroq | None = None
        self._init_client()

    def _init_client(self) -> None:
        api_key = self.config.llm.api_key or os.getenv("GROQ_API_TOKEN", "")
        if self.config.llm.provider == "groq" and api_key:
            self._groq_client = AsyncGroq(api_key=api_key)

    async def chat_turn(
        self,
        conversation_history: list[dict[str, str]],
        active_tasks_summary: str,
    ) -> str:
        """Send conversation history to the LLM and return the assistant response."""
        system_content = SYSTEM_PROMPT_TEMPLATE.format(
            active_tasks_summary=active_tasks_summary.strip() or "No active sub-agents currently running."
        )

        messages = [{"role": "system", "content": system_content}]
        messages.extend(conversation_history)

        model = self.config.llm.control_model or "qwen/qwen3.8-27b"

        if self._groq_client:
            try:
                response = await self._groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.3,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.error("Error calling Groq API: %s", e)
                return f"Error communicating with LLM ({type(e).__name__}): {e}"

        return "LLM provider is not configured. Please check your LLM_API_KEY / GROQ_API_TOKEN in .env."

    async def evaluate_post_relevance(
        self,
        criteria: str,
        post_text: str,
    ) -> tuple[bool, str]:
        """Semantically compare a channel post against the user's natural language criteria."""
        if not post_text or not post_text.strip():
            return False, "Empty post"

        if not self._groq_client:
            # Fallback if no LLM: simple keyword overlap
            words = [w.lower() for w in criteria.split() if len(w) > 3]
            post_lower = post_text.lower()
            matches = [w for w in words if w in post_lower]
            if matches:
                return True, f"Matched keyword(s): {', '.join(matches)}"
            return False, "No keyword overlap"

        prompt = (
            f"Evaluate if this Telegram channel post matches the user's monitoring criteria.\n\n"
            f"User Criteria: {criteria}\n\n"
            f"Post Content:\n{post_text[:1500]}\n\n"
            f"Output format:\n"
            f"MATCH: YES or NO\n"
            f"REASON: brief one-sentence explanation."
        )

        model = self.config.llm.classifier_model or self.config.llm.control_model or "qwen/qwen3.8-27b"

        try:
            response = await self._groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or ""
            is_match = "MATCH: YES" in raw.upper() or "MATCH:YES" in raw.upper()

            reason = "Relevant to user criteria"
            reason_match = re.search(r"REASON:\s*(.+)", raw, re.IGNORECASE)
            if reason_match:
                reason = reason_match.group(1).strip()

            return is_match, reason

        except Exception as e:
            logger.error("Error evaluating post with LLM: %s", e)
            # Fallback to keyword matching if LLM fails
            words = [w.lower() for w in criteria.split() if len(w) > 3]
            post_lower = post_text.lower()
            matches = [w for w in words if w in post_lower]
            if matches:
                return True, f"Fallback match: {', '.join(matches)}"
            return False, f"Evaluation error: {e}"
