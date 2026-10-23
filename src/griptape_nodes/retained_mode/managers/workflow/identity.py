"""Workflow ids for files being registered: derived ids, and settling two files that carry one id.

A workflow file carries its permanent id in its header. Files written before ids existed carry
none, and get one derived from where they are until their next save writes it; this never writes
them. Two different files with one id are a user's copy of a stamped file. The registration scan
settles that once: one file keeps the id, and the other is given a fresh one, written into its
header there and then. That restamp is the only write a scan makes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.files.path_utils import (
    canonicalize_for_identity,
    canonicalize_for_identity_preserving_symlinks,
    is_same_file,
)
from griptape_nodes.files.project_file import ProjectFileDestination
from griptape_nodes.node_library.workflow_registry import (
    DuplicateWorkflowIdError,
    Workflow,
    WorkflowMetadata,
    WorkflowMetadataError,
    derive_library_workflow_id_for_file,
    derive_workflow_id_for_path,
    new_workflow_id,
    read_workflow_metadata,
)
from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger("griptape_nodes")


class _LibraryRoot(NamedTuple):
    """A registered library's directory, as named and with links followed."""

    library_name: str
    root: Path
    followed_root: Path


class _DuplicateCandidate(NamedTuple):
    """One file in a group of files that carry the same id."""

    path: Path
    is_writable: bool
    held_id_before_refresh: bool
    birth_time: float | None


class _KeepsIdOrder(NamedTuple):
    """Sort key for a duplicate group: the smallest keeps the id."""

    is_writable: bool
    did_not_hold_id_before_refresh: bool
    birth_time: float
    path: str


