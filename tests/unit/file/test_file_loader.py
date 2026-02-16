"""Unit tests for FileLoader."""

from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser.core import ParsedMacro
from griptape_nodes.file.file_loader import FileLoader, FileLoadError
from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    ResolveMacroPathResultFailure,
    ResolveMacroPathResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import MacroPath

HANDLE_REQUEST_PATH = "griptape_nodes.file.file_loader.GriptapeNodes.handle_request"


class TestFileLoader:
    """Tests for FileLoader.load()."""

    def test_load_success(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            result = FileLoader.load("workspace/test.txt")

        assert result is success_result
        mock_handle.assert_called_once()

    def test_load_failure_raises_file_load_error(self) -> None:
        failure_result = ReadFileResultFailure(
            result_details="File not found",
            failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileLoadError) as exc_info:
            FileLoader.load("workspace/missing.txt")

        assert exc_info.value.failure_reason == FileIOFailureReason.FILE_NOT_FOUND
        assert "File not found" in exc_info.value.result_details

    def test_load_no_path_raises_file_load_error(self) -> None:
        with pytest.raises(FileLoadError) as exc_info:
            FileLoader.load()

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH


class TestFileLoaderLoadText:
    """Tests for FileLoader.load_text()."""

    def test_load_text_success(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello world",
            file_size=11,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            text = FileLoader.load_text("workspace/test.txt")

        assert text == "hello world"

    def test_load_text_binary_raises_type_error(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=b"\x89PNG",
            file_size=4,
            mime_type="image/png",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result), pytest.raises(TypeError, match="binary content"):
            FileLoader.load_text("workspace/image.png")


class TestFileLoaderLoadBytes:
    """Tests for FileLoader.load_bytes()."""

    def test_load_bytes_binary_success(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/png",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = FileLoader.load_bytes("workspace/image.png")

        assert data == raw_bytes

    def test_load_bytes_text_encodes(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = FileLoader.load_bytes("workspace/test.txt")

        assert data == b"hello"

    def test_load_bytes_text_encodes_with_fallback(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = FileLoader.load_bytes("workspace/test.txt", encoding="latin-1")

        assert data == b"hello"


class TestFileLoaderMacroPath:
    """Tests for FileLoader MacroPath resolution."""

    def test_load_with_macro_path_success(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "/resolved/outputs"})
        resolve_result = ResolveMacroPathResultSuccess(
            result_details="OK",
            resolved_path="/resolved/outputs/file.txt",
        )
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = FileLoader.load(macro_path)

        assert result is read_result
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    def test_load_with_macro_path_resolution_failure(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {})
        resolve_failure = ResolveMacroPathResultFailure(
            result_details="Missing variables: outputs",
            missing_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            FileLoader.load(macro_path)

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}

    def test_load_with_string_template_and_variables(self) -> None:
        resolve_result = ResolveMacroPathResultSuccess(
            result_details="OK",
            resolved_path="/resolved/outputs/file.txt",
        )
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = FileLoader.load("{outputs}/file.txt", variables={"outputs": "/resolved/outputs"})

        assert result is read_result
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    def test_load_with_variables_but_no_path_raises(self) -> None:
        with pytest.raises(FileLoadError) as exc_info:
            FileLoader.load(variables={"outputs": "/resolved/outputs"})

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH

    def test_load_with_macro_path_and_variables_raises(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "/resolved/outputs"})
        with pytest.raises(FileLoadError) as exc_info:
            FileLoader.load(macro_path, variables={"outputs": "/other"})

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH

    def test_load_with_variables_and_file_entry_raises(self) -> None:
        with pytest.raises(FileLoadError) as exc_info:
            FileLoader.load("{outputs}/file.txt", file_entry="entry", variables={"outputs": "/resolved"})  # type: ignore[arg-type]

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH

    def test_plain_string_without_variables_no_resolution(self) -> None:
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=read_result) as mock_handle:
            result = FileLoader.load("workspace/test.txt")

        assert result is read_result
        mock_handle.assert_called_once()
