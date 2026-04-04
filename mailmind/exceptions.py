"""All custom exceptions for MailMind."""


class MailMindBaseError(Exception):
    """Base class for all MailMind exceptions."""


class ConfigurationError(MailMindBaseError):
    """Raised when required configuration is missing or invalid."""


class IMAPConnectionError(MailMindBaseError):
    """Raised when IMAP connect/auth fails."""


class EmailParseError(MailMindBaseError):
    """Raised when a MIME email cannot be parsed to EmailObject."""


class SMTPConnectionError(MailMindBaseError):
    """Raised when SMTP connect/send fails."""


class SessionNotFoundError(MailMindBaseError):
    """Raised when no saved state exists for a thread id."""


class CheckpointError(MailMindBaseError):
    """Raised when saving state to SQLite fails."""


class OpenRouterAPIError(MailMindBaseError):
    """Raised when OpenRouter API calls fail after retries."""


class LowConfidenceError(MailMindBaseError):
    """Raised when LLM confidence is below configured threshold."""


class ToolNotFoundError(MailMindBaseError):
    """Raised when an unknown tool name is requested."""


class CalendarAuthError(MailMindBaseError):
    """Raised when Google Calendar OAuth/refresh fails."""


class CalendarAPIError(MailMindBaseError):
    """Raised when Calendar API requests fail."""


class DuplicateEventError(MailMindBaseError):
    """Raised when an equivalent calendar event already exists."""


class NodeExecutionError(MailMindBaseError):
    """Raised when an agent node raises an unhandled exception."""


class InvalidStateTransitionError(MailMindBaseError):
    """Raised when router returns an undefined next node."""
