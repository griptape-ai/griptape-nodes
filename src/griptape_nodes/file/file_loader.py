"""FileLoader abstraction for simplified file reading via the retained mode API."""

from __future__ import annotations

import base64

from griptape_nodes.common.macro_parser.core import ParsedMacro
from griptape_nodes.retained_mode.events.os_events import (
    FileIOFailureReason,
    FileSystemEntry,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    ResolveMacroPathRequest,
    ResolveMacroPathResultFailure,
)
from griptape_nodes.retained_mode.events.project_events import MacroPath, MacroVariables
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
    ) -> None:
        self.failure_reason = failure_reason
        self.result_details = result_details
        self.missing_variables = missing_variables
        super().__init__(result_details)


class FileLoader:
    """Stateless helper for loading files via the retained mode API.

    Wraps ReadFileRequest / GriptapeNodes.handle_request() and raises
    FileLoadError on failure so callers don't need to inspect result types.

    Supports MacroPath resolution: pass a MacroPath directly, or pass a string
    template with a variables dict to resolve macro paths before reading.
    """

    @staticmethod
    def _resolve_file_path(
        file_path: str | MacroPath | None,
        variables: MacroVariables | None,
    ) -> str | None:
        """Resolve a file path, handling MacroPath resolution if needed.

        Args:
            file_path: A plain path string, a MacroPath, or None.
            variables: Macro variables for template resolution.

        Returns:
            A resolved path string, or None if file_path is None.

        Raises:
            FileLoadError: If the arguments are invalid or macro resolution fails.
        """
        if file_path is None and variables is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be provided without a file_path.",
            )

        if isinstance(file_path, MacroPath) and variables is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be provided when file_path is already a MacroPath.",
            )

        if file_path is None:
            return None

        if isinstance(file_path, str) and variables is None:
            return file_path

        # Build a MacroPath from string template + variables
        if isinstance(file_path, str):
            macro_path = MacroPath(ParsedMacro(file_path), variables)  # type: ignore[arg-type]
        else:
            macro_path = file_path

        resolve_result = GriptapeNodes.handle_request(ResolveMacroPathRequest(macro_path=macro_path))

        if isinstance(resolve_result, ResolveMacroPathResultFailure):
            raise FileLoadError(
                failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
                result_details=str(resolve_result.result_details),
                missing_variables=resolve_result.missing_variables,
            )

        return resolve_result.resolved_path  # type: ignore[union-attr]

    @staticmethod
    async def _aresolve_file_path(
        file_path: str | MacroPath | None,
        variables: MacroVariables | None,
    ) -> str | None:
        """Async version of _resolve_file_path.

        Resolve a file path, handling MacroPath resolution if needed.

        Args:
            file_path: A plain path string, a MacroPath, or None.
            variables: Macro variables for template resolution.

        Returns:
            A resolved path string, or None if file_path is None.

        Raises:
            FileLoadError: If the arguments are invalid or macro resolution fails.
        """
        if file_path is None and variables is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be provided without a file_path.",
            )

        if isinstance(file_path, MacroPath) and variables is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be provided when file_path is already a MacroPath.",
            )

        if file_path is None:
            return None

        if isinstance(file_path, str) and variables is None:
            return file_path

        # Build a MacroPath from string template + variables
        if isinstance(file_path, str):
            macro_path = MacroPath(ParsedMacro(file_path), variables)  # type: ignore[arg-type]
        else:
            macro_path = file_path

        resolve_result = await GriptapeNodes.ahandle_request(ResolveMacroPathRequest(macro_path=macro_path))

        if isinstance(resolve_result, ResolveMacroPathResultFailure):
            raise FileLoadError(
                failure_reason=FileIOFailureReason.MISSING_MACRO_VARIABLES,
                result_details=str(resolve_result.result_details),
                missing_variables=resolve_result.missing_variables,
            )

        return resolve_result.resolved_path  # type: ignore[union-attr]

    @staticmethod
    def load(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> ReadFileResultSuccess:
        """Load a file and return the full result object.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            ReadFileResultSuccess with content, mime_type, encoding, etc.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        if variables is not None and file_entry is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be used together with file_entry.",
            )

        resolved_path = FileLoader._resolve_file_path(file_path, variables)

        if resolved_path is None and file_entry is None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="Either file_path or file_entry must be provided.",
            )

        request = ReadFileRequest(
            file_path=resolved_path,
            file_entry=file_entry,
            encoding=encoding,
        )
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, ReadFileResultFailure):
            raise FileLoadError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
            )

        return result  # type: ignore[return-value]

    @staticmethod
    def load_text(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> str:
        """Load a file and return its text content.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            The file content as a string.

        Raises:
            FileLoadError: If the file cannot be read.
            TypeError: If the file content is binary (bytes).
        """
        result = FileLoader.load(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        if isinstance(result.content, bytes):
            msg = f"Expected text content but got binary content (mime_type={result.mime_type})."
            raise TypeError(msg)

        return result.content

    @staticmethod
    def load_bytes(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> bytes:
        """Load a file and return its content as bytes.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files. Also used as fallback encoding
                when converting text content to bytes if the result has no encoding.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            The file content as bytes.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        result = FileLoader.load(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        if isinstance(result.content, bytes):
            return result.content

        encode_with = result.encoding if result.encoding is not None else encoding
        return result.content.encode(encode_with)

    @staticmethod
    async def aload(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> ReadFileResultSuccess:
        """Async version of load(). Load a file and return the full result object.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            ReadFileResultSuccess with content, mime_type, encoding, etc.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        if variables is not None and file_entry is not None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="variables cannot be used together with file_entry.",
            )

        resolved_path = await FileLoader._aresolve_file_path(file_path, variables)

        if resolved_path is None and file_entry is None:
            raise FileLoadError(
                failure_reason=FileIOFailureReason.INVALID_PATH,
                result_details="Either file_path or file_entry must be provided.",
            )

        request = ReadFileRequest(
            file_path=resolved_path,
            file_entry=file_entry,
            encoding=encoding,
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, ReadFileResultFailure):
            raise FileLoadError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
            )

        return result  # type: ignore[return-value]

    @staticmethod
    async def aload_text(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> str:
        """Async version of load_text(). Load a file and return its text content.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            The file content as a string.

        Raises:
            FileLoadError: If the file cannot be read.
            TypeError: If the file content is binary (bytes).
        """
        result = await FileLoader.aload(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        if isinstance(result.content, bytes):
            msg = f"Expected text content but got binary content (mime_type={result.mime_type})."
            raise TypeError(msg)

        return result.content

    @staticmethod
    async def aload_bytes(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
    ) -> bytes:
        """Async version of load_bytes(). Load a file and return its content as bytes.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files. Also used as fallback encoding
                when converting text content to bytes if the result has no encoding.
            variables: Macro variables for template resolution. Only valid with a string file_path.

        Returns:
            The file content as bytes.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        result = await FileLoader.aload(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        if isinstance(result.content, bytes):
            return result.content

        encode_with = result.encoding if result.encoding is not None else encoding
        return result.content.encode(encode_with)

    @staticmethod
    def load_data_uri(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
        fallback_mime: str = "application/octet-stream",
    ) -> str:
        """Load a file and return its content as a ``data:MIME;base64,...`` URI.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files. Also used as fallback encoding
                when converting text content to bytes if the result has no encoding.
            variables: Macro variables for template resolution. Only valid with a string file_path.
            fallback_mime: MIME type to use when the result has no mime_type.

        Returns:
            A ``data:<mime>;base64,<b64>`` string.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        result = FileLoader.load(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        content = result.content
        if isinstance(content, str):
            encode_with = result.encoding if result.encoding is not None else encoding
            content = content.encode(encode_with)

        mime = result.mime_type if result.mime_type else fallback_mime
        b64 = base64.b64encode(content).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    @staticmethod
    async def aload_data_uri(
        file_path: str | MacroPath | None = None,
        *,
        file_entry: FileSystemEntry | None = None,
        encoding: str = "utf-8",
        variables: MacroVariables | None = None,
        fallback_mime: str = "application/octet-stream",
    ) -> str:
        """Async version of load_data_uri(). Load a file and return its content as a ``data:MIME;base64,...`` URI.

        Args:
            file_path: Path to the file to read. Can be a plain string, a MacroPath
                for macro resolution, or a string template when combined with variables.
                Mutually exclusive with file_entry.
            file_entry: FileSystemEntry from directory listing (mutually exclusive with file_path).
            encoding: Text encoding to use for text files. Also used as fallback encoding
                when converting text content to bytes if the result has no encoding.
            variables: Macro variables for template resolution. Only valid with a string file_path.
            fallback_mime: MIME type to use when the result has no mime_type.

        Returns:
            A ``data:<mime>;base64,<b64>`` string.

        Raises:
            FileLoadError: If the file cannot be read.
        """
        result = await FileLoader.aload(
            file_path,
            file_entry=file_entry,
            encoding=encoding,
            variables=variables,
        )

        content = result.content
        if isinstance(content, str):
            encode_with = result.encoding if result.encoding is not None else encoding
            content = content.encode(encode_with)

        mime = result.mime_type if result.mime_type else fallback_mime
        b64 = base64.b64encode(content).decode("utf-8")
        return f"data:{mime};base64,{b64}"
