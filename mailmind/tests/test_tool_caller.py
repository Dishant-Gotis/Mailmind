"""
Tests for tool_caller.py using mocked OpenRouter responses.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from exceptions import OpenRouterAPIError, LowConfidenceError
from tool_caller import call_with_tools, call_for_text


def _make_tool_call_response(tool_name: str, args: dict) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response that simulates a tool call."""
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


class TestToolCaller:
    @patch("tool_caller.call_llm")
    @patch("tool_registry.call_tool")
    def test_tool_call_dispatched_correctly(self, mock_call_tool, mock_call_llm):
        # Setup
        mock_response = _make_tool_call_response(
            "classify",
            {"intent": "scheduling", "confidence": 0.95},
        )
        mock_call_llm.return_value = mock_response
        mock_call_tool.return_value = {"status": "success"}

        # Execute
        result = call_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tool_schemas=[{"name": "classify"}],
        )

        # Verify
        assert result == {"status": "success"}
        mock_call_tool.assert_called_once_with(
            "classify", {"intent": "scheduling", "confidence": 0.95}
        )

    @patch("tool_caller.call_llm")
    def test_low_confidence_raises_error(self, mock_call_llm):
        # Setup
        mock_response = _make_tool_call_response(
            "classify",
            {"intent": "noise", "confidence": 0.45},
        )
        mock_call_llm.return_value = mock_response

        # Execute & Verify
        with patch("config.config") as mock_config:
            mock_config.llm_confidence_threshold = 0.7
            with pytest.raises(LowConfidenceError):
                call_with_tools(
                    messages=[{"role": "user", "content": "test"}],
                    tool_schemas=[{"name": "classify"}],
                )

    @patch("tool_caller.call_llm")
    def test_text_fallback_parsing(self, mock_call_llm):
        # Setup: Model returns JSON in code fence
        mock_response = _make_text_response("```json\n{\"intent\": \"scheduling\", \"confidence\": 0.8}\n```")
        mock_call_llm.return_value = mock_response

        # Execute
        result = call_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tool_schemas=[],
        )

        # Verify
        assert result["intent"] == "scheduling"
        assert result["confidence"] == 0.8

    @patch("tool_caller.call_llm")
    def test_call_for_text(self, mock_call_llm):
        # Setup
        mock_response = _make_text_response("  Polished response content.  ")
        mock_call_llm.return_value = mock_response

        # Execute
        result = call_for_text(messages=[{"role": "user", "content": "test"}])

        # Verify
        assert result == "Polished response content."

    @patch("tool_caller.call_llm")
    def test_empty_content_raises_error(self, mock_call_llm):
        # Setup
        mock_response = _make_text_response("")
        mock_call_llm.return_value = mock_response

        # Execute & Verify
        with pytest.raises(OpenRouterAPIError):
            call_for_text(messages=[{"role": "user", "content": "test"}])
