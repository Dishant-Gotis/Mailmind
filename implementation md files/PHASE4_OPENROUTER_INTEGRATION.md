# PHASE4_OPENROUTER_INTEGRATION.md
## Phase 4 — OpenRouter LLM Integration
**Covers:** `openrouter_client.py`, `tool_caller.py`, `prompt_builder.py`, confidence threshold logic, retry strategy, tool schema format, prompt templates per node
**Files documented:** `openrouter_client.py`, `tool_caller.py`, `prompt_builder.py`, `tests/test_tool_caller.py`

---

## Purpose

Phase 4 is the intelligence layer of MailMind. It wraps the OpenRouter (Qwen) API behind a clean, retrying client that every node in the agent state machine calls. The key architectural decision is that OpenRouter is accessed via the **OpenAI-compatible endpoint** — this means the `openai` Python SDK is used with a custom `base_url`, giving access to OpenRouter's function-calling (tool use) capability through a familiar API. This phase also implements the **confidence threshold** — a guard that prevents the agent from acting on low-confidence classifications. If OpenRouter is not sure what an email means, the system flags it to the operator rather than guessing. No agent node calls OpenRouter directly — they all go through the three modules documented here.

---

## Dependencies

- **Phase 1 complete:** `config.py` (`config.openrouter_api_key`, `config.openrouter_model`, `config.llm_confidence_threshold`), `exceptions.py` (`OpenRouterAPIError`, `LowConfidenceError`, `ToolNotFoundError`), `logger.py`
- **Phase 3 complete:** `models.py` with `AgentState` TypedDict — `prompt_builder.py` reads state fields
- **Phase 5 will import from this phase:** `tool_caller.py` is used by nodes in Phase 6; `tool_registry.py` (Phase 5) is dispatched from here
- **pip package required:** `openai==1.30.1` (already in `requirements.txt` from Phase 1)
- **OpenRouter OpenAI-compatible endpoint:** `https://openrouter.ai/api/v1`

---

## 1. openrouter_client.py — Complete Implementation

```python
# openrouter_client.py
"""
OpenRouter (Qwen) client using the OpenAI-compatible API endpoint.

Why OpenAI SDK with custom base_url:
    OpenRouter exposes an OpenAI-compatible REST API. Using the openai SDK means:
    - Structured tool calling (function calling) works out of the box
    - Retry and timeout logic from openai SDK is available
    - No need for the google-generativeai SDK or additional dependencies

Endpoint: https://openrouter.ai/api/v1
Auth:      X-Goog-Api-Key header (passed as api_key to OpenAI client)
"""

from __future__ import annotations

import time
from typing import Any, Optional

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from config import config
from exceptions import OpenRouterAPIError
from logger import get_logger

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_DELAY_SECONDS = 2.0     # First retry delay
BACKOFF_MULTIPLIER = 2.0        # Each retry doubles the delay: 2s, 4s, 8s

# Retryable error types — all others raise immediately
RETRYABLE_ERRORS = (APITimeoutError, RateLimitError)

# OpenRouter OpenAI-compatible base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default generation parameters
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.2   # Low temperature for deterministic classification outputs


# Module-level client singleton — created once, reused across all calls
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """
    Return the module-level OpenRouter OpenAI-compatible client.
    Created on first call, reused thereafter (singleton pattern).

    Returns:
        OpenAI: Configured client pointing at OpenRouter endpoint.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client


def call_llm(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Any:
    """
    Send a chat completion request to OpenRouter (Qwen) with retry logic.

    Args:
        messages:    List of message dicts in OpenAI format:
                     [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        tools:       Optional list of tool schema dicts in OpenAI function-calling format.
                     If provided, OpenRouter may return a tool_calls response instead of text.
        temperature: Sampling temperature. Use 0.2 for classification, 0.7 for rewriting.
        max_tokens:  Maximum tokens in the response.

    Returns:
        openai.types.chat.ChatCompletion: The raw completion response object.
        Callers extract .choices[0].message.content or .choices[0].message.tool_calls.

    Raises:
        OpenRouterAPIError: If all MAX_RETRIES attempts fail.
                        Callers should route to error_node on this exception.

    Retry strategy:
        Attempt 1: immediate
        Attempt 2: wait 2s after failure
        Attempt 3: wait 4s after failure
        Non-retryable errors (APIError, AuthenticationError): raise immediately.
    """
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": config.openrouter_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    last_exc: Optional[Exception] = None
    delay = INITIAL_DELAY_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(**kwargs)
            logger.debug("OpenRouter response received (attempt %d).", attempt)
            return response

        except RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                logger.warning(
                    "OpenRouter retryable error (attempt %d/%d): %s — retrying in %.1fs",
                    attempt, MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
                delay *= BACKOFF_MULTIPLIER
            else:
                logger.error("OpenRouter failed after %d attempts: %s", MAX_RETRIES, exc)

        except APIError as exc:
            # Non-retryable (auth failure, invalid request, quota exceeded permanently)
            raise OpenRouterAPIError(
                f"OpenRouter API error (non-retryable): {exc.status_code} — {exc.message}"
            ) from exc

        except Exception as exc:
            raise OpenRouterAPIError(f"Unexpected OpenRouter error: {exc}") from exc

    raise OpenRouterAPIError(
        f"OpenRouter failed after {MAX_RETRIES} retries. Last error: {last_exc}"
    ) from last_exc
```

