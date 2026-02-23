"""Unit tests for File and FileDestination."""

import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.files.file import File, FileContent, FileDestination, FileLoadError, FileWriteError
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    FileIOFailureReason,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    MacroPath,
    PathResolutionFailureReason,
)

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

    def test_constructor_converts_macro_string_to_macro_path(self) -> None:
        """Strings containing macro variables are auto-wrapped in MacroPath."""
        f = File("{outputs}/file.png")
        assert isinstance(f._file_path, MacroPath)
        assert f._file_path.variables == {}

    def test_constructor_keeps_plain_string_unchanged(self) -> None:
        """Strings with no macro variables are stored as plain strings."""
        f = File("workspace/outputs/file.png")
        assert f._file_path == "workspace/outputs/file.png"

    def test_constructor_macro_path_stored_unchanged(self) -> None:
        """MacroPath objects passed directly are stored without modification."""
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "/resolved"})
        f = File(macro_path)
        assert f._file_path is macro_path

    def test_constructor_macro_string_preserves_template(self) -> None:
        """The ParsedMacro inside the auto-converted MacroPath wraps the original string."""
        f = File("{outputs}/Generate Image_output.png")
        assert isinstance(f._file_path, MacroPath)
        assert f._file_path.parsed_macro.template == "{outputs}/Generate Image_output.png"

    def test_constructor_invalid_macro_syntax_keeps_string(self) -> None:
        """Strings that fail ParsedMacro parsing are stored as plain strings."""
        with patch("griptape_nodes.files.file.ParsedMacro", side_effect=MacroSyntaxError("bad syntax")):
            f = File("{unclosed")
        assert f._file_path == "{unclosed"


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
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/resolved/outputs/file.txt"),
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
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            File(macro_path).read()

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}

    def test_read_with_macro_path(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "/resolved/outputs"})
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/resolved/outputs/file.txt"),
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

    def test_read_with_macro_path_directory_override_failure(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "custom_override"})
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Directory override attempted",
            failure_reason=PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED,
            conflicting_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            File(macro_path).read()

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH
        assert exc_info.value.conflicting_variables == {"outputs"}

    def test_read_with_macro_path_resolution_error(self) -> None:
        macro_path = MacroPath(ParsedMacro("{outputs}/file.txt"), {"outputs": "/resolved/outputs"})
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Macro resolution error",
            failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            File(macro_path).read()

        assert exc_info.value.failure_reason == FileIOFailureReason.INVALID_PATH


