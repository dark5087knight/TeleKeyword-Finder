"""Smart keyword and topic matcher for evaluating post relevance."""

from __future__ import annotations

import re
from typing import List, Set


# Common expansions for IT / software engineering roles if broad topics are requested
COMMON_EXPANSIONS = {
    "software": ["software", "developer", "engineer", "dev", "برمجة", "مطور", "مهندس"],
    "it": ["it", "information technology", "tech", "تقنية", "تكنولوجيا", "حاسوب"],
    "backend": ["backend", "python", "php", "laravel", "rust", "go", "node", "sql", "database"],
    "frontend": ["frontend", "react", "vue", "angular", "flutter", "mobile"],
}


class TopicMatcher:
    """Evaluates whether a message matches the user's topics or keywords."""

    def __init__(self, raw_topics: list[str]) -> None:
        self.raw_topics = raw_topics
        self.patterns: list[re.Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        terms: Set[str] = set()
        for topic in self.raw_topics:
            cleaned = topic.strip().lower()
            if not cleaned:
                continue
            terms.add(cleaned)

            # Auto-expand if IT / software engineering related
            for key, exp_list in COMMON_EXPANSIONS.items():
                if key in cleaned:
                    terms.update(exp_list)

        for term in terms:
            # Escape regex specials except spaces
            escaped = re.escape(term)
            pattern = re.compile(rf"(?:\b|\b|_){escaped}(?:\b|\b|_)", re.IGNORECASE | re.UNICODE)
            self.patterns.append(pattern)

    def matches(self, text: str) -> list[str]:
        """Return list of matched terms found in text."""
        if not text:
            return []

        matched = []
        for pattern in self.patterns:
            if pattern.search(text):
                matched.append(pattern.pattern)

        return matched