---

## 2. tool_caller.py — Complete Implementation

```python
# tool_caller.py
"""
Dispatches OpenRouter tool calls to the tool registry and handles confidence checking.

Flow:
    1. Build messages + tool schemas
    2. Call OpenRouter via openrouter_client.call_llm()
    3. Parse response: tool call or plain text
    4. Check confidence if classification call
    5. Dispatch to tool_registry.call_tool(name, args)
    6. Return tool result

This module is the bridge between agent nodes and both OpenRouter AND the tool registry.
No agent node calls OpenRouter directly — they all go through call_with_tools() or call_for_text().
"""

from __future__ import annotations

import json
from typing import Any, Optional

from exceptions import OpenRouterAPIError, LowConfidenceError, ToolNotFoundError
from openrouter_client import call_llm
from logger import get_logger

logger = get_logger(__name__)

# Confidence key OpenRouter is instructed to include in classification responses
CONFIDENCE_KEY = "confidence"


def call_with_tools(
    messages: list[dict],
    tool_schemas: list[dict],
    thread_id: str = "",
    temperature: float = 0.2,
) -> dict[str, Any]:
    """
    Call OpenRouter with tool schemas and dispatch the returned tool call.

    Args:
        messages:      Full conversation history + current user message.
        tool_schemas:  List of OpenAI-format tool schema dicts (from tool_registry.get_schema()).
        thread_id:     Passed through for logging only.
        temperature:   Sampling temperature. Default 0.2 for tool calls.

    Returns:
        dict: The result returned by the dispatched tool function.
              Keys and values depend on which tool was called.

    Raises:
        OpenRouterAPIError:   If OpenRouter API call fails after retries.
        ToolNotFoundError: If OpenRouter returns a tool name not in TOOL_REGISTRY.
        LowConfidenceError: If response contains confidence below threshold.
    """
    response = call_llm(messages=messages, tools=tool_schemas, temperature=temperature)
    choice = response.choices[0]
    message = choice.message

    # Case 1: OpenRouter returned a tool call
    if message.tool_calls:
        tool_call = message.tool_calls[0]  # Always take the first tool call
        tool_name = tool_call.function.name
        try:
            tool_args: dict = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            raise OpenRouterAPIError(
                f"OpenRouter returned non-JSON tool arguments: {tool_call.function.arguments}"
            ) from exc

        logger.debug(
            "OpenRouter called tool '%s' with args: %s", tool_name, tool_args,
            extra={"thread_id": thread_id},
        )

        # Check confidence if present in tool args
        _check_confidence(tool_args, thread_id)

        # Dispatch to tool registry
        from tool_registry import call_tool
        return call_tool(tool_name, tool_args)

    # Case 2: OpenRouter returned plain text instead of a tool call
    # Parse the text for a JSON response if possible
    if message.content:
        return _parse_text_as_json(message.content, thread_id)

    raise OpenRouterAPIError("OpenRouter returned neither tool_calls nor text content.")


def call_for_text(
    messages: list[dict],
    thread_id: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Call OpenRouter for a plain text response (no tool calling).
    Used by: rewrite_node (email tone polishing), thread_intelligence_node (summarise).

    Args:
        messages:   Full message list.
        thread_id:  For logging.
        temperature: Higher temperature for creative/rewriting tasks.
        max_tokens:  Max tokens in response.

    Returns:
        str: The plain text content of OpenRouter's response.

    Raises:
        OpenRouterAPIError: If OpenRouter fails or returns no content.
    """
    response = call_llm(messages=messages, temperature=temperature, max_tokens=max_tokens)
    content = response.choices[0].message.content
    if not content:
        raise OpenRouterAPIError("OpenRouter returned empty content for text call.")
    logger.debug("OpenRouter text response received.", extra={"thread_id": thread_id})
    return content.strip()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _check_confidence(tool_args: dict, thread_id: str) -> None:
    """
    If the tool response contains a 'confidence' key, check it against the threshold.
    This is used for classification tools (e.g. classify() in email_coordinator).

    Args:
        tool_args:  The parsed tool arguments dict returned by OpenRouter.
        thread_id:  For logging.

    Raises:
        LowConfidenceError: If confidence < config.llm_confidence_threshold.
    """
    if CONFIDENCE_KEY not in tool_args:
        return  # Not a confidence-checked call

    from config import config
    confidence = float(tool_args[CONFIDENCE_KEY])
    if confidence < config.llm_confidence_threshold:
        logger.warning(
            "Low confidence classification: %.2f < %.2f threshold — flagging to operator.",
            confidence, config.llm_confidence_threshold,
            extra={"thread_id": thread_id},
        )
        raise LowConfidenceError(
            f"OpenRouter classification confidence {confidence:.2f} is below "
            f"threshold {config.llm_confidence_threshold}. Email flagged to operator."
        )


def _parse_text_as_json(text: str, thread_id: str) -> dict:
    """
    Attempt to parse a plain text OpenRouter response as JSON.
    Fallback when OpenRouter returns text instead of a structured tool call.

    Args:
        text:      Plain text OpenRouter response.
        thread_id: For logging.

    Returns:
        dict: Parsed JSON dict if text is valid JSON, else {"raw_text": text}.
    """
    try:
        # Strip markdown code fences if present: ```json ... ```
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1])
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "OpenRouter returned plain text instead of tool call — wrapping as raw_text.",
            extra={"thread_id": thread_id},
        )
        return {"raw_text": text}
```