class TestFileMacroStringConversion:
    """End-to-end tests for the auto-conversion of macro strings in the constructor.

    These tests verify that passing a plain string containing macro variables
    (e.g. ``"{outputs}/file.png"``) behaves identically to passing an equivalent
    MacroPath: resolution is performed via GetPathForMacroRequest before the read.
    """

    def test_read_with_macro_string_triggers_resolution(self) -> None:
        """File("{outputs}/...").read() resolves the macro then reads the file."""
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/workspace/outputs/file.txt"),
        )
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = File("{outputs}/file.txt").read()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    def test_read_with_macro_string_missing_variables_raises(self) -> None:
        """Resolution failure for a macro string raises FileLoadError."""
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        with patch(HANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            File("{outputs}/file.txt").read()

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}

    def test_read_with_macro_string_uses_empty_variables(self) -> None:
        """The auto-converted MacroPath has empty variables so the project resolves directories."""
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/workspace/outputs/file.txt"),
        )
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="data",
            file_size=4,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(HANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            File("{outputs}/file.txt").read()

        resolve_call_args = mock_handle.call_args_list[0]
        request = resolve_call_args.args[0]
        assert request.variables == {}

    @pytest.mark.asyncio
    async def test_aread_with_macro_string_triggers_resolution(self) -> None:
        """Async: File("{outputs}/...").aread() resolves the macro then reads the file."""
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/workspace/outputs/file.txt"),
        )
        read_result = ReadFileResultSuccess(
            result_details="OK",
            content="hello",
            file_size=5,
            mime_type="text/plain",
            encoding="utf-8",
        )
        with patch(AHANDLE_REQUEST_PATH, side_effect=[resolve_result, read_result]) as mock_handle:
            result = await File("{outputs}/file.txt").aread()

        assert isinstance(result, FileContent)
        assert result.content == "hello"
        expected_call_count = 2
        assert mock_handle.call_count == expected_call_count

    @pytest.mark.asyncio
    async def test_aread_with_macro_string_missing_variables_raises(self) -> None:
        """Async: resolution failure for a macro string raises FileLoadError."""
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
            missing_variables={"outputs"},
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=resolve_failure), pytest.raises(FileLoadError) as exc_info:
            await File("{outputs}/file.txt").aread()

        assert exc_info.value.failure_reason == FileIOFailureReason.MISSING_MACRO_VARIABLES
        assert exc_info.value.missing_variables == {"outputs"}


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
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/resolved/outputs/file.txt"),
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
        resolve_failure = GetPathForMacroResultFailure(
            result_details="Missing variables: outputs",
            failure_reason=PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
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
        resolve_result = GetPathForMacroResultSuccess(
            result_details="OK",
            resolved_path=Path("outputs/file.txt"),
            absolute_path=Path("/resolved/outputs/file.txt"),
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


class TestFileWrite:
    """Tests for File.write_bytes() and File.write_text()."""

    def test_write_bytes_returns_final_path(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.png",
            bytes_written=4,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            path = File("workspace/output.png").write_bytes(b"\x89PNG")

        assert path == "/workspace/output.png"

    def test_write_bytes_failure_raises_file_write_error(self) -> None:
        failure_result = WriteFileResultFailure(
            result_details="Permission denied",
            failure_reason=FileIOFailureReason.PERMISSION_DENIED,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileWriteError) as exc_info:
            File("workspace/output.png").write_bytes(b"\x89PNG")

        assert exc_info.value.failure_reason == FileIOFailureReason.PERMISSION_DENIED

    def test_write_bytes_default_policy_is_overwrite(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.png",
            bytes_written=4,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            File("workspace/output.png").write_bytes(b"\x89PNG")

        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.OVERWRITE
        assert request.append is False
        assert request.create_parents is True

    def test_write_bytes_passes_policy_params_to_request(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output_1.png",
            bytes_written=4,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            File("workspace/output.png").write_bytes(
                b"\x89PNG",
                existing_file_policy=ExistingFilePolicy.CREATE_NEW,
                append=True,
                create_parents=False,
            )

        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.CREATE_NEW
        assert request.append is True
        assert request.create_parents is False

    def test_write_text_returns_final_path(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result):
            path = File("workspace/output.txt").write_text("hello")

        assert path == "/workspace/output.txt"

    def test_write_text_passes_encoding_to_request(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            File("workspace/output.txt").write_text("hello", encoding="latin-1")

        request = mock_handle.call_args.args[0]
        assert request.encoding == "latin-1"

    def test_write_text_failure_raises_file_write_error(self) -> None:
        failure_result = WriteFileResultFailure(
            result_details="File exists",
            failure_reason=FileIOFailureReason.POLICY_NO_OVERWRITE,
        )
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileWriteError) as exc_info:
            File("workspace/output.txt").write_text("hello")

        assert exc_info.value.failure_reason == FileIOFailureReason.POLICY_NO_OVERWRITE


class TestFileWriteAsync:
    """Tests for async File write methods."""

    @pytest.mark.asyncio
    async def test_awrite_bytes_returns_final_path(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.png",
            bytes_written=4,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            path = await File("workspace/output.png").awrite_bytes(b"\x89PNG")

        assert path == "/workspace/output.png"

    @pytest.mark.asyncio
    async def test_awrite_bytes_failure_raises_file_write_error(self) -> None:
        failure_result = WriteFileResultFailure(
            result_details="Permission denied",
            failure_reason=FileIOFailureReason.PERMISSION_DENIED,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileWriteError):
            await File("workspace/output.png").awrite_bytes(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_awrite_bytes_passes_policy_to_request(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output_1.png",
            bytes_written=4,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            await File("workspace/output.png").awrite_bytes(
                b"\x89PNG",
                existing_file_policy=ExistingFilePolicy.CREATE_NEW,
            )

        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.CREATE_NEW

    @pytest.mark.asyncio
    async def test_awrite_text_returns_final_path(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result):
            path = await File("workspace/output.txt").awrite_text("hello")

        assert path == "/workspace/output.txt"

    @pytest.mark.asyncio
    async def test_awrite_text_passes_encoding_to_request(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            await File("workspace/output.txt").awrite_text("hello", encoding="latin-1")

        request = mock_handle.call_args.args[0]
        assert request.encoding == "latin-1"


class TestFileDestinationConstructor:
    """Tests that FileDestination constructor stores config without I/O."""

    def test_constructor_does_no_io(self) -> None:
        with patch(HANDLE_REQUEST_PATH) as mock_handle:
            FileDestination("workspace/output.png")

        mock_handle.assert_not_called()

    def test_constructor_default_policy_is_overwrite(self) -> None:
        dest = FileDestination("workspace/output.png")

        assert dest._existing_file_policy == ExistingFilePolicy.OVERWRITE
        assert dest._append is False
        assert dest._create_parents is True

    def test_constructor_stores_existing_file_policy(self) -> None:
        dest = FileDestination("workspace/output.png", existing_file_policy=ExistingFilePolicy.CREATE_NEW)

        assert dest._existing_file_policy == ExistingFilePolicy.CREATE_NEW

    def test_constructor_stores_append_and_create_parents(self) -> None:
        dest = FileDestination("workspace/output.png", append=True, create_parents=False)

        assert dest._append is True
        assert dest._create_parents is False


class TestFileDestinationWrite:
    """Tests for FileDestination write methods."""

    def test_write_bytes_uses_stored_policy(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output_1.png",
            bytes_written=4,
        )
        dest = FileDestination("workspace/output.png", existing_file_policy=ExistingFilePolicy.CREATE_NEW)
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            path = dest.write_bytes(b"\x89PNG")

        assert path == "/workspace/output_1.png"
        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.CREATE_NEW

    def test_write_bytes_uses_stored_append_and_create_parents(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=4,
        )
        dest = FileDestination("workspace/output.txt", append=True, create_parents=False)
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            dest.write_bytes(b"data")

        request = mock_handle.call_args.args[0]
        assert request.append is True
        assert request.create_parents is False

    def test_write_bytes_failure_raises_file_write_error(self) -> None:
        failure_result = WriteFileResultFailure(
            result_details="File exists",
            failure_reason=FileIOFailureReason.POLICY_NO_OVERWRITE,
        )
        dest = FileDestination("workspace/output.png", existing_file_policy=ExistingFilePolicy.FAIL)
        with patch(HANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileWriteError) as exc_info:
            dest.write_bytes(b"\x89PNG")

        assert exc_info.value.failure_reason == FileIOFailureReason.POLICY_NO_OVERWRITE

    def test_write_text_uses_stored_policy(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        dest = FileDestination("workspace/output.txt", existing_file_policy=ExistingFilePolicy.FAIL)
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            path = dest.write_text("hello")

        assert path == "/workspace/output.txt"
        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.FAIL

    def test_write_text_passes_encoding(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        dest = FileDestination("workspace/output.txt")
        with patch(HANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            dest.write_text("hello", encoding="latin-1")

        request = mock_handle.call_args.args[0]
        assert request.encoding == "latin-1"

    def test_resolve_path_returns_path_string(self) -> None:
        dest = FileDestination("workspace/output.png")

        assert dest.resolve_path() == "workspace/output.png"


class TestFileDestinationAsync:
    """Tests for async FileDestination write methods."""

    @pytest.mark.asyncio
    async def test_awrite_bytes_uses_stored_policy(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output_1.png",
            bytes_written=4,
        )
        dest = FileDestination("workspace/output.png", existing_file_policy=ExistingFilePolicy.CREATE_NEW)
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            path = await dest.awrite_bytes(b"\x89PNG")

        assert path == "/workspace/output_1.png"
        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.CREATE_NEW

    @pytest.mark.asyncio
    async def test_awrite_bytes_failure_raises_file_write_error(self) -> None:
        failure_result = WriteFileResultFailure(
            result_details="Permission denied",
            failure_reason=FileIOFailureReason.PERMISSION_DENIED,
        )
        dest = FileDestination("workspace/output.png")
        with patch(AHANDLE_REQUEST_PATH, return_value=failure_result), pytest.raises(FileWriteError):
            await dest.awrite_bytes(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_awrite_text_uses_stored_policy(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        dest = FileDestination("workspace/output.txt", existing_file_policy=ExistingFilePolicy.FAIL)
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            path = await dest.awrite_text("hello")

        assert path == "/workspace/output.txt"
        request = mock_handle.call_args.args[0]
        assert request.existing_file_policy == ExistingFilePolicy.FAIL

    @pytest.mark.asyncio
    async def test_awrite_text_passes_encoding(self) -> None:
        success_result = WriteFileResultSuccess(
            result_details="OK",
            final_file_path="/workspace/output.txt",
            bytes_written=5,
        )
        dest = FileDestination("workspace/output.txt")
        with patch(AHANDLE_REQUEST_PATH, return_value=success_result) as mock_handle:
            await dest.awrite_text("hello", encoding="latin-1")

        request = mock_handle.call_args.args[0]
        assert request.encoding == "latin-1"
