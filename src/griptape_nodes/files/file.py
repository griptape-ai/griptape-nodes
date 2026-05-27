"""File path-like object for simplified file reading via the retained mode API."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import NamedTuple, Protocol, cast, runtime_checkable

from PIL import Image, UnidentifiedImageError

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
from griptape_nodes.retained_mode.file_metadata.sidecar_metadata import (
    SidecarContent,
    SituationMetadata,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


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
    PathResolutionFailureReason.RESERVED_NAME_COLLISION: FileIOFailureReason.INVALID_PATH,
}


def _resolve_file_path(file_path: str | MacroPath) -> str:
    """Resolve a file path, handling MacroPath resolution if needed.

    Args:
        file_path: A plain path string or a MacroPath.

    Returns:
        A resolved path string.

    Raises:
        FileLoadError: If macro resolution fails.
    """
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


async def _aresolve_file_path(file_path: str | MacroPath) -> str:
    """Async version of _resolve_file_path.

    Resolve a file path, handling MacroPath resolution if needed.

    Args:
        file_path: A plain path string or a MacroPath.

    Returns:
        A resolved path string.

    Raises:
        FileLoadError: If macro resolution fails.
    """
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


# Minimum bytes needed by the magic-byte sniffers below (ISO BMFF brand sits at offset 8-12).
_SNIFF_MIN_HEADER_BYTES = 12

# MPEG audio frame-sync markers used by _sniff_audio_extension.
_MPEG_FRAME_SYNC_BYTE = 0xFF
_MPEG_FRAME_SYNC_MASK = 0xE0
_MPEG_FRAME_SYNC_VALUE = 0xE0
_ADTS_SYNC_MASK = 0xF0
_ADTS_SYNC_VALUE = 0xF0
_MP3_LAYER_BYTES = (0xFB, 0xF3, 0xF2)

# Pairs of suffixes that should be treated as equivalent when comparing a
# user-supplied filename extension against the canonical extension reported by
# the sniffers. Keys and values are lowercase, no leading dot.
_EXTENSION_ALIASES: dict[str, str] = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "tif": "tiff",
    "tiff": "tiff",
    "m4v": "mp4",
    "mp4": "mp4",
}


def _canonical_extension(ext: str) -> str:
    """Return the canonical form of an on-disk extension for equivalence checks."""
    lowered = ext.lstrip(".").lower()
    return _EXTENSION_ALIASES.get(lowered, lowered)


def _sniff_image_extension(data: bytes) -> str | None:
    """Sniff a canonical image extension via PIL. Returns None if PIL can't identify."""
    try:
        with Image.open(BytesIO(data)) as img:
            fmt = img.format
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    if fmt is None:
        return None
    pil_to_extension: dict[str, str] = {
        "JPEG": "jpg",
        "PNG": "png",
        "WEBP": "webp",
        "GIF": "gif",
        "BMP": "bmp",
        "TIFF": "tiff",
        "ICO": "ico",
        "HEIF": "heic",
    }
    return pil_to_extension.get(fmt.upper())


def _sniff_video_extension(data: bytes) -> str | None:  # noqa: C901, PLR0911
    """Magic-byte sniff for common video container formats."""
    if len(data) < _SNIFF_MIN_HEADER_BYTES:
        return None
    head = data[:_SNIFF_MIN_HEADER_BYTES]
    # ISO BMFF: 'ftyp' at bytes 4-8, brand at bytes 8-12.
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        # Audio-only ISO BMFF brands are handled by the audio sniffer; skip here.
        if brand in (b"M4A ", b"M4B "):
            return None
        if brand == b"qt  ":
            return "mov"
        if brand in (b"M4V ", b"M4VH", b"M4VP"):
            return "m4v"
        # HEIC/HEIF are technically images; let the image sniffer claim them.
        if brand in (b"heic", b"heix", b"mif1", b"heim", b"heis"):
            return None
        return "mp4"
    # Matroska / WebM EBML header.
    if head[:4] == b"\x1aE\xdf\xa3":
        if b"webm" in data[:256]:
            return "webm"
        return "mkv"
    # AVI: RIFF....AVI .
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def _sniff_audio_extension(data: bytes) -> str | None:  # noqa: C901, PLR0911
    """Magic-byte sniff for common audio container/codec formats."""
    if len(data) < _SNIFF_MIN_HEADER_BYTES:
        return None
    head = data[:_SNIFF_MIN_HEADER_BYTES]
    if head[:3] == b"ID3":
        return "mp3"
    if head[0] == _MPEG_FRAME_SYNC_BYTE and (head[1] & _MPEG_FRAME_SYNC_MASK) == _MPEG_FRAME_SYNC_VALUE:
        return "mp3"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        if b"OpusHead" in data[:128]:
            return "opus"
        return "ogg"
    if head[4:8] == b"ftyp" and head[8:12] in (b"M4A ", b"M4B "):
        return "m4a"
    if head[:4] == b"\x1aE\xdf\xa3" and b"webm" in data[:256]:
        # WebM with audio-only stream is sniffable as webm; defer to video sniffer.
        return None
    if (
        head[0] == _MPEG_FRAME_SYNC_BYTE
        and (head[1] & _ADTS_SYNC_MASK) == _ADTS_SYNC_VALUE
        and head[1] not in _MP3_LAYER_BYTES
    ):
        return "aac"
    return None


