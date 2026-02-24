"""Tests for LoadImage node."""

import pytest
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.image.load_image import LoadImage


class TestLoadImageFromPath:
    """Tests for LoadImage._load_image_from_path.

    The key behavior: the method wraps any non-empty path string directly
    in an ImageUrlArtifact without checking file existence or extension validity.
    """

    @pytest.fixture
    def node(self, griptape_nodes: GriptapeNodes) -> LoadImage:
        return LoadImage(name="test_load_image")

    def test_empty_string_returns_none(self, node: LoadImage) -> None:
        result = node._load_image_from_path("")
        assert result is None

    def test_none_returns_none(self, node: LoadImage) -> None:
        result = node._load_image_from_path(None)
        assert result is None

    def test_local_path_returns_image_url_artifact(self, node: LoadImage) -> None:
        """Any non-empty path should be wrapped in an ImageUrlArtifact without existence checks."""
        result = node._load_image_from_path("/path/to/nonexistent/image.png")
        assert isinstance(result, ImageUrlArtifact)

    def test_artifact_value_matches_input_path(self, node: LoadImage) -> None:
        path = "/some/local/image.jpg"
        result = node._load_image_from_path(path)
        assert result is not None
        assert result.value == path

    def test_url_returns_image_url_artifact(self, node: LoadImage) -> None:
        url = "https://example.com/photo.png"
        result = node._load_image_from_path(url)
        assert isinstance(result, ImageUrlArtifact)
        assert result.value == url

    def test_macro_path_returns_image_url_artifact(self, node: LoadImage) -> None:
        """Macro paths like {outputs}/file.png are wrapped without resolution."""
        path = "{outputs}/generated_image.png"
        result = node._load_image_from_path(path)
        assert isinstance(result, ImageUrlArtifact)
        assert result.value == path

    def test_unsupported_extension_does_not_raise(self, node: LoadImage) -> None:
        """Extension validation is no longer done at path-loading time."""
        result = node._load_image_from_path("/path/to/file.bmp")
        assert isinstance(result, ImageUrlArtifact)