---

## 3. OpenRouter Tool Schema Format

OpenRouter's OpenAI-compatible endpoint accepts tools in exactly the OpenAI function-calling format. Every tool in `tool_registry.py` (Phase 5) must have a schema in this exact shape:

```python
# Example: schema for classify() tool in email_coordinator
{
    "type": "function",
    "function": {
        "name": "classify",
        "description": (
            "Classify the intent of an inbound email. Returns the intent category "
            "and a confidence score between 0.0 and 1.0."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "body": {
                    "type": "string",
                    "description": "The plain-text body of the email."
                },
                "subject": {
                    "type": "string",
                    "description": "The subject line of the email."
                }
            },
            "required": ["body", "subject"]
        }
    }
}
```

```python
# Example: schema for rank_slots() — more complex, nested types
{
    "type": "function",
    "function": {
        "name": "rank_slots",
        "description": (
            "Score and rank a list of candidate time slots using weighted criteria. "
            "Returns the best slot with a human-readable reason string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_slots": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of TimeSlot dicts with start_utc and end_utc as ISO strings."
                },
                "preferences": {
                    "type": "object",
                    "description": "Mapping of participant email to their PreferenceProfile dict."
                }
            },
            "required": ["candidate_slots", "preferences"]
        }
    }
}
```

**Python type → JSON Schema type mapping:**

| Python Type | JSON Schema Type |
|---|---|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list[str]` | `{"type": "array", "items": {"type": "string"}}` |
| `list[dict]` | `{"type": "array", "items": {"type": "object"}}` |
| `dict` | `{"type": "object"}` |
| `Optional[str]` | `{"type": "string"}` (mark as not required) |

---

## 4. How to Parse a OpenRouter Tool Call Response

```python
# Exact structure of a OpenRouter tool call response (openai SDK object):

response = client.chat.completions.create(
    model="openrouter-2.0-flash",
    messages=[...],
    tools=[...],
    tool_choice="auto",
)

# Access pattern:
choice = response.choices[0]
message = choice.message

# If OpenRouter called a tool:
if message.tool_calls:
    tool_call = message.tool_calls[0]
    tool_name: str = tool_call.function.name          # e.g. "classify"
    args_json: str = tool_call.function.arguments     # e.g. '{"body": "...", "subject": "..."}'
    args: dict = json.loads(args_json)

