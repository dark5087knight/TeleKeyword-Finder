"""Domain error types across all application layers."""


class TGAgentError(Exception):
    """Base exception for all tgagent domain errors."""


# ---------------------------------------------------------------------------
# Telegram & MTProto Errors
# ---------------------------------------------------------------------------

class TelegramError(TGAgentError):
    """Base error for Telegram operations."""


class FloodWaitWrapperError(TelegramError):
    """Wrapper for Telegram FloodWait error carrying a cooldown period."""
    def __init__(self, retry_after: int, message: str | None = None):
        self.retry_after = retry_after
        super().__init__(message or f"Telegram FloodWait: retry after {retry_after}s")


class ChannelInaccessibleError(TelegramError):
    """Channel is private, banned, or does not exist."""
    def __init__(self, channel_ref: str, reason: str = "Inaccessible"):
        self.channel_ref = channel_ref
        self.reason = reason
        super().__init__(f"Channel '{channel_ref}' is inaccessible: {reason}")


# ---------------------------------------------------------------------------
# LLM Taxonomy Errors
# ---------------------------------------------------------------------------

class LLMError(TGAgentError):
    """Base error for LLM service operations."""


class LLMAuthError(LLMError):
    """User LLM API key is invalid or revoked."""


class LLMRateLimited(LLMError):
    """Vendor quota or rate limit exceeded (HTTP 429)."""
    def __init__(self, retry_after: int = 60, message: str | None = None):
        self.retry_after = retry_after
        super().__init__(message or f"LLM rate limited: retry after {retry_after}s")


class LLMUnavailable(LLMError):
    """Vendor timeout or service unavailable (HTTP 5xx)."""


class LLMOutputInvalid(LLMError):
    """LLM response failed schema validation and repair retry."""


class LLMBudgetExceeded(LLMError):
    """User exceeded their daily LLM call budget."""


# ---------------------------------------------------------------------------
# Task & Orchestration Errors
# ---------------------------------------------------------------------------

class TaskNotFoundError(TGAgentError):
    """Task ID or reference does not exist."""


class UnauthorizedError(TGAgentError):
    """Operation requested by an unauthorized caller."""


class TaskStateError(TGAgentError):
    """Illegal state transition requested for a task."""


class RecipientNotFoundError(TGAgentError):
    """Recipient alias does not exist for the owner."""
