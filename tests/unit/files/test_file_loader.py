"""Unit tests for File."""

import base64
from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser.core import ParsedMacro
from griptape_nodes.files.file import File, FileContent, FileLoadError
from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    ResolveMacroPathResultFailure,
    ResolveMacroPathResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import MacroPath

HANDLE_REQUEST_PATH = "griptape_nodes.files.file.GriptapeNodes.handle_request"
AHANDLE_REQUEST_PATH = "griptape_nodes.files.file.GriptapeNodes.ahandle_request"


class TestFileConstructor:
    """Tests that File constructor stores references without I/O."""

    def test_constructor_stores_path(self) -> None:
        f = File("workspace/test.txt")
        assert f._file_path == "workspace/test.txt"

    def test_constructor_does_no_io(self) -> None:
        """File() should not call handle_request."""
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            File("workspace/test.txt")
        mock_handle.assert_not_called()


class TestFileRead:
    """Tests for File.read()."""

    def test_read_returns_file_content(self) -> None:
        expected_size = 5
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=expected_size,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            result = File("workspace/test.txt").read()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        assert result.mime_type == "text/plain"
        assert result.encoding == "utf-8"
        assert result.size == expected_size
        mock_handle.assert_called_once()

    def test_read_failure_raises_file_load_error(self) -> None:
        failure_result = ReadFileResultFailure(
            result_details="File not found",
            failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileLoadError) as exc_info:
            File("workspace/missing.txt").read()

        assert exc_info.value.failure_reason == FileIOFailureReason.FILE_NOT_FOUND
        assert "File not found" in exc_info.value.result_details


class TestFileReadBytes:
    """Tests for File.read_bytes()."""

    def test_read_bytes_returns_binary(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/png",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = File("workspace/image.png").read_bytes()

        assert data == raw_bytes

    def test_read_bytes_encodes_text(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = File("workspace/test.txt").read_bytes()

        assert data == b"hello"

    def test_read_bytes_encodes_text_with_fallback_encoding(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            data = File("workspace/test.txt").read_bytes()

        assert data == b"hello"


class TestFileReadText:
    """Tests for File.read_text()."""

    def test_read_text_returns_string(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello world",
            file_size=11,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            text = File("workspace/test.txt").read_text()

        assert text == "hello world"

    def test_read_text_raises_type_error_on_binary(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=b"\x89PNG",
            file_size=4,
            mime_type="image/png",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result), pytest.raises(TypeError, match="binary content"):
            File("workspace/image.png").read_text()


class TestFileReadDataUri:
    """Tests for File.read_data_uri()."""

    def test_read_data_uri_binary(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/png",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            uri = File("workspace/image.png").read_data_uri()

        expected_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        assert uri == f"data:image/png;base64,{expected_b64}"

    def test_read_data_uri_text(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            uri = File("workspace/test.txt").read_data_uri()

        expected_b64 = base64.b64encode(b"hello").decode("utf-8")
        assert uri == f"data:text/plain;base64,{expected_b64}"

    def test_read_data_uri_uses_mime_type_over_fallback(self) -> None:
        raw_bytes = b"\xff\xd8\xff"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/jpeg",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            uri = File("workspace/image.jpg").read_data_uri(fallback_mime="image/png")

        assert uri.startswith("data:image/jpeg;base64,")

    def test_read_data_uri_uses_fallback_when_empty(self) -> None:
        raw_bytes = b"\x00\x01"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="",
            encoding=None,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            uri = File("workspace/file.bin").read_data_uri(fallback_mime="video/mp4")

        assert uri.startswith("data:video/mp4;base64,")

    def test_read_data_uri_propagates_file_load_error(self) -> None:
        failure_result = ReadFileResultFailure(
            result_details="File not found",
            failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileLoadError):
            File("workspace/missing.txt").read_data_uri()


class TestFileMacroPath:
    """Tests for File MacroPath resolution."""

    def test_read_with_macro_path_success(self) -> None:
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
            result = File(macro_path).read()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    def test_read_with_macro_path_resolution_failure(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {})
        resolve_failure = ResolveMacroPathResultFailure(
            result_details="Missing variables: outputs",
            missing_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            File(macro_path).read()

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}

    def test_read_with_macro_path(self) -> None:
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
            result = File(macro_path).read()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    def test_plain_string_without_variables_no_resolution(self) -> None:
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, return_value=read_result) as mock_handle:
            result = File("workspace/test.txt").read()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        mock_handle.assert_called_once()


class TestFileAsync:
    """Tests for async File methods."""

    @pytest.mark.asyncio
    async def test_aread_data_uri(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/png",
            encoding=None,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            uri = await File("workspace/image.png").aread_data_uri()

        expected_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        assert uri == f"data:image/png;base64,{expected_b64}"

    @pytest.mark.asyncio
    async def test_aread_data_uri_text(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            uri = await File("workspace/test.txt").aread_data_uri()

        expected_b64 = base64.b64encode(b"hello").decode("utf-8")
        assert uri == f"data:text/plain;base64,{expected_b64}"

    @pytest.mark.asyncio
    async def test_aread_data_uri_with_fallback(self) -> None:
        raw_bytes = b"\x00\x01"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="",
            encoding=None,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            uri = await File("workspace/file.bin").aread_data_uri(fallback_mime="audio/mpeg")

        assert uri.startswith("data:audio/mpeg;base64,")

    @pytest.mark.asyncio
    async def test_aread_bytes(self) -> None:
        raw_bytes = b"\x89PNG\r\n"
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content=raw_bytes,
            file_size=len(raw_bytes),
            mime_type="image/png",
            encoding=None,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            data = await File("workspace/image.png").aread_bytes()

        assert data == raw_bytes

    @pytest.mark.asyncio
    async def test_aread_text(self) -> None:
        success_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello world",
            file_size=11,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            text = await File("workspace/test.txt").aread_text()

        assert text == "hello world"

    @pytest.mark.asyncio
    async def test_aread_propagates_file_load_error(self) -> None:
        failure_result = ReadFileResultFailure(
            result_details="File not found",
            failure_reason=FileIOFailureReason.FILE_NOT_FOUND,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileLoadError):
            await File("workspace/missing.txt").aread()

    @pytest.mark.asyncio
    async def test_aread_with_macro_path_success(self) -> None:
        """Test async read with MacroPath resolution."""
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
        with patch(AHANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = await File(macro_path).aread()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    @pytest.mark.asyncio
    async def test_aread_with_macro_path_resolution_failure(self) -> None:
        """Test async read with MacroPath resolution failure."""
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {})
        resolve_failure = ResolveMacroPathResultFailure(
            result_details="Missing variables: outputs",
            missing_variables={"outputs"},
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            await File(macro_path).aread()

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}

    @pytest.mark.asyncio
    async def test_aread_with_macro_path(self) -> None:
        """Test async read with MacroPath."""
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
        with patch(AHANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = await File(macro_path).aread()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count
