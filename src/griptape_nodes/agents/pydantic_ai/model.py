"""Build a Pydantic AI model pointed at Griptape Cloud's OpenAI-compatible API.

Griptape Cloud exposes an OpenAI-compatible Chat Completions endpoint at
``POST {base_url}/api/v1/chat/completions``. It translates OpenAI requests into
Griptape's own ``PromptStack`` / ``Message`` shapes and runs them through
whichever provider the configured model maps to (OpenAI, Anthropic, Bedrock,
Google, etc.). Because the wire format is plain OpenAI Chat Completions, we use
Pydantic AI's built-in :class:`OpenAIChatModel` instead of a hand-rolled model
adapter: text, native tool calls, structured output, and streaming usage all
flow through the standard client.
"""

from __future__ import annotations

import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

GRIPTAPE_CLOUD_BASE_URL = "https://cloud.griptape.ai"
"""Default Griptape Cloud root. The ``/api/v1`` OpenAI-compatible prefix is added here."""


def build_griptape_cloud_model(
    model_name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAIChatModel:
    """Return an :class:`OpenAIChatModel` bound to Griptape Cloud's ``/api/v1`` endpoint.

    Args:
        model_name: The Griptape Cloud model id (e.g. ``"gpt-4o"``). Cloud picks
            the underlying provider from this name server-side.
        api_key: Griptape Cloud API key. Falls back to the ``GT_CLOUD_API_KEY``
            environment variable. Sent as ``Authorization: Bearer <key>``.
        base_url: Griptape Cloud root URL (no ``/api/v1`` suffix). Falls back to
            the ``GT_CLOUD_BASE_URL`` environment variable, then to
            :data:`GRIPTAPE_CLOUD_BASE_URL`.

    Raises:
        ValueError: If no API key is available.
    """
    resolved_key = api_key or os.environ.get("GT_CLOUD_API_KEY")
    if not resolved_key:
        msg = "Griptape Cloud API key is required. Pass `api_key=` or set the GT_CLOUD_API_KEY environment variable."
        raise ValueError(msg)

    cloud_root = (base_url or os.environ.get("GT_CLOUD_BASE_URL", GRIPTAPE_CLOUD_BASE_URL)).rstrip("/")
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=f"{cloud_root}/api/v1", api_key=resolved_key),
    )
