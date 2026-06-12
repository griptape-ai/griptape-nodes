"""FileSequence and FileSequenceDestination for numbered file collections (frames, audio takes, etc.).

Entry macros like ``{outputs}/dialogue_v{_index:03}/{entry:04}.wav`` drive both reading
(FileSequence) and writing (FileSequenceDestination). Scanning delegates to the engine via
ScanSequencesRequest; versioned destinations lock a free directory index via
build_versioned_sequence_destination.
"""

from __future__ import annotations

import pathlib
import re
import typing

from fileseq import constants as fileseq_constants
from fileseq import filesequence as fileseq_filesequence

from griptape_nodes.common import macro_parser, sequences
from griptape_nodes.files import directory as directory_mod
from griptape_nodes.files import file as file_mod
from griptape_nodes.files import project_file
from griptape_nodes.retained_mode import griptape_nodes as griptape_nodes_mod
from griptape_nodes.retained_mode.events import os_events, project_events

if typing.TYPE_CHECKING:
    import collections.abc

_ENTRY_VAR_NAME = "entry"
_ENTRY_MACRO_PATTERN = re.compile(r"\{entry(?::(\d+))?\}")


class FileSequenceError(Exception):
    """Raised when a file sequence operation fails."""

    def __init__(self, result_details: str) -> None:
        self.result_details = result_details
        super().__init__(result_details)


class FileSequence:
    """A collection of files identified by an entry-number pattern.

    Internally stores a MacroPath template with a ``{entry:XX}`` variable slot.
    Exposes the industry-standard ``####`` notation at property boundaries for
    DCC software interop.

    Use ``entry(n)`` to get a ``File`` for reading a specific entry, and
    ``directory`` to get the containing folder.
    """

    def __init__(self, entry_macro: project_events.MacroPath) -> None:
        """Store the entry macro. No I/O is performed.

        Args:
            entry_macro: MacroPath whose template contains an ``{entry}`` variable
                slot and whose variables dict holds all resolved values (including
                a locked ``_index`` when versioning is in effect).
        """
        self._entry_macro = entry_macro

    @property
    def location(self) -> str:
        """Return the raw macro template for this sequence.

        Unresolved placeholders (including ``{_index}`` when versioning is in
        effect) remain in the returned string. Use ``_entry_macro`` directly
        when a self-contained (template + locked variables) representation is
        needed for serialisation.

        Example: ``"{outputs}/dialogue_v{_index:03}/{entry:04}.wav"``
        """
        return self._entry_macro.parsed_macro.template

    @property
    def pattern(self) -> str:
        """Return the #### notation form of this sequence's entry pattern.

        The ``{entry:NN}`` macro variable is replaced with a run of ``#``
        characters matching the padding width. Other placeholders (e.g.
        ``{_index}``) remain unresolved.

        Example: ``"{outputs}/dialogue_v{_index:03}/####.wav"``
        """
        return entry_macro_to_hash_pattern(self.location)

    @property
    def directory(self) -> directory_mod.Directory:
        """Return the containing directory as a Directory.

        No I/O is performed; the directory path is derived from the macro
        template by stripping the filename component. The locked variables
        (e.g. ``_index``) are preserved so the returned Directory can be resolved.
        """
        dir_template = str(pathlib.PurePosixPath(self.location).parent)
        dir_variables = {k: v for k, v in self._entry_macro.variables.items() if k != _ENTRY_VAR_NAME}
        return directory_mod.Directory(project_events.MacroPath(macro_parser.ParsedMacro(dir_template), dir_variables))

    def entry(self, entry_number: int) -> file_mod.File:
        """Return a File for reading a specific entry.

        Args:
            entry_number: Entry index (caller's convention, e.g. 0-based or 1-based).

        Returns:
            File that resolves to the absolute path of that entry.
        """
        variables = {**self._entry_macro.variables, _ENTRY_VAR_NAME: entry_number}
        return file_mod.File(project_events.MacroPath(self._entry_macro.parsed_macro, variables))

    def scan(
        self,
        *,
        policy: sequences.MissingItemPolicy = sequences.MissingItemPolicy.SPLIT,
        start: int | None = None,
        end: int | None = None,
    ) -> list[sequences.Sequence]:
        """Scan the sequence directory and return what's on disk.

        Args:
            policy: How to handle gaps in the number range. Defaults to SPLIT.
            start: Optional lower bound (inclusive) for the active subset.
            end: Optional upper bound (inclusive) for the active subset.

        Returns:
            List of Sequence objects. Empty if the directory cannot be resolved
            or contains no matching files.
        """
        probe_vars = {**self._entry_macro.variables, _ENTRY_VAR_NAME: 0}
        resolve_result = griptape_nodes_mod.GriptapeNodes.handle_request(
            project_events.GetPathForMacroRequest(parsed_macro=self._entry_macro.parsed_macro, variables=probe_vars)
        )
        if not isinstance(resolve_result, project_events.GetPathForMacroResultSuccess):
            return []
        resolved_dir = str(resolve_result.absolute_path.parent)
        filename_template = pathlib.PurePosixPath(self.location).name
        entry_match = _ENTRY_MACRO_PATTERN.search(filename_template)
        entry_width = int(entry_match.group(1)) if entry_match and entry_match.group(1) else 4
        entry_zero_str = format(0, f"0{entry_width}d")
        filename_pattern = resolve_result.absolute_path.name.replace(entry_zero_str, "#" * entry_width, 1)
        scan_result = griptape_nodes_mod.GriptapeNodes.handle_request(
            os_events.ScanSequencesRequest(
                directory=resolved_dir,
                pattern=filename_pattern,
                policy=policy,
                start_number=start,
                end_number=end,
            )
        )
        if not isinstance(scan_result, os_events.ScanSequencesResultSuccess):
            return []
        return scan_result.sequences


