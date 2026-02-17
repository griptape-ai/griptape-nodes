"""File path-like object for simplified file reading via the retained mode API."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, NamedTuple, cast

from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    ResolveMacroPathRequest,
    ResolveMacroPathResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.project_events import MacroPath


class FileLoadError(Exception):
    """Raised when a file load operation fails.

    Attributes:
        failure_reason: Classification of why the load failed.
        result_details: Human-readable error message.
    """

    def __init__(
        self,
        failure_reason: FileIOFailureReason,
        result_details: str,
        missing_variables: set[str] | None = None,
    ) -> None:
        self.failure_reason = failure_reason
        self.result_details = result_details
        self.missing_variables = missing_variables
        super().__init__(result_details)


class FileContent(NamedTuple):
    """Result of reading a file, containing content and metadata."""

    content: str | bytes
    mime_type: str
    encoding: str | None
    size: int


def _resolve_file_path(file_path: str | MacroPath | None) -> str | None:
    """Resolve a file path, handling MacroPath resolution if needed.

    Args:
        file_path: A plain path string, a MacroPath, or None.

    Returns:
        A resolved path string, or None if file_path is None.

    Raises:
        FileLoadError: If macro resolution fails.
    """
    if file_path is None:
        return None

    if isinstance(file_path, str):
        return file_path

    # It's a MacroPath - resolve it
    resolve_result = GriptapeNodes.handle_request(ResolveMacroPathRequest(macro_path=file_path))

    if isinstance(resolve_result, ResolveMacroPathResultFailure):
        raise FileLoadError(
            failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
            result_details=str(resolve_result.result_details),
            missing_variables=resolve_result.missing_variables,
        )

    return resolve_result.resolved_path  # type: ignore[union-attr]


async def _aresolve_file_path(file_path: str | MacroPath | None) -> str | None:
    """Async version of _resolve_file_path.

    Resolve a file path, handling MacroPath resolution if needed.

    Args:
        file_path: A plain path string, a MacroPath, or None.

    Returns:
        A resolved path string, or None if file_path is None.

    Raises:
        FileLoadError: If macro resolution fails.
    """
    if file_path is None:
        return None

    if isinstance(file_path, str):
        return file_path

    # It's a MacroPath - resolve it
    resolve_result = await GriptapeNodes.ahandle_request(ResolveMacroPathRequest(macro_path=file_path))

    if isinstance(resolve_result, ResolveMacroPathResultFailure):
        raise FileLoadError(
            failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
            result_details=str(resolve_result.result_details),
            missing_variables=resolve_result.missing_variables,
        )

    return resolve_result.resolved_path  # type: ignore[union-attr]


class File:
    """Path-like object for reading files via the retained mode API.

    The constructor stores a file reference without performing any I/O.
    Call instance methods like ``read_bytes()``, ``read_text()``, or
    ``read_data_uri()`` to perform the actual read.

    Supports MacroPath resolution: pass a MacroPath (which contains variables)
    or a plain string path.
    """

    def __init__(self, file_path: str | MacroPath) -> None:
        """Store file reference. No I/O is performed.

        Args:
            file_path: Path to the file to read. Can be a plain string or a MacroPath
                (which contains macro variables).
        """
        self._file_path = file_path

    def _read(self, encoding: str = "utf-8") -> FileContent:
        """Perform the sync file read and return a FileContent.

        Args:
            encoding: Text encoding to use if file is detected as text.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        resolved_path = _resolve_file_path(self._file_path)

        request = ReadFileRequest(
            file_path=resolved_path,
            encoding=encoding,
            should_transform_image_content_to_thumbnail=False,
        )
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ReadFileResultFailure):
            raise FileLoadError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
            )

        success = cast("ReadFileResultSuccess", result)
        return FileContent(
            content=success.content,
            mime_type=success.mime_type,
            encoding=success.encoding,
            size=success.file_size,
        )

    async def _aread(self, encoding: str = "utf-8") -> FileContent:
        """Perform the async file read and return a FileContent.

        Args:
            encoding: Text encoding to use if file is detected as text.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        resolved_path = await _aresolve_file_path(self._file_path)

        request = ReadFileRequest(
            file_path=resolved_path,
            encoding=encoding,
            should_transform_image_content_to_thumbnail=False,
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, ReadFileResultFailure):
            raise FileLoadError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
            )

        success = cast("ReadFileResultSuccess", result)
        return FileContent(
            content=success.content,
            mime_type=success.mime_type,
            encoding=success.encoding,
            size=success.file_size,
        )

    def read(self, encoding: str = "utf-8") -> FileContent:
        """Read the file and return a FileContent with content and metadata.

        Args:
            encoding: Text encoding to use if file is detected as text.

        Returns:
            A FileContent named tuple with content, mime_type, encoding, and size.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        return self._read(encoding=encoding)

    async def aread(self, encoding: str = "utf-8") -> FileContent:
        """Async version of read().

        Args:
            encoding: Text encoding to use if file is detected as text.

        Returns:
            A FileContent named tuple with content, mime_type, encoding, and size.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        return await self._aread(encoding=encoding)

    def read_bytes(self) -> bytes:
        """Read the file and return its content as bytes.

        If the content is a string, it is encoded using the file's encoding
        (falling back to utf-8 if encoding is None).

        Returns:
            The file content as bytes.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        fc = self._read()
        return _to_bytes(fc)

    async def aread_bytes(self) -> bytes:
        """Async version of read_bytes().

        Returns:
            The file content as bytes.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        fc = await self._aread()
        return _to_bytes(fc)

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read the file and return its content as a string.

        Args:
            encoding: Text encoding to use for decoding the file.

        Returns:
            The file content as a string.

        Raises:
            FileLoadError: If the file cannot be read.
            TypeError: If the file content is binary (bytes).
        """
        fc = self._read(encoding=encoding)
        return _to_text(fc)

    async def aread_text(self, encoding: str = "utf-8") -> str:
        """Async version of read_text().

        Args:
            encoding: Text encoding to use for decoding the file.

        Returns:
            The file content as a string.

        Raises:
            FileLoadError: If the file cannot be read.
            TypeError: If the file content is binary (bytes).
        """
        fc = await self._aread(encoding=encoding)
        return _to_text(fc)

    def read_data_uri(self, fallback_mime: str = "application/octet-stream") -> str:
        """Read the file and return its content as a ``data:MIME;base64,...`` URI.

        Args:
            fallback_mime: MIME type to use when the file has no mime_type.

        Returns:
            A ``data:<mime>;base64,<b64>`` string.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        fc = self._read()
        return _to_data_uri(fc, fallback_mime)

    async def aread_data_uri(self, fallback_mime: str = "application/octet-stream") -> str:
        """Async version of read_data_uri().

        Args:
            fallback_mime: MIME type to use when the file has no mime_type.

        Returns:
            A ``data:<mime>;base64,<b64>`` string.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        fc = await self._aread()
        return _to_data_uri(fc, fallback_mime)


def _to_bytes(fc: FileContent) -> bytes:
    """Convert FileContent to bytes."""
    if isinstance(fc.content, bytes):
        return fc.content

    encode_with = fc.encoding if fc.encoding is not None else "utf-8"
    return fc.content.encode(encode_with)


def _to_text(fc: FileContent) -> str:
    """Convert FileContent to str.

    Raises:
        TypeError: If the content is binary.
    """
    if isinstance(fc.content, bytes):
        msg = f"Expected text content but got binary content (mime_type={fc.mime_type})."
        raise TypeError(msg)

    return fc.content


def _to_data_uri(fc: FileContent, fallback_mime: str) -> str:
    """Convert FileContent to a data URI string."""
    mime = fc.mime_type if fc.mime_type else fallback_mime
    raw_bytes = _to_bytes(fc)
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"
