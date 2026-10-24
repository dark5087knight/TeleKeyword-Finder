"""Semantic analysis and keyword matching tools for Telegram posts."""

from __future__ import annotations

import json
import logging
import re
from typing import Set

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from tgagent.domain.schemas import PostEvaluationResult

logger = logging.getLogger("tgagent.tools.analysis")

# Common expansions for IT / software engineering roles and terms
COMMON_EXPANSIONS: dict[str, list[str]] = {
    "software": ["software", "developer", "engineer", "dev", "برمجة", "مطور", "مهندس"],
    "it": ["it", "information technology", "tech", "تقنية", "تكنولوجيا", "حاسوب"],
    "backend": ["backend", "python", "php", "laravel", "rust", "go", "node", "sql", "database"],
    "frontend": ["frontend", "react", "vue", "angular", "flutter", "mobile"],
    "ai": ["ai", "machine learning", "ml", "deep learning", "nlp", "llm", "ذكاء اصطناعي"],
    "security": ["security", "cyber", "infosec", "pentest", "أمن سيبراني"],
}


def make_analysis_tools(classifier_model: BaseChatModel) -> list[BaseTool]:
    """Create post analysis tools bound to a classifier ChatModel."""

    @tool
    async def evaluate_post_relevance(criteria: str, post_text: str) -> str:
        """Semantically evaluate whether a Telegram post matches the user's monitoring criteria.

        Args:
            criteria: Natural language explanation of what to monitor for.
            post_text: The full text content of the channel post.
        """
        clean_text = (post_text or "").strip()
        if not clean_text:
            return json.dumps({
                "is_relevant": False,
                "confidence": 0.0,
                "reason": "Post content is empty.",
            })

        prompt = (
            "You are an expert content verification system. Strictly evaluate whether this Telegram post genuinely satisfies the user's monitoring intent.\n\n"
            f"User Monitoring Criteria:\n{criteria}\n\n"
            f"Post Text:\n{clean_text[:1500]}\n\n"
            "RULES:\n"
            "1. SUBSTANCE OVER KEYWORDS: Merely mentioning keywords or laughter ('joke', 'hahaha', 'job') without genuine content is NOT a match.\n"
            "2. CHATTER & REACTIONS: One-word posts, greetings, or reactions are NEVER matches.\n"
            "3. ALL CONSTRAINTS: All criteria conditions (e.g. topic + location) must be genuinely satisfied together.\n"
            "Return whether it is relevant, confidence (0.0 to 1.0), and a concise reason."
        )

        try:
            structured_llm = classifier_model.with_structured_output(PostEvaluationResult)
            result: PostEvaluationResult = await structured_llm.ainvoke([("user", prompt)])
            return json.dumps({
                "is_relevant": result.is_relevant,
                "confidence": result.confidence,
                "reason": result.reason,
            })
        except Exception as exc:
            logger.warning("Structured output failed in evaluate_post_relevance, attempting raw invoke: %s", exc)
            try:
                # Fallback to direct prompt invoke
                raw_res = await classifier_model.ainvoke([("user", prompt + "\nAnswer format: MATCH: YES/NO\nCONFIDENCE: 0.0-1.0\nREASON: text")])
                content = str(raw_res.content)
                is_match = "MATCH: YES" in content.upper()
                reason = "Relevant to criteria" if is_match else "Not relevant"
                m_reason = re.search(r"REASON:\s*(.+)", content, re.IGNORECASE)
                if m_reason:
                    reason = m_reason.group(1).strip()
                return json.dumps({
                    "is_relevant": is_match,
                    "confidence": 0.8 if is_match else 0.2,
                    "reason": reason,
                })
            except Exception as e2:
                # Keyword fallback
                words = [w.lower() for w in criteria.split() if len(w) > 3]
                post_lower = clean_text.lower()
                matches = [w for w in words if w in post_lower]
                return json.dumps({
                    "is_relevant": len(matches) > 0,
                    "confidence": 0.5 if len(matches) > 0 else 0.0,
                    "reason": f"Fallback matched: {', '.join(matches)}" if matches else f"Evaluation error: {e2}",
                })

    @tool
    async def batch_evaluate_posts(criteria: str, posts: list[str]) -> str:
        """Evaluate multiple Telegram posts against monitoring criteria.

        Args:
            criteria: Natural language explanation of what to monitor for.
            posts: List of post text strings to evaluate.
        """
        results = []
        for idx, post in enumerate(posts[:10]):
            res_str = await evaluate_post_relevance.ainvoke({"criteria": criteria, "post_text": post})
            try:
                data = json.loads(res_str)
                data["post_index"] = idx
                results.append(data)
            except Exception:
                results.append({"post_index": idx, "is_relevant": False, "reason": res_str})

        relevant_count = sum(1 for r in results if r.get("is_relevant"))
        summary = {
            "total_evaluated": len(results),
            "relevant_count": relevant_count,
            "results": results,
        }
        return json.dumps(summary, indent=2)

    @tool
    def keyword_prefilter(topics: list[str], post_text: str) -> str:
        """Fast regex/keyword pre-filter for broad topics with auto-expansion for IT/tech terms.

        Args:
            topics: List of topics or keywords to check against.
            post_text: Text of the Telegram post.
        """
        if not post_text:
            return json.dumps({"matched": False, "matched_terms": []})

        terms: Set[str] = set()
        for topic in topics:
            cleaned = topic.strip().lower()
            if not cleaned:
                continue
            terms.add(cleaned)
            for key, exp_list in COMMON_EXPANSIONS.items():
                if key in cleaned:
                    terms.update(exp_list)

        matched_terms = []
        for term in terms:
            escaped = re.escape(term)
            pattern = re.compile(rf"(?:\b|_){escaped}(?:\b|_)", re.IGNORECASE | re.UNICODE)
            if pattern.search(post_text):
                matched_terms.append(term)

        return json.dumps({
            "matched": len(matched_terms) > 0,
            "matched_terms": matched_terms,
        })

    return [
        evaluate_post_relevance,
        batch_evaluate_posts,
        keyword_prefilter,
    ]
