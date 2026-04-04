"""
Central registry mapping tool names to callables and Gemini JSON schemas.
"""

from __future__ import annotations

from typing import Any

from exceptions import ToolNotFoundError
from logger import get_logger

logger = get_logger(__name__)


def _get_registry() -> dict[str, Any]:
    """
    Lazy import tool functions to avoid early circular imports.
    """
    from tools.calendar_manager import check_duplicate, create_event, send_invite
    from tools.coordination_memory import find_overlap, rank_slots, track_participant_slots
    from tools.email_coordinator import (
        classify,
        detect_ambiguity,
        get_thread_history,
        parse_availability,
        send_reply,
    )
    from tools.thread_intelligence import (
        detect_cancellation,
        get_scheduling_status,
        summarise_thread,
        suggest_optimal_time,
    )

    return {
        "classify": classify,
        "parse_availability": parse_availability,
        "detect_ambiguity": detect_ambiguity,
        "get_thread_history": get_thread_history,
        "send_reply": send_reply,
        "check_duplicate": check_duplicate,
        "create_event": create_event,
        "send_invite": send_invite,
        "track_participant_slots": track_participant_slots,
        "find_overlap": find_overlap,
        "rank_slots": rank_slots,
        "summarise_thread": summarise_thread,
        "get_scheduling_status": get_scheduling_status,
        "detect_cancellation": detect_cancellation,
        "suggest_optimal_time": suggest_optimal_time,
    }


def call_tool(name: str, args: dict) -> Any:
    """
    Dispatch tool call by name with keyword arguments.
    """
    registry = _get_registry()
    if name not in registry:
        raise ToolNotFoundError(
            f"Tool '{name}' not found in registry. Available tools: {sorted(registry.keys())}"
        )

    logger.debug("Dispatching tool '%s' with args: %s", name, args)
    return registry[name](**args)


def get_schema(name: str) -> dict[str, Any]:
    """
    Return schema for one tool by function name.
    """
    for schema in ALL_TOOL_SCHEMAS:
        if schema["function"]["name"] == name:
            return schema
    raise ToolNotFoundError(f"No schema found for tool '{name}'.")


ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "classify",
            "description": "Classify email intent and confidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "Email body text."},
                    "subject": {"type": "string", "description": "Email subject line."},
                    "intent": {
                        "type": "string",
                        "enum": ["scheduling", "update_request", "reschedule", "cancellation", "noise"],
                        "description": "Intent label selected by the model.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score from 0.0 to 1.0.",
                    },
                },
                "required": ["body", "subject", "intent", "confidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_availability",
            "description": "Extract UTC availability slots from free-form text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Availability text."},
                    "sender_tz": {
                        "type": "string",
                        "description": "Sender IANA timezone, for example Asia/Kolkata.",
                        "default": "UTC",
                    },
                },
                "required": ["text", "sender_tz"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_ambiguity",
            "description": "Detect whether availability text is too vague and generate one clarifying question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Availability text to evaluate."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_thread_history",
            "description": "Get stored message history for a thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread/session identifier."}
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_reply",
            "description": "Send a reply email through SMTP sender.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Primary recipient email."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Reply body without disclaimer."},
                    "thread_id": {"type": "string", "description": "Thread/session id."},
                    "in_reply_to": {
                        "type": "string",
                        "description": "Message-ID of email being replied to.",
                        "default": "",
                    },
                    "references": {
                        "type": "string",
                        "description": "References header chain.",
                        "default": "",
                    },
                    "cc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional cc recipients.",
                    },
                },
                "required": ["to", "subject", "body", "thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_duplicate",
            "description": "Check for duplicate calendar events before creating one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_utc": {"type": "string", "description": "Event start datetime in UTC ISO format."},
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Participant attendee emails.",
                    },
                },
                "required": ["title", "start_utc", "participants"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a calendar event and send attendee updates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_utc": {"type": "string", "description": "UTC start datetime ISO."},
                    "end_utc": {"type": "string", "description": "UTC end datetime ISO."},
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Attendee email addresses.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description.",
                        "default": "",
                    },
                },
                "required": ["title", "start_utc", "end_utc", "participants"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_invite",
            "description": "Ensure participants are invited to an existing event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Calendar event id."},
                    "participants": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Emails to invite.",
                    },
                },
                "required": ["event_id", "participants"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_participant_slots",
            "description": "Persist parsed slots for a participant in session state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread/session id."},
                    "email": {"type": "string", "description": "Participant email address."},
                    "slots": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of participant slot objects in UTC.",
                    },
                },
                "required": ["thread_id", "email", "slots"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_overlap",
            "description": "Find candidate slots that satisfy attendance threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread/session id."}
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_slots",
            "description": "Rank candidate slots with weighted deterministic scoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_slots": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Candidate overlap slot objects.",
                    },
                    "preferences": {
                        "type": "object",
                        "description": "Participant preference profile mapping keyed by email.",
                        "additionalProperties": {"type": "object"},
                    },
                },
                "required": ["candidate_slots", "preferences"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarise_thread",
            "description": "Summarise full thread history into concise status text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread/session id."}
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scheduling_status",
            "description": "Get machine-readable scheduling status snapshot for a thread.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Thread/session id."}
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_cancellation",
            "description": "Detect cancellation intent from an email body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "body": {"type": "string", "description": "Email body text."}
                },
                "required": ["body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_optimal_time",
            "description": "Suggest preferred hour/day buckets from historical accepted slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Participant email address."}
                },
                "required": ["email"],
            },
        },
    },
]