# If OpenRouter returned text (no tool call):
if message.content:
    text: str = message.content
```

---

## 5. prompt_builder.py — Complete Implementation

```python
# prompt_builder.py
"""
Constructs system prompts and user messages for each agent node type.

Design principles:
    - System prompt is static per node type — describes the agent's role
    - User message injects dynamic context: email body, session state, participant list
    - History from AgentState is prepended to give OpenRouter full thread context
    - All prompts are designed to elicit structured tool calls, not free-form text

Usage in nodes:
    messages = prompt_builder.build_triage_prompt(email_obj, state)
    result = tool_caller.call_with_tools(messages, tool_schemas, thread_id=state["thread_id"])
"""

from __future__ import annotations

from models import AgentState, EmailObject


# ── System prompts (static per node type) ─────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
Your ONLY job right now is to classify the intent of an inbound email.
Classify into exactly one of these categories:
  - scheduling: The email is initiating, requesting, or accepting a meeting invitation.
  - update_request: The email is asking for a summary or status of an existing meeting/thread.
  - reschedule: The email is requesting to change the time of an already agreed meeting.
  - cancellation: The email is cancelling an existing meeting or coordination thread.
  - noise: The email is unrelated to scheduling (newsletters, spam, social messages, etc).
Return your classification using the classify tool.
Include a confidence score between 0.0 (wild guess) and 1.0 (certain).
Do not write any explanatory text outside the tool call."""

COORDINATION_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
Your job is to extract availability information from the email body provided.
Use the parse_availability tool to extract all mentioned time slots.
Convert all times to UTC. If no specific times are mentioned, use detect_ambiguity.
Do not infer or invent times. Only extract what is explicitly stated."""

AMBIGUITY_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
A participant replied with vague availability (e.g. "sometime next week", "mornings").
Use the detect_ambiguity tool to generate one specific clarifying question.
The question must ask for SPECIFIC dates and times, preferably in a given format:
"Could you share 2-3 specific times (e.g. Monday 10 Apr 10am–12pm IST)?"
Do not ask multiple questions. One clear, specific question only."""

REWRITE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
You have been given a draft email to review and polish.
Improve clarity and professionalism. Keep it concise (under 200 words).
Do not change any factual content: times, participant names, event title.
Do not add or remove the AI disclaimer — it is added separately.
Return ONLY the polished email body text. No markdown, no subject line."""

SUMMARISE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
You have been given the full history of an email thread.
Provide a concise summary (3-5 bullet points) of: who is involved, what meeting is being coordinated,
what times have been proposed, and what the current status is.
Return plain text only. No markdown headers."""

THREAD_INTELLIGENCE_SYSTEM_PROMPT = """You are MailMind, an autonomous AI scheduling assistant.
A participant has asked for a status update on this thread.
Using the thread history provided, summarise the current state of scheduling coordination.
Be factual and concise. Use the summarise_thread tool."""


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_triage_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for triage_node.

    Args:
        email_obj:  The inbound EmailObject being classified.
        state:      Current AgentState (used for history).

    Returns:
        list[dict]: Message list ready for call_with_tools().
    """
    messages = [{"role": "system", "content": TRIAGE_SYSTEM_PROMPT}]
    messages.extend(state.get("history", []))
    messages.append({
        "role": "user",
        "content": (
            f"From: {email_obj['sender_name']} <{email_obj['sender_email']}>\n"
            f"Subject: {email_obj['subject']}\n\n"
            f"{email_obj['body']}"
        ),
    })
    return messages


