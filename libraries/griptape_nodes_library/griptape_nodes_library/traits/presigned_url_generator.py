"""Presigned URL generator trait for converting asset URLs to presigned URLs."""

import logging
from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.exe_types.core_types import Trait
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@dataclass(eq=False)
class PresignedUrlGenerator(Trait):
    """Trait that converts asset URLs to presigned URLs when parameter values are accessed.

    This trait converts URLs into presigned download URLs when the parameter value is retrieved.
    When this trait is applied, any HTTP/HTTPS URL will be converted to a presigned download URL
    using the static file system.

    Usage example:
        parameter.add_trait(PresignedUrlGenerator())

    Conversion rules:
    - HTTP/HTTPS URLs: Convert to presigned download URL
    - Non-URL values: Pass through unchanged
    """

    element_id: str = field(default_factory=lambda: "PresignedUrlGeneratorTrait")

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["presigned_url_generator"]

    def ui_options_for_trait(self) -> dict:
        return {}

    def display_options_for_trait(self) -> dict:
        return {}

    def validators_for_trait(self) -> list:
        return []

    def converters_for_trait(self) -> list:
        return []

    def read_converters_for_trait(self) -> list:
        def convert_asset_url_to_presigned(value: Any) -> Any:
            """Convert asset URLs to presigned URLs when accessing parameter values."""
            if not value:
                return value

            # Handle dictionary format (most common for artifacts)
            if isinstance(value, dict):
                url = value.get("value")
                if url and self._should_convert_url(url):
                    presigned_url = self._convert_to_presigned_url(url)
                    if presigned_url != url:
                        # Create a copy to avoid mutating the original
                        converted_value = value.copy()
                        converted_value["value"] = presigned_url
                        return converted_value
                return value

            # Handle direct string URLs
            if isinstance(value, str) and self._should_convert_url(value):
                return self._convert_to_presigned_url(value)

            # Handle artifact objects with a value attribute
            if hasattr(value, "value") and not isinstance(value, str):
                artifact_value = value.value  # type: ignore[attr-defined]
                if self._should_convert_url(artifact_value):
                    # For artifact objects, we need to create a new instance with the presigned URL
                    # Since we can't easily clone arbitrary artifact objects, we'll modify the value directly
                    # This is safe because the conversion is temporary for access purposes
                    original_value = artifact_value
                    presigned_url = self._convert_to_presigned_url(original_value)
                    if presigned_url != original_value:
                        value.value = presigned_url  # type: ignore[attr-defined]
                return value

            return value

        return [convert_asset_url_to_presigned]

    def _should_convert_url(self, url: str | None) -> bool:
        """Check if a URL should be converted to presigned URL."""
        if not url or not isinstance(url, str):
            return False

        # If this trait is applied, we always want to generate presigned download URLs
        return url.startswith(("http://", "https://"))

    def _convert_to_presigned_url(self, url: str) -> str:
        """Convert a URL to a presigned download URL."""
        try:
            # Request presigned download URL by passing the asset_url directly
            # The storage manager will handle URL parsing using the appropriate storage driver
            download_request = CreateStaticFileDownloadUrlRequest(asset_url=url)
            download_result = GriptapeNodes.handle_request(download_request)

            if isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
                return download_result.url

        except Exception as e:
            # Log the exception but continue with fallback behavior
            logging.getLogger("griptape_nodes").debug("Failed to convert URL to presigned URL: %s", e)

        # If we can't generate a presigned URL, return the original URL
        # This allows fallback behavior rather than breaking functionality
        return url
