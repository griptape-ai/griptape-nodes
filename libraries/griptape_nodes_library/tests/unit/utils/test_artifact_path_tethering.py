"""Tests for ArtifactPathTethering path sanitization behavior."""

from unittest.mock import patch

import pytest
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.node_types import TransformedParameterValue
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.image.load_image import LoadImage


class TestArtifactPathTetheringSurroundingQuotes:
    """Tests that paths are sanitized (e.g. from macOS Finder 'Copy as Pathname').

    Sanitization (quote stripping and shell escape removal) must happen in two entry points:
    - on_before_value_set: when a string is typed/pasted into the artifact field
    - _handle_path_change: when a string is typed/pasted into the path field
    """

    @pytest.fixture
    def node(self, griptape_nodes: GriptapeNodes) -> LoadImage:
        return LoadImage(name="test_node")

    def test_on_before_value_set_strips_single_quotes(self, node: LoadImage) -> None:
        """Quoted path pasted into the image field should have quotes removed."""
        result = node._tethering.on_before_value_set(node.image_parameter, "'/path/to/image.png'")

        assert isinstance(result, TransformedParameterValue)
        assert isinstance(result.value, ImageUrlArtifact)
        assert result.value.value == "/path/to/image.png"

    def test_on_before_value_set_strips_double_quotes(self, node: LoadImage) -> None:
        result = node._tethering.on_before_value_set(node.image_parameter, '"/path/to/image.png"')

        assert isinstance(result, TransformedParameterValue)
        assert isinstance(result.value, ImageUrlArtifact)
        assert result.value.value == "/path/to/image.png"

    def test_on_before_value_set_unquoted_path_unchanged(self, node: LoadImage) -> None:
        """Paths without surrounding quotes should be stored as-is."""
        result = node._tethering.on_before_value_set(node.image_parameter, "/path/to/image.png")

        assert isinstance(result, TransformedParameterValue)
        assert isinstance(result.value, ImageUrlArtifact)
        assert result.value.value == "/path/to/image.png"

    def test_handle_path_change_strips_single_quotes(self, node: LoadImage) -> None:
        """Quoted path pasted into the path field should have quotes removed before artifact sync."""
        captured = {}

        def capture_artifact(artifact, source_param_name):  # noqa: ANN001
            captured["artifact"] = artifact

        with patch.object(node._tethering, "_sync_both_parameters", side_effect=capture_artifact):
            node._tethering._handle_path_change("'/path/to/image.png'")

        assert isinstance(captured["artifact"], ImageUrlArtifact)
        assert captured["artifact"].value == "/path/to/image.png"

    def test_handle_path_change_strips_double_quotes(self, node: LoadImage) -> None:
        captured = {}

        def capture_artifact(artifact, source_param_name):  # noqa: ANN001
            captured["artifact"] = artifact

        with patch.object(node._tethering, "_sync_both_parameters", side_effect=capture_artifact):
            node._tethering._handle_path_change('"/path/to/image.png"')

        assert isinstance(captured["artifact"], ImageUrlArtifact)
        assert captured["artifact"].value == "/path/to/image.png"

    def test_handle_path_change_unquoted_path_unchanged(self, node: LoadImage) -> None:
        captured = {}

        def capture_artifact(artifact, source_param_name):  # noqa: ANN001
            captured["artifact"] = artifact

        with patch.object(node._tethering, "_sync_both_parameters", side_effect=capture_artifact):
            node._tethering._handle_path_change("/path/to/image.png")

        assert isinstance(captured["artifact"], ImageUrlArtifact)
        assert captured["artifact"].value == "/path/to/image.png"

    def test_on_before_value_set_removes_shell_escapes(self, node: LoadImage) -> None:
        """Shell-escaped path from macOS Finder 'Copy as Pathname' should have escapes removed."""
        result = node._tethering.on_before_value_set(
            node.image_parameter, "/Downloads/Dragon\\'s\\ Curse/screenshot.jpg"
        )

        assert isinstance(result, TransformedParameterValue)
        assert isinstance(result.value, ImageUrlArtifact)
        assert result.value.value == "/Downloads/Dragon's Curse/screenshot.jpg"

    def test_handle_path_change_removes_shell_escapes(self, node: LoadImage) -> None:
        """Shell-escaped path from macOS Finder 'Copy as Pathname' should have escapes removed."""
        captured = {}

        def capture_artifact(artifact, source_param_name):  # noqa: ANN001
            captured["artifact"] = artifact

        with patch.object(node._tethering, "_sync_both_parameters", side_effect=capture_artifact):
            node._tethering._handle_path_change("/Downloads/Dragon\\'s\\ Curse/screenshot.jpg")

        assert isinstance(captured["artifact"], ImageUrlArtifact)
        assert captured["artifact"].value == "/Downloads/Dragon's Curse/screenshot.jpg"
