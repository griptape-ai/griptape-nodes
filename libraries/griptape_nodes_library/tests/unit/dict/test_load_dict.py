"""Tests for LoadDictionary node."""

from unittest.mock import patch

import pytest
from griptape_nodes_library.dict.load_dict import LoadDictionary

from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestLoadDictionaryProcess:
    """Tests for LoadDictionary.process().

    The key behavioral change: files are now read via File.read_text()
    instead of griptape's TextLoader.
    """

    @pytest.fixture
    def node(self, griptape_nodes: GriptapeNodes) -> LoadDictionary:  # noqa: ARG002
        return LoadDictionary(name="test_load_dict")

    def test_uses_file_read_text(self, node: LoadDictionary) -> None:
        """File content should be read via File.read_text()."""
        node.parameter_values["file_path"] = "data.json"

        with patch.object(File, "read_text", return_value='{"key": "value"}') as mock_read:
            node.process()

        mock_read.assert_called_once()

    def test_output_is_a_dict(self, node: LoadDictionary) -> None:
        node.parameter_values["file_path"] = "data.json"

        with patch.object(File, "read_text", return_value='{"key": "value"}'):
            node.process()

        assert isinstance(node.parameter_output_values["output"], dict)

    def test_json_content_is_parsed(self, node: LoadDictionary) -> None:
        node.parameter_values["file_path"] = "data.json"

        with patch.object(File, "read_text", return_value='{"foo": "bar", "count": 42}'):
            node.process()

        assert node.parameter_output_values["output"] == {"foo": "bar", "count": 42}

    def test_file_path_output_is_set(self, node: LoadDictionary) -> None:
        node.parameter_values["file_path"] = "data.json"

        with patch.object(File, "read_text", return_value='{"key": "value"}'):
            node.process()

        assert node.parameter_output_values["file_path"] == "data.json"

    def test_empty_content_returns_value_dict(self, node: LoadDictionary) -> None:
        """Empty string falls through to to_dict's default fallback: {"value": <input>}."""
        node.parameter_values["file_path"] = "empty.json"

        with patch.object(File, "read_text", return_value=""):
            node.process()

        assert node.parameter_output_values["output"] == {"value": ""}
