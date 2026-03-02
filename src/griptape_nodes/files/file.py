"""File path-like object for simplified file reading via the retained mode API."""

from __future__ import annotations

import base64
from typing import NamedTuple, cast

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    FileIOFailureReason,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultFailure,
    MacroPath,
    PathResolutionFailureReason,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


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
        conflicting_variables: set[str] | None = None,
    ) -> None:
        self.failure_reason = failure_reason
        self.result_details = result_details
        self.missing_variables = missing_variables
        self.conflicting_variables = conflicting_variables
        super().__init__(result_details)


class FileWriteError(Exception):
    """Raised when a file write operation fails.

    Attributes:
        failure_reason: Classification of why the write failed.
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


_PATH_FAILURE_TO_FILE_IO: dict[PathResolutionFailureReason, FileIOFailureReason] = {
    PathResolutionFailureReason.MISSING_REQUIRED_VARIABLES: FileIOFailureReason.MISSING_MACRO_VARIABLES,
    PathResolutionFailureReason.MACRO_RESOLUTION_ERROR: FileIOFailureReason.INVALID_PATH,
    PathResolutionFailureReason.DIRECTORY_OVERRIDE_ATTEMPTED: FileIOFailureReason.INVALID_PATH,
}


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

    # It's a MacroPath - resolve it via project-aware resolution
    resolve_result = GriptapeNodes.handle_request(
        GetPathForMacroRequest(parsed_macro=file_path.parsed_macro, variables=file_path.variables)
    )

    if isinstance(resolve_result, GetPathForMacroResultFailure):
        raise FileLoadError(
            failure_reason=_PATH_FAILURE_TO_FILE_IO[resolve_result.failure_reason],
            result_details=str(resolve_result.result_details),
            missing_variables=resolve_result.missing_variables,
            conflicting_variables=resolve_result.conflicting_variables,
        )

    return str(resolve_result.absolute_path)  # type: ignore[union-attr]


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

    # It's a MacroPath - resolve it via project-aware resolution
    resolve_result = await GriptapeNodes.ahandle_request(
        GetPathForMacroRequest(parsed_macro=file_path.parsed_macro, variables=file_path.variables)
    )

    if isinstance(resolve_result, GetPathForMacroResultFailure):
        raise FileLoadError(
            failure_reason=_PATH_FAILURE_TO_FILE_IO[resolve_result.failure_reason],
            result_details=str(resolve_result.result_details),
            missing_variables=resolve_result.missing_variables,
            conflicting_variables=resolve_result.conflicting_variables,
        )

    return str(resolve_result.absolute_path)  # type: ignore[union-attr]


class File:
    """Path-like object for reading and writing files via the retained mode API.

    The constructor stores a file reference without performing any I/O.
    Call instance methods like ``read_bytes()``, ``read_text()``,
    ``read_data_uri()``, ``write_bytes()``, or ``write_text()`` to perform
    the actual I/O.

    Supports MacroPath resolution: pass a MacroPath (which contains variables)
    or a plain string path.

    For a pre-configured write handle with baked-in write policy, use
    ``FileDestination`` instead.
    """

    def __init__(
        self,
        file_path: str | MacroPath,
    ) -> None:
        """Store file reference. No I/O is performed.

        Plain strings containing macro variables (e.g. ``"{outputs}/file.png"``) are
        automatically wrapped in a MacroPath so they are resolved against the current
        project at read time.  Strings with no macro variables and already-constructed
        MacroPath objects are stored as-is.

        Args:
            file_path: Path to the file. Can be a plain string or a MacroPath
                (which contains macro variables).
        """
        if isinstance(file_path, str):
            try:
                parsed = ParsedMacro(file_path)
            except MacroSyntaxError:
                self._file_path: str | MacroPath = file_path
            else:
                if parsed.get_variables():
                    self._file_path = MacroPath(parsed, {})
                else:
                    self._file_path = file_path
        else:
            self._file_path = file_path

    def resolve_path(self) -> str:
        """Resolve and return the absolute path string for this file.

        Useful when a caller needs the path for writing (not reading). Macro
        variables in the path are resolved against the current project at call time.

        Returns:
            Absolute path string.

        Raises:
            FileLoadError: If macro resolution fails (e.g. no project loaded).
        """
        resolved = _resolve_file_path(self._file_path)
        if resolved is None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="Cannot resolve path: file_path is None",
            )
        return resolved

    def write_bytes(
        self,
        content: bytes,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Write bytes to the file.

        Args:
            content: The bytes to write.
            existing_file_policy: How to handle an existing file. Ignored when
                append=True. Defaults to OVERWRITE.
            append: If True, append to an existing file. Defaults to False.
            create_parents: If True, create parent directories if missing.
                Defaults to True.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return self._write_content(
            content,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
        )

    async def awrite_bytes(
        self,
        content: bytes,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Async version of write_bytes().

        Args:
            content: The bytes to write.
            existing_file_policy: How to handle an existing file. Ignored when
                append=True. Defaults to OVERWRITE.
            append: If True, append to an existing file. Defaults to False.
            create_parents: If True, create parent directories if missing.
                Defaults to True.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return await self._awrite_content(
            content,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
        )

    def write_text(
        self,
        content: str,
        encoding: str = "utf-8",
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Write text to the file.

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.
            existing_file_policy: How to handle an existing file. Ignored when
                append=True. Defaults to OVERWRITE.
            append: If True, append to an existing file. Defaults to False.
            create_parents: If True, create parent directories if missing.
                Defaults to True.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return self._write_content(
            content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
        )

    async def awrite_text(
        self,
        content: str,
        encoding: str = "utf-8",
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Async version of write_text().

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.
            existing_file_policy: How to handle an existing file. Ignored when
                append=True. Defaults to OVERWRITE.
            append: If True, append to an existing file. Defaults to False.
            create_parents: If True, create parent directories if missing.
                Defaults to True.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return await self._awrite_content(
            content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
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

    def _write_content(
        self,
        content: str | bytes,
        encoding: str = "utf-8",
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Perform the sync file write.

        Args:
            content: Content to write (str or bytes).
            encoding: Text encoding to use when writing text content.
            existing_file_policy: How to handle an existing file.
            append: If True, append to an existing file.
            create_parents: If True, create parent directories if missing.

        Returns:
            The actual path where the file was written (may differ from the
            requested path if CREATE_NEW policy is in effect).

        Raises:
            FileWriteError: If the file cannot be written.
        """
        resolved_path = _resolve_file_path(self._file_path)

        if resolved_path is None:
            raise FileWriteError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="Cannot write: file_path is None",
            )

        request = WriteFileRequest(
            file_path=resolved_path,
            content=content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
        )
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, WriteFileResultFailure):
            raise FileWriteError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
                missing_variables=result.missing_variables,
            )

        return cast("WriteFileResultSuccess", result).final_file_path

    async def _awrite_content(
        self,
        content: str | bytes,
        encoding: str = "utf-8",
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> str:
        """Async version of _write_content.

        Args:
            content: Content to write (str or bytes).
            encoding: Text encoding to use when writing text content.
            existing_file_policy: How to handle an existing file.
            append: If True, append to an existing file.
            create_parents: If True, create parent directories if missing.

        Returns:
            The actual path where the file was written (may differ from the
            requested path if CREATE_NEW policy is in effect).

        Raises:
            FileWriteError: If the file cannot be written.
        """
        resolved_path = await _aresolve_file_path(self._file_path)

        if resolved_path is None:
            raise FileWriteError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="Cannot write: file_path is None",
            )

        request = WriteFileRequest(
            file_path=resolved_path,
            content=content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, WriteFileResultFailure):
            raise FileWriteError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
                missing_variables=result.missing_variables,
            )

        return cast("WriteFileResultSuccess", result).final_file_path