class WorkflowIdentity(EngineScoped):
    def register_file(self, path: str | Path, metadata: WorkflowMetadata, *, listed: bool = True) -> Workflow:
        """Register a workflow file, settling an id another registered file already holds.

        The registered file keeps the id: it is the one open tabs and references already know.
        This file gets a fresh id written into its header, or, when it cannot be written, the id
        derived from its path.

        Raises:
            ValueError: The file is not on disk.
            WorkflowPathTakenError: Another entry holds the path, or the name derived from it.
        """
        registry = self.engine.workflow_registry
        library_roots = self._library_roots()
        metadata = self._with_library_id(path, metadata, library_roots)
        try:
            return registry.register_file(path, metadata, listed=listed)
        except DuplicateWorkflowIdError as err:
            holder_path = err.existing.absolute_path
        absolute_path = self._absolute_path(path)
        settled_metadata = self._settle_loser(absolute_path, metadata, holder_path, library_roots)
        return registry.register_file(path, settled_metadata, listed=listed)

    def settle_duplicates_in_scan(
        self,
        metadata_by_file: dict[Path, WorkflowMetadata],
        previous_paths_by_id: Mapping[str, Path],
    ) -> None:
        """Settle every id that more than one file in a scan carries, before any of them registers.

        Updates `metadata_by_file` in place: each losing file's entry carries the id it now has.
        Paths to one file (`os.path.samefile`) are aliases, not duplicates, and are left alone.

        An id a registered workflow already holds (the open workflow, kept through a refresh) is
        left to registration, where that workflow keeps it. Otherwise one file keeps the id,
        chosen in this order:
        1. A file that cannot be written, since it cannot be restamped.
        2. The file that held the id before this refresh (`previous_paths_by_id`).
        3. The file created first (birth time), since a copy is the newer file. Where any file's
           birth time is unavailable (most Linux filesystems), the smallest path.
        """
        library_roots = self._library_roots()
        files_by_id: dict[str, list[Path]] = {}
        for workflow_file, metadata in metadata_by_file.items():
            settled = self._with_library_id(workflow_file, metadata, library_roots)
            metadata_by_file[workflow_file] = settled
            if settled.workflow_id is None:
                continue
            files_by_id.setdefault(settled.workflow_id, []).append(workflow_file)

        registry = self.engine.workflow_registry
        for workflow_id, workflow_files in files_by_id.items():
            # A workflow still registered (the open one, kept through a refresh) keeps its id;
            # registering each of these files settles them against it, one at a time.
            if registry.find_by_id(workflow_id) is not None:
                continue
            distinct_files = self._without_aliases(workflow_files)
            if len(distinct_files) < 2:  # noqa: PLR2004 - a duplicate needs two files
                continue
            previous_path = previous_paths_by_id.get(workflow_id)
            winner = self._pick_winner(distinct_files, metadata_by_file, previous_path, library_roots)
            for workflow_file in distinct_files:
                if workflow_file == winner:
                    continue
                metadata_by_file[workflow_file] = self._settle_loser(
                    self._absolute_path(workflow_file), metadata_by_file[workflow_file], winner, library_roots
                )

    def _with_library_id(
        self, path: str | Path, metadata: WorkflowMetadata, library_roots: list[_LibraryRoot]
    ) -> WorkflowMetadata:
        """Give a library workflow without an id the one derived from its library, or return `metadata` as is.

        Library workflows are never written, so their id is derived from what survives a
        reinstall: the library's name and the file's path inside it.
        """
        if metadata.workflow_id is not None:
            return metadata
        absolute_path = self._absolute_path(path)
        library_root = _library_root_containing(absolute_path, library_roots)
        if library_root is None:
            return metadata
        library_id = derive_library_workflow_id_for_file(library_root.library_name, library_root.root, absolute_path)
        if library_id is None:
            return metadata
        return metadata.model_copy(update={"workflow_id": library_id})

    def _settle_loser(
        self,
        loser_path: Path,
        metadata: WorkflowMetadata,
        winner_path: Path | None,
        library_roots: list[_LibraryRoot],
    ) -> WorkflowMetadata:
        """Give the file that lost an id a new one, and return its metadata carrying it.

        Only the engine that owns the workspace writes the new id. Workers and short-lived engines
        beside a live orchestrator scan the same files, and a write from them would race the
        orchestrator's and leave the two with different ids. They use the derived id instead.
        """
        derived_id = derive_workflow_id_for_path(loser_path)
        if not self.engine.library_manager.owns_workspace:
            logger.debug(
                "Workflow '%s' has the same workflow id as '%s'. Leaving it for the engine that owns the "
                "workspace to give it a new id, and using an id derived from its path here.",
                loser_path,
                winner_path,
            )
            return metadata.model_copy(update={"workflow_id": derived_id})

        if self._is_writable(loser_path, metadata, library_roots):
            restamped = self._restamp(loser_path)
            if restamped is not None:
                logger.info(
                    "Workflow '%s' had the same workflow id as '%s', so it was given a new id.",
                    loser_path,
                    winner_path,
                )
                return metadata.model_copy(update={"workflow_id": restamped})

        logger.warning(
            "Workflow '%s' has the same workflow id as '%s' and could not be given a new id. "
            "Using an id derived from its path instead.",
            loser_path,
            winner_path,
        )
        return metadata.model_copy(update={"workflow_id": derived_id})

    def _restamp(self, workflow_file: Path) -> str | None:
        """Write a fresh id into the file's header and return it, or None if the file could not be rewritten.

        Reads the header from the file rather than taking the scan's metadata, which the load
        checks may have filled in (missing dates), so only the id changes on disk.
        """
        try:
            file_metadata = read_workflow_metadata(workflow_file)
            content = workflow_file.read_text(encoding="utf-8")
        except (WorkflowMetadataError, OSError, UnicodeDecodeError) as err:
            logger.warning("Could not read workflow '%s' to give it a new id: %s", workflow_file, err)
            return None

        fresh_id = new_workflow_id()
        restamped_content = self.engine.workflow_manager.codegen.replace_workflow_metadata_header(
            content, file_metadata.model_copy(update={"workflow_id": fresh_id})
        )
        if restamped_content is None:
            return None
        write_result = self.engine.workflow_manager.saver.write_workflow_file(
            ProjectFileDestination(str(workflow_file), existing_file_policy=ExistingFilePolicy.OVERWRITE),
            restamped_content,
            file_metadata.name,
        )
        if not write_result.success:
            logger.warning("Could not give workflow '%s' a new id: %s", workflow_file, write_result.error_details)
            return None
        return fresh_id

    def _pick_winner(
        self,
        workflow_files: list[Path],
        metadata_by_file: Mapping[Path, WorkflowMetadata],
        previous_path: Path | None,
        library_roots: list[_LibraryRoot],
    ) -> Path:
        candidates = [
            self._duplicate_candidate(workflow_file, metadata_by_file[workflow_file], previous_path, library_roots)
            for workflow_file in workflow_files
        ]
        every_birth_time_known = all(candidate.birth_time is not None for candidate in candidates)

        def keeps_id_first(candidate: _DuplicateCandidate) -> _KeepsIdOrder:
            birth_time = 0.0
            if every_birth_time_known and candidate.birth_time is not None:
                birth_time = candidate.birth_time
            return _KeepsIdOrder(
                is_writable=candidate.is_writable,
                did_not_hold_id_before_refresh=not candidate.held_id_before_refresh,
                birth_time=birth_time,
                path=str(candidate.path),
            )

        return min(candidates, key=keeps_id_first).path

    def _duplicate_candidate(
        self,
        workflow_file: Path,
        metadata: WorkflowMetadata,
        previous_path: Path | None,
        library_roots: list[_LibraryRoot],
    ) -> _DuplicateCandidate:
        absolute_path = self._absolute_path(workflow_file)
        held_id = previous_path is not None and self._absolute_path(previous_path) == absolute_path
        birth_time = file_birth_time(absolute_path)
        return _DuplicateCandidate(
            path=workflow_file,
            is_writable=self._is_writable(absolute_path, metadata, library_roots),
            held_id_before_refresh=held_id,
            birth_time=birth_time,
        )

    def _without_aliases(self, workflow_files: list[Path]) -> list[Path]:
        distinct_files: list[Path] = []
        for workflow_file in workflow_files:
            if any(is_same_file(workflow_file, kept) for kept in distinct_files):
                continue
            distinct_files.append(workflow_file)
        return distinct_files

    def _is_writable(self, absolute_path: Path, metadata: WorkflowMetadata, library_roots: list[_LibraryRoot]) -> bool:
        """Whether this file may be written. Library workflows never are, whatever the filesystem says.

        A property of the file alone, so every engine picks the same winner for a duplicate.
        """
        if metadata.is_griptape_provided:
            return False
        if _library_root_containing(absolute_path, library_roots) is not None:
            return False
        return os.access(absolute_path, os.W_OK)

    def _library_roots(self) -> list[_LibraryRoot]:
        """Registered libraries' directories. Sandbox libraries are left out: they hold the user's own files."""
        library_roots = []
        for library_info in self.engine.library_manager._library_file_path_to_info.values():
            if library_info.is_sandbox or library_info.library_name is None:
                continue
            root = canonicalize_for_identity_preserving_symlinks(Path(library_info.library_path).parent)
            library_roots.append(
                _LibraryRoot(
                    library_name=library_info.library_name,
                    root=root,
                    followed_root=canonicalize_for_identity(root),
                )
            )
        return library_roots

    def _absolute_path(self, path: str | Path) -> Path:
        return self.engine.workflow_registry.canonical_path(path)


def file_birth_time(path: Path) -> float | None:
    """When the file was created, where the filesystem records it (macOS, Windows), else None.

    A Finder or Explorer copy gets a new birth time but keeps the modified time, so birth time is
    what tells the copy from the original.
    """
    try:
        return getattr(path.stat(), "st_birthtime", None)
    except OSError:
        return None


def _library_root_containing(absolute_path: Path, library_roots: list[_LibraryRoot]) -> _LibraryRoot | None:
    """The library whose directory holds the file, through links kept or followed."""
    followed_path = None
    for library_root in library_roots:
        if absolute_path.is_relative_to(library_root.root):
            return library_root
        if followed_path is None:
            followed_path = canonicalize_for_identity(absolute_path)
        if followed_path.is_relative_to(library_root.followed_root):
            return library_root
    return None
