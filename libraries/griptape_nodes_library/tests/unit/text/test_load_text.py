"""Tests for LoadText node."""

from unittest.mock import Mock, patch

import pytest
from griptape_nodes_library.text.load_text import LoadText

from griptape_nodes.files.file import File
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestLoadTextProcess:
    """Tests for LoadText.process().

    The key behavioral change: non-PDF files now use File.read_text()
    instead of griptape's TextLoader.
    """

    @pytest.fixture
    def node(self, griptape_nodes: GriptapeNodes) -> LoadText:  # noqa: ARG002
        return LoadText(name="test_load_text")

    def test_non_pdf_uses_file_read_text(self, node: LoadText) -> None:
        """Non-PDF files should be read via File.read_text()."""
        node.parameter_values["path"] = "document.txt"

        with patch.object(File, "read_text", return_value="hello world") as mock_read:
            node.process()

        mock_read.assert_called_once()

    def test_non_pdf_output_is_set(self, node: LoadText) -> None:
        node.parameter_values["path"] = "document.txt"

        with patch.object(File, "read_text", return_value="hello world"):
            node.process()

        assert node.parameter_output_values["output"] == "hello world"
        assert node.parameter_output_values["path"] == "document.txt"

    def test_pdf_uses_pdf_loader(self, node: LoadText) -> None:
        """PDF files should use PdfLoader, not File.read_text()."""
        node.parameter_values["path"] = "document.pdf"

        mock_artifact = Mock()
        mock_artifact.value = "pdf content"

        with patch("griptape_nodes_library.text.load_text.PdfLoader") as mock_loader_cls:
            mock_loader_cls.return_value.load.return_value = [mock_artifact]
            node.process()

        mock_loader_cls.return_value.load.assert_called_once_with("document.pdf")

    def test_pdf_output_is_set(self, node: LoadText) -> None:
        node.parameter_values["path"] = "document.pdf"

        mock_artifact = Mock()
        mock_artifact.value = "pdf content"

        with patch("griptape_nodes_library.text.load_text.PdfLoader") as mock_loader_cls:
            mock_loader_cls.return_value.load.return_value = [mock_artifact]
            node.process()

        assert node.parameter_output_values["output"] == "pdf content"
        assert node.parameter_output_values["path"] == "document.pdf"

    def test_non_pdf_does_not_use_pdf_loader(self, node: LoadText) -> None:
        """Non-PDF extensions should never touch PdfLoader."""
        node.parameter_values["path"] = "notes.md"

        with (
            patch.object(File, "read_text", return_value="markdown content"),
            patch("griptape_nodes_library.text.load_text.PdfLoader") as mock_loader_cls,
        ):
            node.process()

        mock_loader_cls.assert_not_called()
