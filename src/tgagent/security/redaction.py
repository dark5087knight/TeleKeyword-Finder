"""Logging redaction filter to ensure sensitive credentials never appear in logs.

Strips:
- Telegram Bot API tokens
- Telegram API Hashes
- Fernet Master keys
- LLM API keys (OpenAI, Anthropic, Groq, Gemini)
- Phone numbers
"""

import logging
import re
from typing import Any

# Regex patterns for common sensitive tokens (specific before general)
REDACTION_PATTERNS = [
    # Telegram Bot Token (e.g. 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ)
    (re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,45}\b"), "[REDACTED_BOT_TOKEN]"),
    # Anthropic API Key (sk-ant-...) - MUST be before generic sk-
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_ANTHROPIC_KEY]"),
    # Groq API Key (gsk_...)
    (re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"), "[REDACTED_GROQ_KEY]"),
    # Google AI / Gemini API Key (AIzaSy...)
    (re.compile(r"\bAIzaSy[A-Za-z0-9_-]{25,45}\b"), "[REDACTED_GEMINI_KEY]"),
    # OpenAI API Key (sk-...)
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_OPENAI_KEY]"),
    # Generic Bearer Token
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE), r"\1[REDACTED_BEARER]"),
    # Fernet Master Key (44 characters ending in =)
    (re.compile(r"\b[A-Za-z0-9_-]{42,44}={0,2}\b"), "[REDACTED_MASTER_KEY]"),
    # Phone numbers in international format (e.g. +12345678901)
    (re.compile(r"\+\d{1,4}[-.\s]?\d{6,14}\b"), "[REDACTED_PHONE]"),
]


def redact_text(text: str) -> str:
    """Apply all redaction patterns to a string."""
    sanitized = text
    for pattern, replacement in REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFilter(logging.Filter):
    """Logging filter that sanitizes message contents and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_text(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with redaction filter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Avoid duplicate handlers if reconfigured
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.addFilter(RedactingFilter())