def _sniff_extension(data: bytes) -> str | None:
    """Sniff a canonical on-disk extension from raw bytes.

    Tries image, video, and audio sniffers in turn. Returns None if none of
    them identifies the data; callers should treat that as "unknown bytes,
    write through" rather than an error.
    """
    return _sniff_image_extension(data) or _sniff_video_extension(data) or _sniff_audio_extension(data)


def _validate_extension_matches_bytes(file_path: str, content: str | bytes) -> None:
    """Raise ValueError if `content`'s sniffed extension disagrees with the path suffix.

    Validation is skipped when:
    - `content` is text (not bytes),
    - the path has no extension,
    - the bytes can't be identified by any sniffer (a warning is logged).

    Args:
        file_path: The resolved on-disk path the bytes will be written to.
        content: The bytes (or text) being written.

    Raises:
        ValueError: If the sniffed canonical extension disagrees with the
            extension on `file_path`.
    """
    if not isinstance(content, bytes):
        return

    suffix = Path(file_path).suffix.lstrip(".").lower()
    if not suffix:
        return

    sniffed = _sniff_extension(content)
    if sniffed is None:
        logger.warning(
            "Could not identify byte content for '%s'; writing through without extension validation.",
            file_path,
        )
        return

    if _canonical_extension(suffix) != _canonical_extension(sniffed):
        msg = (
            f"Refusing to write {sniffed.upper()} bytes to '{file_path}' "
            f"(extension '.{suffix}'). The file extension must match the byte content; "
            f"either rename the destination to '.{sniffed}' or supply bytes that match '.{suffix}'."
        )
        raise ValueError(msg)


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
        *,
        file_metadata: SidecarContent | None = None,
    ) -> None:
        """Store file reference. No I/O is performed.

        Plain strings containing macro variables (e.g. ``"{outputs}/file.png"``) are
        automatically wrapped in a MacroPath so they are resolved against the current
        project at read time.  Strings with no macro variables and already-constructed
        MacroPath objects are stored as-is.

        Args:
            file_path: Path to the file. Can be a plain string or a MacroPath
                (which contains macro variables).
            file_metadata: Optional caller-provided context to include in the sidecar
                metadata file alongside auto-collected workflow metadata.
        """
        self._file_metadata = file_metadata
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

    def resolve(self) -> str:
        """Resolve and return the absolute path string for this file.

        Useful when a caller needs the path for writing (not reading). Macro
        variables in the path are resolved against the current project at call time.

        Returns:
            Absolute path string.

        Raises:
            FileLoadError: If macro resolution fails (e.g. no project loaded).
        """
        return _resolve_file_path(self._file_path)

    @property
    def location(self) -> str:
        """Return the most portable string representation of this file's location.

        Returns the macro template (e.g. ``"{outputs}/image.png"``) when the file
        holds a macro path, otherwise the plain path string.  No I/O is performed.
        """
        if isinstance(self._file_path, MacroPath):
            return self._file_path.parsed_macro.template
        return self._file_path

    @property
    def name(self) -> str:
        """Return the filename component of this file's location.

        For example, a File holding ``"{outputs}/image.png"`` returns ``"image.png"``.
        """
        return Path(self.location).name

    def write_bytes(
        self,
        content: bytes,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> Path:
        """Write bytes to the file.

        The bytes are sniffed for a known media format. If the sniffed format
        disagrees with the file's extension, ``ValueError`` is raised before
        any I/O happens. If the bytes can't be identified, a warning is
        logged and the write proceeds unchanged.

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
            ValueError: If the bytes' sniffed format does not match the file
                extension.
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
    ) -> Path:
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
            ValueError: If the bytes' sniffed format does not match the file
                extension.
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
    ) -> Path:
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
    ) -> Path:
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
        request = ReadFileRequest(
            file_path=_resolve_file_path(self._file_path),
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
        request = ReadFileRequest(
            file_path=await _aresolve_file_path(self._file_path),
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
    ) -> Path:
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
            ValueError: If `content` is bytes whose sniffed format does not
                match the file extension.
        """
        resolved_path = _resolve_file_path(self._file_path)
        _validate_extension_matches_bytes(resolved_path, content)
        request = WriteFileRequest(
            file_path=resolved_path,
            content=content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
            file_metadata=self._build_file_metadata(),
        )
        result = GriptapeNodes.handle_request(request)

        if isinstance(result, WriteFileResultFailure):
            raise FileWriteError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
                missing_variables=result.missing_variables,
            )

        return Path(cast("WriteFileResultSuccess", result).final_file_path)

    async def _awrite_content(
        self,
        content: str | bytes,
        encoding: str = "utf-8",
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        append: bool = False,
        create_parents: bool = True,
    ) -> Path:
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
            ValueError: If `content` is bytes whose sniffed format does not
                match the file extension.
        """
        resolved_path = await _aresolve_file_path(self._file_path)
        _validate_extension_matches_bytes(resolved_path, content)
        request = WriteFileRequest(
            file_path=resolved_path,
            content=content,
            encoding=encoding,
            existing_file_policy=existing_file_policy,
            append=append,
            create_parents=create_parents,
            file_metadata=self._build_file_metadata(),
        )
        result = await GriptapeNodes.ahandle_request(request)

        if isinstance(result, WriteFileResultFailure):
            raise FileWriteError(
                failure_reason=result.failure_reason,
                result_details=str(result.result_details),
                missing_variables=result.missing_variables,
            )

        return Path(cast("WriteFileResultSuccess", result).final_file_path)

    def _build_file_metadata(self) -> SidecarContent | None:
        """Build SidecarContent from MacroPath variables and caller-provided metadata.

        Caller-provided metadata takes full precedence. If only a MacroPath is present
        (no caller metadata), the macro template and variables are captured as a minimal
        SituationMetadata.
        """
        if self._file_metadata is not None:
            return self._file_metadata
        if isinstance(self._file_path, MacroPath):
            return SidecarContent(
                situation=SituationMetadata(
                    macro=self._file_path.parsed_macro.template,
                    variables={k: str(v) for k, v in self._file_path.variables.items()},
                ),
            )
        return None


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
        file_metadata: SidecarContent | None = None,
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
            file_metadata: Optional caller-provided context to include in the sidecar
                metadata file alongside auto-collected workflow metadata.
        """
        self._file = File(file_path, file_metadata=file_metadata)
        self._existing_file_policy = existing_file_policy
        self._append = append
        self._create_parents = create_parents

    def resolve(self) -> str:
        """Resolve and return the absolute path string for this destination.

        Returns:
            Absolute path string.

        Raises:
            FileLoadError: If macro resolution fails (e.g. no project loaded).
        """
        return self._file.resolve()

    @property
    def location(self) -> str:
        return self._file.location

    @property
    def name(self) -> str:
        return self._file.name

    def write_bytes(self, content: bytes) -> File:
        """Write bytes to the file using the configured write policy.

        Args:
            content: The bytes to write.

        Returns:
            A File referencing the path where the content was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        path = self._file.write_bytes(
            content,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )
        return File(str(path))

    async def awrite_bytes(self, content: bytes) -> File:
        """Async version of write_bytes().

        Args:
            content: The bytes to write.

        Returns:
            A File referencing the path where the content was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        path = await self._file.awrite_bytes(
            content,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )
        return File(str(path))

    def write_text(self, content: str, encoding: str = "utf-8") -> File:
        """Write text to the file using the configured write policy.

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.

        Returns:
            A File referencing the path where the content was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        path = self._file.write_text(
            content,
            encoding,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )
        return File(str(path))

    async def awrite_text(self, content: str, encoding: str = "utf-8") -> File:
        """Async version of write_text().

        Args:
            content: The text to write.
            encoding: Text encoding to use when writing.

        Returns:
            A File referencing the path where the content was written.

        Raises:
            FileWriteError: If the file cannot be written.
        """
        path = await self._file.awrite_text(
            content,
            encoding,
            existing_file_policy=self._existing_file_policy,
            append=self._append,
            create_parents=self._create_parents,
        )
        return File(str(path))


@runtime_checkable
class FileDestinationProvider(Protocol):
    """Protocol for nodes that provide a FileDestination without serializing it over the wire."""

    @property
    def file_destination(self) -> FileDestination | None: ...


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
    mime = fc.mime_type or fallback_mime
    raw_bytes = _to_bytes(fc)
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"