class FileDestination:
    """A pre-configured write handle for a file path.

    Bundles a file path with write policy so it can be passed around as a
    self-contained object. The consumer calls ``write_bytes()`` or
    ``write_text()`` without needing to know the policy details.

    For a lean path reference that also supports reading, use ``File`` instead.
    """

    def __init__(
        self,
        file_path: str | MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> None:
        """Store file path and write configuration. No I/O is performed.

        Args:
            file_path: Path to the file. Can be a plain string or a MacroPath
                (which contains macro variables).
            existing_file_policy: How to handle an existing file. Ignored when
                append=True. Defaults to OVERWRITE.
            append: If True, append to an existing file. Defaults to False.
            create_parents: If True, create parent directories if missing.
                Defaults to True.
        """
        self._file = File(file_path)
        self._existing_file_policy = existing_file_policy
        self._append = append
        self._create_parents = create_parents

    def resolve_path(self) -> str:
        """Resolve and return the absolute path string for this destination.

        Returns:
            Absolute path string.

        Raises:
            FileLoadError: If macro resolution fails (e.g. no project loaded).
        """
        return self._file.resolve_path()

    def write_bytes(self, content: bytes) -> str:
        """Write bytes to the file using the configured write policy.

        Args:
            content: The bytes to write.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return self._file.write_bytes(
            content,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )

    async def awrite_bytes(self, content: bytes) -> str:
        """Async version of write_bytes().

        Args:
            content: The bytes to write.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return await self._file.awrite_bytes(
            content,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )

    def write_text(self, content: str, encoding: str = "utf-8") -> str:
        """Write text to the file using the configured write policy.

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return self._file.write_text(
            content,
            encoding,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )

    async def awrite_text(self, content: str, encoding: str = "utf-8") -> str:
        """Async version of write_text().

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.

        Returns:
            The actual path where the file was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        return await self._file.awrite_text(
            content,
            encoding,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )


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
