import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class KeywordMatcher:
    """
    High-performance, pre-compiled keyword matcher supporting:
    - Case-insensitive whole-word matching
    - Multi-language / Unicode support (English, Arabic, Russian, etc.)
    - Special symbols (e.g. C++, C#, .NET, Node.js) without regex boundary breakage
    - Exclusion keywords (negative filtering / spam blacklist)
    """

    def __init__(self, keywords: List[str], exclude_keywords: Optional[List[str]] = None):
        self.keywords = [k.strip() for k in keywords if k.strip()]
        self.exclude_keywords = [k.strip() for k in (exclude_keywords or []) if k.strip()]

        self._compiled_keywords: List[Tuple[str, re.Pattern]] = [
            (kw, self._compile_pattern(kw)) for kw in self.keywords
        ]
        self._compiled_excludes: List[Tuple[str, re.Pattern]] = [
            (kw, self._compile_pattern(kw)) for kw in self.exclude_keywords
        ]

        logger.debug(
            f"KeywordMatcher initialized with {len(self._compiled_keywords)} keywords and "
            f"{len(self._compiled_excludes)} exclusion keywords."
        )

    @staticmethod
    def _compile_pattern(keyword: str) -> re.Pattern:
        """
        Builds an optimized regex with context-sensitive boundary lookarounds.
        """
        escaped = re.escape(keyword)
        first_char = keyword[:1]
        last_char = keyword[-1:]

        # Left boundary
        if re.match(r"\w", first_char):
            left = r"(?<!\w)"
        elif first_char in (".", "/"):
            left = r"(?<![.\w])"
        else:
            left = r"(?<!\S)"

        # Right boundary
        if re.match(r"\w", last_char):
            right = r"(?!\w)"
        elif last_char in ("+", "#"):
            right = r"(?![#+\w])"
        else:
            right = r"(?!\w)"

        return re.compile(rf"{left}{escaped}{right}", re.IGNORECASE)

    def is_excluded(self, text: str) -> Optional[str]:
        """
        Check if text matches any exclusion keyword.
        Returns the matched exclusion keyword or None.
        """
        if not text or not self._compiled_excludes:
            return None

        for kw, pattern in self._compiled_excludes:
            if pattern.search(text):
                return kw
        return None

    def find_all_matches(self, text: str) -> List[str]:
        """
        Find all matched keywords in the text.
        Returns an empty list if the text matches an exclusion keyword or has no matches.
        """
        if not text:
            return []

        excluded = self.is_excluded(text)
        if excluded:
            logger.debug(f"Message ignored due to exclusion keyword: '{excluded}'")
            return []

        matches: List[str] = []
        for kw, pattern in self._compiled_keywords:
            if pattern.search(text):
                matches.append(kw)
        return matches

    def match(self, text: str) -> Optional[str]:
        """
        Returns the first matched keyword in the text, or None if no match or excluded.
        """
        matches = self.find_all_matches(text)
        return matches[0] if matches else None
