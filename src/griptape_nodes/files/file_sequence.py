"""FileSequence - a collection of files identified by an entry-number pattern."""

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

_ENTRY_VAR_NAME = "entry"
_HASH_PATTERN = re.compile(r"#+")
_ENTRY_MACRO_PATTERN = re.compile(r"\{entry(?::(\d+))?\}")
_MAX_VERSION_INDEX = 9999


class FileSequenceError(Exception):
    """Raised when a file sequence operation fails."""

    def __init__(self, result_details: str) -> None:
        self.result_details = result_details
        super().__init__(result_details)


class FileSequence:
    """A collection of files identified by an entry-number pattern.

    Internally stores a MacroPath template with a ``{entry:04}`` variable slot.
    Exposes the industry-standard ``####`` notation at property boundaries for
    DCC software interop.

    Use ``entry(n)`` to get a ``File`` for reading a specific entry, and
    ``directory`` to get the containing folder.
    """

    def __init__(self, entry_macro: MacroPath) -> None:
        """Store the entry macro. No I/O is performed.

        Args:
            entry_macro: MacroPath whose template contains an ``{entry}`` variable
                slot and whose variables dict holds all resolved values (including
                a locked ``_index`` when versioning is in effect).
        """
        self._entry_macro = entry_macro

    @property
    def location(self) -> str:
        """Return the raw macro template for wire serialisation.

        Example: ``"{outputs}/dialogue_v001/{entry:04}.wav"``
        """
        return self._entry_macro.parsed_macro.template

    @property
    def pattern(self) -> str:
        """Return the #### notation form of this sequence's entry pattern.

        The ``{entry:NN}`` macro variable is replaced with a run of ``#``
        characters matching the padding width.

        Example: ``"{outputs}/renders_v001/frame_####.exr"``
        """
        return entry_macro_to_hash_pattern(self.location)

    @property
    def directory(self) -> Directory:
        """Return the containing directory as a Directory.

        No I/O is performed; the directory path is derived from the macro
        template by stripping the filename component.
        """
        dir_location = str(Path(self.location).parent)
        return Directory(dir_location)

    def entry(self, entry_number: int) -> File:
        """Return a File for reading a specific entry.

        Args:
            entry_number: Entry index (caller's convention, e.g. 0-based or 1-based).

        Returns:
            File that resolves to the absolute path of that entry.
        """
        variables = {**self._entry_macro.variables, _ENTRY_VAR_NAME: entry_number}
        return File(MacroPath(self._entry_macro.parsed_macro, variables))


class _EntryWriteDestination(ProjectFileDestination):
    """FileDestination subclass that fires a callback after each successful write."""

    def __init__(
        self,
        entry_path: MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy,
        create_parents: bool,
        on_written: Callable[[File], None],
    ) -> None:
        super().__init__(
            entry_path,
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


class FileSequenceDestination:
    """A pre-configured write handle for a file sequence.

    Bundles an entry macro path and write policy. The caller resolves a
    version index once (via ``build_versioned_sequence_destination``), then
    calls ``entry(n)`` to get a ``FileDestination`` for each entry.

    The ``file_sequence`` property becomes non-None after the first entry write.
    """

    def __init__(
        self,
        entry_macro: MacroPath,
        *,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        create_parents: bool = True,
    ) -> None:
        """Store entry macro and write configuration. No I/O is performed.

        Args:
            entry_macro: MacroPath with template containing an ``{entry}`` variable.
                Should already have ``_index`` locked in the variables dict.
            existing_file_policy: How to handle existing entry files. Defaults to OVERWRITE.
            create_parents: If True, create parent directories automatically. Defaults to True.
        """
        self._entry_macro = entry_macro
        self._existing_file_policy = existing_file_policy
        self._create_parents = create_parents
        self._written_sequence: FileSequence | None = None

    @property
    def file_sequence(self) -> FileSequence | None:
        """Return the FileSequence descriptor after at least one entry has been written.

        Returns None before any entry write.
        """
        return self._written_sequence

    def entry(self, entry_number: int) -> FileDestination:
        """Return a FileDestination for writing a specific entry.

        After the returned destination is used to write, the ``file_sequence``
        property becomes available.

        Args:
            entry_number: Entry index to write.

        Returns:
            FileDestination pre-configured with the resolved entry path and policy.
        """
        variables = {**self._entry_macro.variables, _ENTRY_VAR_NAME: entry_number}
        entry_path = MacroPath(self._entry_macro.parsed_macro, variables)
        return _EntryWriteDestination(
            entry_path,
            existing_file_policy=self._existing_file_policy,
            create_parents=self._create_parents,
            on_written=self._on_entry_written,
        )

    def _on_entry_written(self, written_file: File) -> None:  # noqa: ARG002
        """Record that an entry was written to expose the FileSequence descriptor."""
        if self._written_sequence is None:
            self._written_sequence = FileSequence(self._entry_macro)


def build_versioned_sequence_destination(
    entry_macro: MacroPath,
    *,
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
    create_parents: bool = True,
) -> FileSequenceDestination:
    """Find the first available version index and return a locked FileSequenceDestination.

    Increments ``_index`` in the entry macro starting at 1 until the corresponding
    parent directory does not exist. Returns a ``FileSequenceDestination`` with
    that index locked into the variables dict.

    Args:
        entry_macro: MacroPath template with ``{entry}`` and ``{_index}`` variables.
        existing_file_policy: Policy for individual entry files. Defaults to OVERWRITE.
        create_parents: Whether to create parent directories. Defaults to True.

    Returns:
        FileSequenceDestination with a locked _index version.

    Raises:
        FileSequenceError: If no available version is found within the limit.
    """
    for index in range(1, _MAX_VERSION_INDEX + 1):
        probe_variables = {**entry_macro.variables, "_index": index, _ENTRY_VAR_NAME: 0}
        resolve_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(parsed_macro=entry_macro.parsed_macro, variables=probe_variables)
        )
        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            msg = f"Attempted to find available sequence version. Failed to resolve macro: {resolve_result.result_details}"
            raise FileSequenceError(msg)

        parent_dir = resolve_result.absolute_path.parent
        if not parent_dir.exists():
            locked_vars = {**entry_macro.variables, "_index": index}
            locked_macro = MacroPath(entry_macro.parsed_macro, locked_vars)
            return FileSequenceDestination(
                locked_macro,
                existing_file_policy=existing_file_policy,
                create_parents=create_parents,
            )

    msg = f"Attempted to find available sequence version. Failed because no path found after {_MAX_VERSION_INDEX} attempts."
    raise FileSequenceError(msg)


def hash_pattern_to_entry_macro(pattern: str) -> str:
    """Convert a #### entry pattern to a macro template with {entry:NN} syntax.

    Args:
        pattern: Pattern string like ``"render_####.exr"`` or ``"frame_##.png"``.

    Returns:
        Macro template string like ``"render_{entry:04}.exr"``.
    """

    def replace_hashes(match: re.Match) -> str:
        width = len(match.group())
        return f"{{entry:{width:02d}}}"

    return _HASH_PATTERN.sub(replace_hashes, pattern)


def entry_macro_to_hash_pattern(template: str) -> str:
    """Convert a macro template with {entry:NN} syntax to a #### pattern.

    Args:
        template: Macro template like ``"render_{entry:04}.exr"``.

    Returns:
        Pattern string like ``"render_####.exr"``.
    """

    def replace_entry_var(match: re.Match) -> str:
        width_str = match.group(1)
        width = int(width_str) if width_str else 4
        return "#" * width

    return _ENTRY_MACRO_PATTERN.sub(replace_entry_var, template)
