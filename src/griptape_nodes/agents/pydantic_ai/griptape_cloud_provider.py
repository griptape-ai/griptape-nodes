"""HTTP client provider for the Griptape Cloud chat-messages endpoint."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
from pydantic_ai.models import DEFAULT_HTTP_TIMEOUT, create_async_http_client
from pydantic_ai.providers import Provider

if TYPE_CHECKING:
    from pydantic_ai.profiles import ModelProfile


GRIPTAPE_CLOUD_BASE_URL = "https://cloud.griptape.ai"


class GriptapeCloudProvider(Provider[httpx.AsyncClient]):
    """Provides an authenticated `httpx.AsyncClient` for Griptape Cloud's chat API.

    Pydantic AI providers are responsible for owning the HTTP client lifecycle.
    When the provider is used as an async context manager (the agent does this
    automatically), it closes any client it created on its own.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("GT_CLOUD_API_KEY")
        if not api_key:
            msg = (
                "Griptape Cloud API key is required. Pass `api_key=` or set the GT_CLOUD_API_KEY environment variable."
            )
            raise ValueError(msg)

        self._api_key = api_key
        self._base_url = (base_url or os.environ.get("GT_CLOUD_BASE_URL", GRIPTAPE_CLOUD_BASE_URL)).rstrip("/")

        if http_client is None:

            def factory() -> httpx.AsyncClient:
                return create_async_http_client(timeout=DEFAULT_HTTP_TIMEOUT)

            self._client = factory()
            self._own_http_client = self._client
            self._http_client_factory = factory
        else:
            self._client = http_client

    @property
    def name(self) -> str:
        return "griptape-cloud"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @staticmethod
    def model_profile(model_name: str) -> ModelProfile | None:  # noqa: ARG004
        # Griptape Cloud picks the underlying model server-side based on the
        # `driver_configuration.model` we send. We don't know that model's
        # capabilities here, so we hand back the default profile and let the
        # cloud worry about provider-specific quirks.
        return None

    def _set_http_client(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client
