"""Tests for FlowManager.on_extract_flow_commands_from_image_metadata."""

import base64
import pickle
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from griptape_nodes.retained_mode.events.flow_events import (
    ExtractFlowCommandsFromImageMetadataRequest,
    ExtractFlowCommandsFromImageMetadataResultFailure,
    ExtractFlowCommandsFromImageMetadataResultSuccess,
)
from griptape_nodes.retained_mode.file_metadata.workflow_metadata import FLOW_COMMANDS_KEY
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@pytest.fixture
def image_without_metadata() -> Generator[str, None, None]:
    """A plain PNG with no embedded text chunks."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        Image.new("RGB", (4, 4), color="red").save(f, format="PNG")
        path = f.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def image_with_unrelated_metadata() -> Generator[str, None, None]:
    """A PNG that has metadata but no gtn flow commands key."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        info = PngInfo()
        info.add_text("Description", "not a workflow")
        Image.new("RGB", (4, 4), color="green").save(f, format="PNG", pnginfo=info)
        path = f.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def image_with_flow_commands() -> Generator[str, None, None]:
    """A PNG whose FLOW_COMMANDS_KEY payload is a valid pickle."""
    payload = base64.b64encode(pickle.dumps({"sentinel": "flow"})).decode("ascii")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        info = PngInfo()
        info.add_text(FLOW_COMMANDS_KEY, payload)
        Image.new("RGB", (4, 4), color="blue").save(f, format="PNG", pnginfo=info)
        path = f.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)


class TestExtractFlowCommandsFromImageMetadata:
    """Covers the non-error success paths for images that carry no workflow payload."""

    def test_returns_success_with_none_when_image_has_no_metadata(
        self, griptape_nodes: GriptapeNodes, image_without_metadata: str
    ) -> None:
        flow_manager = griptape_nodes.FlowManager()
        request = ExtractFlowCommandsFromImageMetadataRequest(file_url_or_path=image_without_metadata)

        result = flow_manager.on_extract_flow_commands_from_image_metadata(request)

        assert isinstance(result, ExtractFlowCommandsFromImageMetadataResultSuccess)
        assert result.serialized_flow_commands is None
        assert result.altered_workflow_state is False

    def test_returns_success_with_none_when_flow_commands_key_missing(
        self, griptape_nodes: GriptapeNodes, image_with_unrelated_metadata: str
    ) -> None:
        flow_manager = griptape_nodes.FlowManager()
        request = ExtractFlowCommandsFromImageMetadataRequest(file_url_or_path=image_with_unrelated_metadata)

        result = flow_manager.on_extract_flow_commands_from_image_metadata(request)

        assert isinstance(result, ExtractFlowCommandsFromImageMetadataResultSuccess)
        assert result.serialized_flow_commands is None
        assert result.altered_workflow_state is False

    def test_returns_failure_when_file_missing(self, griptape_nodes: GriptapeNodes) -> None:
        flow_manager = griptape_nodes.FlowManager()
        request = ExtractFlowCommandsFromImageMetadataRequest(file_url_or_path="/does/not/exist.png")

        result = flow_manager.on_extract_flow_commands_from_image_metadata(request)

        assert isinstance(result, ExtractFlowCommandsFromImageMetadataResultFailure)

    def test_returns_commands_when_flow_commands_key_present(
        self, griptape_nodes: GriptapeNodes, image_with_flow_commands: str
    ) -> None:
        flow_manager = griptape_nodes.FlowManager()
        request = ExtractFlowCommandsFromImageMetadataRequest(file_url_or_path=image_with_flow_commands)

        result = flow_manager.on_extract_flow_commands_from_image_metadata(request)

        assert isinstance(result, ExtractFlowCommandsFromImageMetadataResultSuccess)
        assert result.serialized_flow_commands == {"sentinel": "flow"}
        assert result.altered_workflow_state is False