def build_coordination_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for coordination_node.
    Includes participant list and pending responses for context.

    Args:
        email_obj:  The current inbound email to extract availability from.
        state:      Current AgentState.

    Returns:
        list[dict]: Message list for call_with_tools().
    """
    participants_str = ", ".join(state.get("participants", []))
    pending_str = ", ".join(state.get("pending_responses", [])) or "none"

    messages = [{"role": "system", "content": COORDINATION_SYSTEM_PROMPT}]
    messages.extend(state.get("history", []))
    messages.append({
        "role": "user",
        "content": (
            f"Participants: {participants_str}\n"
            f"Still waiting for: {pending_str}\n\n"
            f"Email from {email_obj['sender_email']}:\n"
            f"{email_obj['body']}"
        ),
    })
    return messages


def build_ambiguity_prompt(email_obj: EmailObject, state: AgentState) -> list[dict]:
    """
    Build the message list for ambiguity_node.

    Args:
        email_obj:  The email with vague availability.
        state:      Current AgentState.

    Returns:
        list[dict]: Message list for call_with_tools().
    """
    rounds = state.get("ambiguity_rounds", {}).get(email_obj["sender_email"], 0)
    escalation_note = ""
    if rounds >= 1:
        escalation_note = (
            "\nThis is the second clarification attempt. "
            "Be more explicit — ask for times in this exact format: "
            "Day DD Mon HH:MM–HH:MM Timezone (e.g. Monday 07 Apr 10:00–12:00 IST)."
        )

    messages = [{"role": "system", "content": AMBIGUITY_SYSTEM_PROMPT + escalation_note}]
    messages.append({
        "role": "user",
        "content": (
            f"Sender: {email_obj['sender_email']}\n"
            f"Their message:\n{email_obj['body']}"
        ),
    })
    return messages


def build_rewrite_prompt(draft: str, state: AgentState) -> list[dict]:
    """
    Build the message list for rewrite_node.

    Args:
        draft:  The outbound email draft to polish.
        state:  Current AgentState (for history context).

    Returns:
        list[dict]: Message list for call_for_text().
    """
    return [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Draft email to polish:\n\n{draft}"},
    ]


def build_summarise_prompt(thread_history_text: str, state: AgentState) -> list[dict]:
    """
    Build the message list for thread_intelligence_node summary calls.

    Args:
        thread_history_text:  Full thread history as a single formatted string.
        state:                Current AgentState.

    Returns:
        list[dict]: Message list for call_for_text().
    """
    return [
        {"role": "system", "content": SUMMARISE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Thread history:\n\n{thread_history_text}"},
    ]


def append_to_history(state: AgentState, role: str, content: str) -> None:
    """
    Append one message to AgentState history in place.
    Called after every OpenRouter interaction to maintain full thread context.

    Args:
        state:   AgentState dict (mutated in place).
        role:    "user" | "assistant"
        content: The message content string.
    """
    state["history"].append({"role": role, "content": content})
```

---

## 6. Confidence Threshold Logic

**Where it applies:** Only on calls to the `classify()` tool from `email_coordinator.py`.

**How it works:**
1. `classify()` is instructed in TRIAGE_SYSTEM_PROMPT to return a `confidence` float
2. The tool schema for `classify` includes a `confidence` parameter (0.0–1.0)
3. `tool_caller._check_confidence()` reads this value from the parsed tool args
4. If `confidence < config.llm_confidence_threshold` (default 0.7):
   - `LowConfidenceError` is raised
   - Caught in `agent/nodes.py triage_node`
   - Routes to `error_node`
   - No action is taken on the email

**Tool schema addition for classify()** (must be in Phase 5's `email_coordinator.py`):
```python
# The classify tool MUST include confidence in its return schema
# classify() must return a dict like:
{
    "intent": "scheduling",  # one of the 5 intent strings
    "confidence": 0.92       # float 0.0–1.0
}
```

---

## 7. Error Handling

| Error | Source | What Happens |
|---|---|---|
| `APITimeoutError` | `openrouter_client.call_llm()` | Retried up to 3 times with exponential backoff (2s, 4s) |
| `RateLimitError` | `openrouter_client.call_llm()` | Retried (same as timeout) |
| `APIError` (non-retryable) | `openrouter_client.call_llm()` | `OpenRouterAPIError` raised immediately — no retry |
| All 3 retries exhausted | `openrouter_client.call_llm()` | `OpenRouterAPIError` raised |
| `OpenRouterAPIError` in node | `agent/nodes.py` | Caught, routes to `error_node` |
| OpenRouter returns text not tool call | `tool_caller.call_with_tools()` | `_parse_text_as_json()` attempts JSON parse — fallback to `{"raw_text": text}` |
| OpenRouter returns invalid JSON in tool args | `tool_caller.call_with_tools()` | `OpenRouterAPIError` raised |
| Tool name not in TOOL_REGISTRY | `tool_registry.call_tool()` | `ToolNotFoundError` raised, caught in node, routes to `error_node` |
| Confidence below threshold | `tool_caller._check_confidence()` | `LowConfidenceError` raised, routes to `error_node` |

---

## 8. Test Cases — tests/test_tool_caller.py

```python
# tests/test_tool_caller.py
"""
Tests for tool_caller.py using mocked OpenRouter responses.
Run: pytest tests/test_tool_caller.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from exceptions import OpenRouterAPIError, LowConfidenceError, ToolNotFoundError


