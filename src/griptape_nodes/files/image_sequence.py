"""ImageSequence - a collection of images identified by a frame-number pattern."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.files.directory import Directory
from griptape_nodes.files.file import File, FileDestination
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from collections.abc import Callable

_FRAME_VAR_NAME = "frame"
_HASH_PATTERN = re.compile(r"#+")
_FRAME_MACRO_PATTERN = re.compile(r"\{frame(?::(\d+))?\}")
_MAX_VERSION_INDEX = 9999


class ImageSequenceError(Exception):
    """Raised when an image sequence operation fails."""

    def __init__(self, result_details: str) -> None:
        self.result_details = result_details
        super().__init__(result_details)


class ImageSequence:
    """A collection of images identified by a frame-number pattern.

    Internally stores a MacroPath template with a ``{frame:04}`` variable slot.
    Exposes the industry-standard ``####`` notation at property boundaries for
    DCC software interop.

    Use ``frame(n)`` to get a ``File`` for reading a specific frame, and
    ``directory`` to get the containing folder.
    """

    def __init__(self, frame_macro: MacroPath) -> None:
        """Store the frame macro. No I/O is performed.

        Args:
            frame_macro: MacroPath whose template contains a ``{frame}`` variable
                slot and whose variables dict holds all resolved values (including
                a locked ``_index`` when versioning is in effect).
        """
        self._frame_macro = frame_macro

    @property
    def location(self) -> str:
        """Return the raw macro template for wire serialization.

        Example: ``"{outputs}/Render_frames_v001/{frame:04}.exr"``
        """
        return self._frame_macro.parsed_macro.template

    @property
    def pattern(self) -> str:
        """Return the #### notation form of this sequence's frame pattern.

        The ``{frame:NN}`` macro variable is replaced with a run of ``#``
        characters matching the padding width.

        Example: ``"{outputs}/renders_v001/frame_####.exr"``
        """
        return frame_macro_to_hash_pattern(self.location)

    @property
    def directory(self) -> Directory:
        """Return the containing directory as a Directory.

        No I/O is performed; the directory path is derived from the macro
        template by stripping the filename component.
        """
        dir_location = str(Path(self.location).parent)
        return Directory(dir_location)

    def frame(self, frame_number: int) -> File:
        """Return a File for reading a specific frame.

        Args:
            frame_number: Frame index (caller's convention, e.g. 0-based or 1-based).

        Returns:
            File that resolves to the absolute path of that frame.
        """
        variables = {**self._frame_macro.variables, _FRAME_VAR_NAME: frame_number}
        return File(MacroPath(self._frame_macro.parsed_macro, variables))


class _FrameWriteDestination(ProjectFileDestination):
    """FileDestination subclass that fires a callback after each successful write."""

    def __init__(
        self,
        frame_path: MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy,
        create_parents: bool,
        on_written: Callable[[File], None],
    ) -> None:
        super().__init__(
            frame_path,
            existing_file_policy=existing_file_policy,
            create_parents=create_parents,
        )
        self._on_written = on_written

    def write_bytes(self, content: bytes) -> File:
        result = super().write_bytes(content)
        self._on_written(result)
        return result

    async def awrite_bytes(self, content: bytes) -> File:
        result = await super().awrite_bytes(content)
        self._on_written(result)
        return result

    def write_text(self, content: str, encoding: str = "utf-8") -> File:
        result = super().write_text(content, encoding)
        self._on_written(result)
        return result

    async def awrite_text(self, content: str, encoding: str = "utf-8") -> File:
        result = await super().awrite_text(content, encoding)
        self._on_written(result)
        return result


class ImageSequenceDestination:
    """A pre-configured write handle for an image sequence.

    Bundles a frame macro path and write policy. The caller resolves a
    version index once (via ``build_versioned_sequence_destination``), then
    calls ``frame(n)`` to get a ``FileDestination`` for each frame.

    The ``image_sequence`` property becomes non-None after the first frame write.
    """

    def __init__(
        self,
        frame_macro: MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        create_parents: bool = True,
    ) -> None:
        """Store frame macro and write configuration. No I/O is performed.

        Args:
            frame_macro: MacroPath with template containing a ``{frame}`` variable.
                Should already have ``_index`` locked in the variables dict.
            existing_file_policy: How to handle existing frame files. Defaults to OVERWRITE.
            create_parents: If True, create parent directories automatically. Defaults to True.
        """
        self._frame_macro = frame_macro
        self._existing_file_policy = existing_file_policy
        self._create_parents = create_parents
        self._written_sequence: ImageSequence | None = None

    @property
    def image_sequence(self) -> ImageSequence | None:
        """Return the ImageSequence descriptor after at least one frame has been written.

        Returns None before any frame write.
        """
        return self._written_sequence

    def frame(self, frame_number: int) -> FileDestination:
        """Return a FileDestination for writing a specific frame.

        After the returned destination is used to write, the ``image_sequence``
        property becomes available.

        Args:
            frame_number: Frame index to write.

        Returns:
            FileDestination pre-configured with the resolved frame path and policy.
        """
        variables = {**self._frame_macro.variables, _FRAME_VAR_NAME: frame_number}
        frame_path = MacroPath(self._frame_macro.parsed_macro, variables)
        return _FrameWriteDestination(
            frame_path,
            existing_file_policy=self._existing_file_policy,
            create_parents=self._create_parents,
            on_written=self._on_frame_written,
        )

    def _on_frame_written(self, written_file: File) -> None:  # noqa: ARG002
        """Record that a frame was written to expose the ImageSequence descriptor."""
        if self._written_sequence is None:
            self._written_sequence = ImageSequence(self._frame_macro)


def build_versioned_sequence_destination(
    frame_macro: MacroPath,
    *,
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
    create_parents: bool = True,
) -> ImageSequenceDestination:
    """Find the first available version index and return a locked ImageSequenceDestination.

    Increments ``_index`` in the frame macro starting at 1 until the corresponding
    parent directory does not exist. Returns an ``ImageSequenceDestination`` with
    that index locked into the variables dict.

    Args:
        frame_macro: MacroPath template with ``{frame}`` and ``{_index}`` variables.
        existing_file_policy: Policy for individual frame files. Defaults to OVERWRITE.
        create_parents: Whether to create parent directories. Defaults to True.

    Returns:
        ImageSequenceDestination with a locked _index version.

    Raises:
        ImageSequenceError: If no available version is found within the limit.
    """
    for index in range(1, _MAX_VERSION_INDEX + 1):
        probe_variables = {**frame_macro.variables, "_index": index, _FRAME_VAR_NAME: 0}
        resolve_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(parsed_macro=frame_macro.parsed_macro, variables=probe_variables)
        )
        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            msg = f"Attempted to find available sequence version. Failed to resolve macro: {resolve_result.result_details}"
            raise ImageSequenceError(msg)

        parent_dir = resolve_result.absolute_path.parent
        if not parent_dir.exists():
            locked_vars = {**frame_macro.variables, "_index": index}
            locked_macro = MacroPath(frame_macro.parsed_macro, locked_vars)
            return ImageSequenceDestination(
                locked_macro,
                existing_file_policy=existing_file_policy,
                create_parents=create_parents,
            )

    msg = f"Attempted to find available sequence version. Failed because no path found after {_MAX_VERSION_INDEX} attempts."
    raise ImageSequenceError(msg)


def hash_pattern_to_frame_macro(pattern: str) -> str:
    """Convert a #### frame pattern to a macro template with {frame:NN} syntax.

    Args:
        pattern: Pattern string like ``"render_####.exr"`` or ``"frame_##.png"``.

    Returns:
        Macro template string like ``"render_{frame:04}.exr"``.
    """

    def replace_hashes(match: re.Match) -> str:
        width = len(match.group())
        return f"{{frame:{width:02d}}}"

    return _HASH_PATTERN.sub(replace_hashes, pattern)


def frame_macro_to_hash_pattern(template: str) -> str:
    """Convert a macro template with {frame:NN} syntax to a #### pattern.

    Args:
        template: Macro template like ``"render_{frame:04}.exr"``.

    Returns:
        Pattern string like ``"render_####.exr"``.
    """

    def replace_frame_var(match: re.Match) -> str:
        width_str = match.group(1)
        width = int(width_str) if width_str else 4
        return "#" * width

    return _FRAME_MACRO_PATTERN.sub(replace_frame_var, template)