class _EntryWriteDestination(project_file.ProjectFileDestination):
    """FileDestination subclass that fires a callback after each successful write."""

    def __init__(
        self,
        entry_path: project_events.MacroPath,
        *,
        existing_file_policy: os_events.ExistingFilePolicy,
        create_parents: bool,
        on_written: collections.abc.Callable[[file_mod.File], None],
    ) -> None:
        super().__init__(
            entry_path,
            existing_file_policy=existing_file_policy,
            create_parents=create_parents,
        )
        self._on_written = on_written

    def write_bytes(self, content: bytes) -> file_mod.File:
        result = super().write_bytes(content)
        self._on_written(result)
        return result

    async def awrite_bytes(self, content: bytes) -> file_mod.File:
        result = await super().awrite_bytes(content)
        self._on_written(result)
        return result

    def write_text(self, content: str, encoding: str = "utf-8") -> file_mod.File:
        result = super().write_text(content, encoding)
        self._on_written(result)
        return result

    async def awrite_text(self, content: str, encoding: str = "utf-8") -> file_mod.File:
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
        entry_macro: project_events.MacroPath,
        *,
        existing_file_policy: os_events.ExistingFilePolicy = os_events.ExistingFilePolicy.OVERWRITE,
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

    def entry(self, entry_number: int) -> file_mod.FileDestination:
        """Return a FileDestination for writing a specific entry.

        After the returned destination is used to write, the ``file_sequence``
        property becomes available.

        Args:
            entry_number: Entry index to write.

        Returns:
            FileDestination pre-configured with the resolved entry path and policy.
        """
        variables = {**self._entry_macro.variables, _ENTRY_VAR_NAME: entry_number}
        entry_path = project_events.MacroPath(self._entry_macro.parsed_macro, variables)
        return _EntryWriteDestination(
            entry_path,
            existing_file_policy=self._existing_file_policy,
            create_parents=self._create_parents,
            on_written=self._on_entry_written,
        )

    def _on_entry_written(self, written_file: file_mod.File) -> None:  # noqa: ARG002
        """Record that an entry was written to expose the FileSequence descriptor."""
        if self._written_sequence is None:
            self._written_sequence = FileSequence(self._entry_macro)


def build_versioned_sequence_destination(
    entry_macro: project_events.MacroPath,
    *,
    existing_file_policy: os_events.ExistingFilePolicy = os_events.ExistingFilePolicy.OVERWRITE,
    create_parents: bool = True,
) -> FileSequenceDestination:
    """Find the next available version index and return a locked FileSequenceDestination.

    Delegates index discovery to GetNextVersionIndexRequest (a single glob pass),
    then locks the returned index into the entry macro variables.

    Args:
        entry_macro: MacroPath template with ``{entry}`` and ``{_index}`` variables.
        existing_file_policy: Policy for individual entry files. Defaults to OVERWRITE.
        create_parents: Whether to create parent directories. Defaults to True.

    Returns:
        FileSequenceDestination with a locked _index version.

    Raises:
        FileSequenceError: If the engine cannot determine the next available version index.
    """
    dir_template = str(pathlib.PurePosixPath(entry_macro.parsed_macro.template).parent)
    dir_variables = {k: v for k, v in entry_macro.variables.items() if k != _ENTRY_VAR_NAME}
    dir_macro = project_events.MacroPath(macro_parser.ParsedMacro(dir_template), dir_variables)

    index_result = griptape_nodes_mod.GriptapeNodes.handle_request(
        os_events.GetNextVersionIndexRequest(macro_path=dir_macro)
    )
    if not isinstance(index_result, os_events.GetNextVersionIndexResultSuccess):
        msg = (
            f"Attempted to find available sequence version. Failed to find version index: {index_result.result_details}"
        )
        raise FileSequenceError(msg)

    index = index_result.index if index_result.index is not None else 1
    locked_vars = {**entry_macro.variables, "_index": index}
    locked_macro = project_events.MacroPath(entry_macro.parsed_macro, locked_vars)
    return FileSequenceDestination(
        locked_macro,
        existing_file_policy=existing_file_policy,
        create_parents=create_parents,
    )


def hash_pattern_to_entry_macro(pattern: str) -> str:
    """Convert a sequence token pattern to a macro template with {entry:NN} syntax.

    Accepts all fileseq token forms: ``####``, ``%04d``, ``@@@@``, ``$F4``.

    Args:
        pattern: Pattern string like ``"render_####.exr"``, ``"render_%04d.exr"``,
            or a full path like ``"{outputs}/renders/render_####.exr"``.

    Returns:
        Macro template string with the token replaced by ``{entry:NN}``. Returns
        the input unchanged if no sequence token is found.
    """
    path = pathlib.PurePosixPath(pattern)
    fseq = fileseq_filesequence.FileSequence(path.name, pad_style=fileseq_constants.PAD_STYLE_HASH1)
    width = fseq.zfill()
    if width == 0:
        return pattern
    entry_part = f"{{entry:{width:02}}}"
    new_name = fseq.basename() + entry_part + fseq.extension()
    parent = str(path.parent)
    return f"{parent}/{new_name}" if parent != "." else new_name


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