def _make_tool_call_response(tool_name: str, args: dict) -> MagicMock:
    """Build a mock openai ChatCompletion response that simulates a tool call."""
    tool_call = MagicMock()
    tool_call.function.name = tool_name
    tool_call.function.arguments = json.dumps(args)

    message = MagicMock()
    message.tool_calls = [tool_call]
    message.content = None

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_text_response(text: str) -> MagicMock:
    """Build a mock response with plain text content."""
    message = MagicMock()
    message.tool_calls = None
    message.content = text

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


class TestCallWithTools:
    """Test case 1 — successful tool call dispatch."""

    def test_tool_call_dispatched_correctly(self):
        mock_response = _make_tool_call_response(
            "classify",
            {"intent": "scheduling", "confidence": 0.95},
        )
        mock_tool_result = {"intent": "scheduling", "confidence": 0.95}

        with patch("openrouter_client.call_llm", return_value=mock_response), \
             patch("tool_registry.call_tool", return_value=mock_tool_result) as mock_call:
            from tool_caller import call_with_tools
            result = call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tool_schemas=[],
            )
            mock_call.assert_called_once_with(
                "classify", {"intent": "scheduling", "confidence": 0.95}
            )
            assert result["intent"] == "scheduling"


class TestConfidenceThreshold:
    """Test case 2 — low confidence raises LowConfidenceError."""

    def test_low_confidence_raises(self):
        mock_response = _make_tool_call_response(
            "classify",
            {"intent": "noise", "confidence": 0.45},
        )
        with patch("openrouter_client.call_llm", return_value=mock_response), \
             patch("tool_registry.call_tool", return_value={}), \
             patch("config.config") as mock_cfg:
            mock_cfg.llm_confidence_threshold = 0.7
            from tool_caller import call_with_tools
            with pytest.raises(LowConfidenceError):
                call_with_tools(
                    messages=[{"role": "user", "content": "test"}],
                    tool_schemas=[],
                )

    def test_high_confidence_does_not_raise(self):
        mock_response = _make_tool_call_response(
            "classify",
            {"intent": "scheduling", "confidence": 0.92},
        )
        with patch("openrouter_client.call_llm", return_value=mock_response), \
             patch("tool_registry.call_tool", return_value={"intent": "scheduling"}), \
             patch("config.config") as mock_cfg:
            mock_cfg.llm_confidence_threshold = 0.7
            from tool_caller import call_with_tools
            result = call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tool_schemas=[],
            )
            assert result is not None


class TestTextFallback:
    """Test case 3 — plain text OpenRouter response handled gracefully."""

    def test_valid_json_text_parsed(self):
        mock_response = _make_text_response('{"intent": "scheduling", "confidence": 0.8}')
        with patch("openrouter_client.call_llm", return_value=mock_response):
            from tool_caller import call_with_tools
            result = call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tool_schemas=[],
            )
            assert result.get("intent") == "scheduling"

    def test_non_json_text_wrapped_as_raw_text(self):
        mock_response = _make_text_response("I cannot determine the intent.")
        with patch("openrouter_client.call_llm", return_value=mock_response):
            from tool_caller import call_with_tools
            result = call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tool_schemas=[],
            )
            assert "raw_text" in result


class TestRetryBehavior:
    """Test case 4 — retryable errors trigger retries, non-retryable raise immediately."""

    def test_rate_limit_error_retried(self):
        from openai import RateLimitError
        # Fail twice, succeed on third attempt
        mock_success = _make_text_response("OK")
        with patch("openrouter_client.get_client") as mock_client_fn, \
             patch("time.sleep"):
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.chat.completions.create.side_effect = [
                RateLimitError("rate limit", response=MagicMock(), body={}),
                RateLimitError("rate limit", response=MagicMock(), body={}),
                mock_success,
            ]
            from openrouter_client import call_llm
            result = call_llm(messages=[{"role": "user", "content": "test"}])
            assert mock_client.chat.completions.create.call_count == 3

    def test_all_retries_exhausted_raises_openrouter_api_error(self):
        from openai import RateLimitError
        from exceptions import OpenRouterAPIError
        with patch("openrouter_client.get_client") as mock_client_fn, \
             patch("time.sleep"):
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.chat.completions.create.side_effect = RateLimitError(
                "rate limit", response=MagicMock(), body={}
            )
            from openrouter_client import call_llm
            with pytest.raises(OpenRouterAPIError):
                call_llm(messages=[{"role": "user", "content": "test"}])


