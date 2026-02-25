"""Tests for ArtifactPathValidator trait."""

from collections.abc import Callable
from typing import Any

import pytest
from griptape_nodes_library.utils.artifact_path_tethering import ArtifactPathValidator


class TestArtifactPathValidator:
    """Tests for ArtifactPathValidator validation behavior.

    The key behavior: local file paths and macro paths are accepted as-is
    (deferred to execution time). Only URLs are validated eagerly.
    """

    @pytest.fixture
    def validator(self) -> ArtifactPathValidator:
        return ArtifactPathValidator(
            supported_extensions={".png", ".jpg"},
            url_content_type_prefix="image/",
        )

    @pytest.fixture
    def validate(self, validator: ArtifactPathValidator) -> Callable[[Any, Any], None]:
        """Return the first validator function from the trait."""
        return validator.validators_for_trait()[0]

    def test_empty_string_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        validate(None, "")

    def test_none_value_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        validate(None, None)

    def test_whitespace_only_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        validate(None, "   ")

    def test_local_file_path_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Non-existent local file paths are accepted; validation deferred to execution time."""
        validate(None, "/path/to/nonexistent/image.png")

    def test_macro_path_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """{outputs}/file.png style macro paths are accepted without validation."""
        validate(None, "{outputs}/image.png")

    def test_relative_path_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Relative paths are accepted without validation."""
        validate(None, "images/photo.png")

    def test_quoted_path_from_finder_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Quoted file paths (e.g. from macOS Finder 'Copy as Pathname') are accepted."""
        validate(None, "'/path/to/image.png'")

    def test_path_with_unsupported_extension_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Local paths with unsupported extensions are still accepted; checked at execution time."""
        validate(None, "/path/to/file.bmp")

    def test_valid_https_url_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Valid https:// URLs pass URL validation."""
        validate(None, "https://example.com/image.png")

    def test_valid_http_url_is_accepted(self, validate: Callable[[Any, Any], None]) -> None:
        """Valid http:// URLs pass URL validation."""
        validate(None, "http://example.com/image.png")

    def test_url_with_no_netloc_raises_value_error(self, validate: Callable[[Any, Any], None]) -> None:
        """https:// with no hostname should raise ValueError since it's a malformed URL."""
        with pytest.raises(ValueError, match="Invalid URL"):
            validate(None, "https://")

    def test_http_url_with_no_netloc_raises_value_error(self, validate: Callable[[Any, Any], None]) -> None:
        """http:// with no hostname should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid URL"):
            validate(None, "http://")
