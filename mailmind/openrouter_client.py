"""
OpenRouter client using the OpenAI-compatible API endpoint.
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
INITIAL_DELAY_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.0

RETRYABLE_ERRORS = (APITimeoutError, RateLimitError)

# OpenRouter base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.2

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """
    Return the module-level OpenRouter OpenAI-compatible client.
    """
    global _client
    if _client is None:
        if not config.openrouter_api_key:
            logger.error("OPENROUTER_API_KEY is missing from environment!")
            
        _client = OpenAI(
            api_key=config.openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/mailmind", # Required by OpenRouter for ranking
                "X-Title": "MailMind Assistant",
            }
        )
    return _client


def call_llm(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Any:
    """
    Send a chat completion request to OpenRouter with retry logic.
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
            raise OpenRouterAPIError(
                f"OpenRouter API error (non-retryable): {exc.status_code} — {exc.message}"
            ) from exc

        except Exception as exc:
            raise OpenRouterAPIError(f"Unexpected OpenRouter error: {exc}") from exc

    raise OpenRouterAPIError(
        f"OpenRouter failed after {MAX_RETRIES} retries. Last error: {last_exc}"
    ) from last_exc