class TestCallForText:
    """Test case 5 — call_for_text returns stripped plain text."""

    def test_returns_stripped_text(self):
        mock_response = _make_text_response("  Hello, your meeting is confirmed.  ")
        with patch("openrouter_client.call_llm", return_value=mock_response):
            from tool_caller import call_for_text
            result = call_for_text(messages=[{"role": "user", "content": "test"}])
            assert result == "Hello, your meeting is confirmed."

    def test_empty_content_raises(self):
        mock_response = _make_text_response("")
        mock_response.choices[0].message.content = ""
        with patch("openrouter_client.call_llm", return_value=mock_response):
            from tool_caller import call_for_text
            with pytest.raises(OpenRouterAPIError):
                call_for_text(messages=[{"role": "user", "content": "test"}])
```

---

## 9. Integration Checklist

- [ ] `openrouter_client.py` exists — `call_llm()` implemented with retry logic
- [ ] `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"` used as `base_url`
- [ ] `get_client()` creates singleton `OpenAI` client — not a new instance per call
- [ ] Retry logic: 3 attempts, delays 2s and 4s, only for `APITimeoutError` and `RateLimitError`
- [ ] `APIError` (e.g. 401, 400) is NOT retried — raises `OpenRouterAPIError` immediately
- [ ] `tool_caller.py` exists — `call_with_tools()` and `call_for_text()` implemented
- [ ] `call_with_tools()` reads `message.tool_calls[0]` for tool name + JSON args
- [ ] `_check_confidence()` raises `LowConfidenceError` when `confidence` key present and below threshold
- [ ] `_parse_text_as_json()` strips markdown code fences before attempting JSON parse
- [ ] `prompt_builder.py` exists — all 5 `build_*` prompt functions implemented
- [ ] `TRIAGE_SYSTEM_PROMPT` instructs OpenRouter to return confidence score with classification
- [ ] `build_triage_prompt()` includes `state["history"]` in the messages list
- [ ] `append_to_history()` is called in `agent/nodes.py` after every OpenRouter interaction (Phase 6)
- [ ] `pytest tests/test_tool_caller.py -v` passes all tests with mocked OpenRouter

---

## Cross-Phase References

| Exported | From | Imported By |
|---|---|---|
| `call_llm()` | `openrouter_client.py` | `tool_caller.py` (P4) — only entry point to OpenRouter |
| `call_with_tools()` | `tool_caller.py` | `agent/nodes.py` (P6) — every node that calls OpenRouter with tools |
| `call_for_text()` | `tool_caller.py` | `agent/nodes.py` (P6) — `rewrite_node`, `thread_intelligence_node` |
| `build_triage_prompt()` | `prompt_builder.py` | `agent/nodes.py triage_node` (P6) |
| `build_coordination_prompt()` | `prompt_builder.py` | `agent/nodes.py coordination_node` (P6) |
| `build_ambiguity_prompt()` | `prompt_builder.py` | `agent/nodes.py ambiguity_node` (P6) |
| `build_rewrite_prompt()` | `prompt_builder.py` | `agent/nodes.py rewrite_node` (P6) |
| `build_summarise_prompt()` | `prompt_builder.py` | `agent/nodes.py thread_intelligence_node` (P6) |
| `append_to_history()` | `prompt_builder.py` | `agent/nodes.py` (P6) — after every OpenRouter call |
| `OpenRouterAPIError` | `exceptions.py` (P1) | `openrouter_client.py`, `tool_caller.py`, `agent/nodes.py` |
| `LowConfidenceError` | `exceptions.py` (P1) | `tool_caller.py`, `agent/nodes.py triage_node` |
| `ToolNotFoundError` | `exceptions.py` (P1) | `tool_registry.py` (P5), caught in `agent/nodes.py` |

---

*PHASE4_OPENROUTER_INTEGRATION.md | Team TRIOLOGY | PCCOE Pune | Problem Statement 03*
