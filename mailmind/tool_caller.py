"""
Dispatches OpenRouter tool calls to the tool registry and handles confidence checking.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from exceptions import OpenRouterAPIError, LowConfidenceError, ToolNotFoundError
from openrouter_client import call_llm
from logger import get_logger

logger = get_logger(__name__)

# Confidence key model is instructed to include in classification responses
CONFIDENCE_KEY = "confidence"


def call_with_tools(
    messages: list[dict],
    tool_schemas: list[dict],
    thread_id: str = "",
    temperature: float = 0.2,
) -> dict[str, Any]:
    """
    Call LLM with tool schemas and dispatch the returned tool call.
    """
    response = call_llm(messages=messages, tools=tool_schemas, temperature=temperature)
    choice = response.choices[0]
    message = choice.message

    # Case 1: Model returned a tool call
    if message.tool_calls:
        tool_call = message.tool_calls[0]  # Always take the first tool call
        tool_name = tool_call.function.name
        try:
            tool_args: dict = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as exc:
            raise OpenRouterAPIError(
                f"Model returned non-JSON tool arguments: {tool_call.function.arguments}"
            ) from exc

        logger.debug(
            "Model called tool '%s' with args: %s", tool_name, tool_args,
            extra={"thread_id": thread_id},
        )

        # Check confidence if present in tool args
        _check_confidence(tool_args, thread_id)

        # Dispatch to tool registry
        from tool_registry import call_tool
        return call_tool(tool_name, tool_args)

    # Case 2: Model returned plain text instead of a tool call
    if message.content:
        return _parse_text_as_json(message.content, thread_id)

    raise OpenRouterAPIError("Model returned neither tool_calls nor text content.")


def call_for_text(
    messages: list[dict],
    thread_id: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Call LLM for a plain text response (no tool calling).
    """
    response = call_llm(messages=messages, temperature=temperature, max_tokens=max_tokens)
    content = response.choices[0].message.content
    if not content:
        raise OpenRouterAPIError("Model returned empty content for text call.")
    logger.debug("Model text response received.", extra={"thread_id": thread_id})
    return content.strip()


def _check_confidence(tool_args: dict, thread_id: str) -> None:
    """
    If the tool response contains a 'confidence' key, check it against the threshold.
    """
    if CONFIDENCE_KEY not in tool_args:
        return

    from config import config
    confidence = float(tool_args[CONFIDENCE_KEY])
    if confidence < config.llm_confidence_threshold:
        logger.warning(
            "Low confidence classification: %.2f < %.2f threshold.",
            confidence, config.llm_confidence_threshold,
            extra={"thread_id": thread_id},
        )
        raise LowConfidenceError(
            f"Classification confidence {confidence:.2f} is below "
            f"threshold {config.llm_confidence_threshold}. Handled by operator."
        )


def _parse_text_as_json(text: str, thread_id: str) -> dict:
    """
    Attempt to parse a plain text response as JSON.
    """
    try:
        # Strip markdown code fences
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) > 2:
                # remove first and last line of fence
                cleaned = "\n".join(lines[1:-1])
            else:
                # maybe just one line like ```json {} ```
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()
                
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "Model returned plain text instead of tool call — wrapping as raw_text.",
            extra={"thread_id": thread_id},
        )
        return {"raw_text": text}
