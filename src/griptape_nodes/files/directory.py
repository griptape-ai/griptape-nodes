"""Directory - a macro-path handle for project directories.

Supports I/O-free path inspection and deferred write via DirectoryDestination.
Versioned directories (v001, v002 …) are provisioned by build_versioned_directory_destination,
which probes the filesystem via the retained mode API to find the first unused index.
"""

from __future__ import annotations

from pathlib import Path

from griptape_nodes.common.macro_parser import MacroSyntaxError, ParsedMacro
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    GetNextVersionIndexRequest,
    GetNextVersionIndexResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import (
    AttemptMapAbsolutePathToProjectRequest,
    AttemptMapAbsolutePathToProjectResultSuccess,
    GetPathForMacroRequest,
    GetPathForMacroResultSuccess,
    MacroPath,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class DirectoryError(Exception):
    """Raised when a directory operation fails."""

    def __init__(self, result_details: str) -> None:
        self.result_details = result_details
        super().__init__(result_details)


class Directory:
    """Path-like object representing a directory.

    The constructor stores a directory reference without performing any I/O.
    Call ``resolve()`` to get the absolute filesystem path.

    Supports MacroPath resolution: pass a MacroPath (which contains variables)
    or a plain string path. Plain strings containing macro variables are
    automatically wrapped in a MacroPath.
    """

    def __init__(self, dir_path: str | MacroPath) -> None:
        """Store directory reference. No I/O is performed.

        Args:
            dir_path: Path to the directory. Can be a plain string or a MacroPath.
        """
        if isinstance(dir_path, str):
            try:
                parsed = ParsedMacro(dir_path)
            except MacroSyntaxError:
                self._dir_path: str | MacroPath = dir_path
            else:
                if parsed.get_variables():
                    self._dir_path = MacroPath(parsed, {})
                else:
                    self._dir_path = dir_path
        else:
            self._dir_path = dir_path

    def resolve(self) -> Path:
        """Resolve and return the absolute path for this directory.

        Returns:
            Absolute Path object.

        Raises:
            DirectoryError: If macro resolution fails (e.g. no project loaded).
        """
        return Path(_resolve_dir_path(self._dir_path))

    @property
    def location(self) -> str:
        """Return the most portable string representation of this directory's location.

        Returns the macro template when the directory holds a macro path,
        otherwise the plain path string. No I/O is performed.
        """
        if isinstance(self._dir_path, MacroPath):
            return self._dir_path.parsed_macro.template
        return self._dir_path

    @property
    def name(self) -> str:
        """Return the directory name (last path component)."""
        return Path(self.location).name


class DirectoryDestination:
    """A pre-configured handle for directory creation.

    Bundles a directory path with a creation policy so it can be passed
    around as a self-contained object. The consumer calls ``create()``
    without needing to know the policy details.

    When the policy is CREATE_NEW and the path contains a ``{_index}``
    macro variable, ``create()`` increments ``_index`` starting at 1 until
    it finds a path that does not yet exist, then creates that directory.
    This produces versioned directories: ``renders_v001/``, ``renders_v002/``.
    """

    def __init__(
        self,
        dir_path: str | MacroPath,
        *,
        existing_dir_policy: ExistingFilePolicy = ExistingFilePolicy.CREATE_NEW,
        create_parents: bool = True,
    ) -> None:
        """Store directory path and creation configuration. No I/O is performed.

        Args:
            dir_path: Path to the directory. Can be a plain string or a MacroPath.
            existing_dir_policy: How to handle an existing directory.
                CREATE_NEW increments _index; OVERWRITE allows reuse; FAIL raises.
                Defaults to CREATE_NEW.
            create_parents: If True, create intermediate directories automatically.
                Defaults to True.
        """
        self._dir_path = dir_path
        self._existing_dir_policy = existing_dir_policy
        self._create_parents = create_parents

    def resolve(self) -> Path:
        """Resolve and return the absolute path for this destination.

        Returns:
            Absolute Path object.

        Raises:
            DirectoryError: If macro resolution fails.
        """
        return Path(_resolve_dir_path(self._dir_path))

    @property
    def location(self) -> str:
        """Return the most portable string representation of this destination's location."""
        if isinstance(self._dir_path, MacroPath):
            return self._dir_path.parsed_macro.template
        return self._dir_path

    def create(self) -> Directory:
        """Create the directory and return a Directory referencing it.

        When policy is CREATE_NEW and the path is a MacroPath containing
        ``{_index}``, increments the index starting at 1 until a non-existent
        directory is found, then creates it.

        Returns:
            Directory referencing the created path (in macro form if inside project).

        Raises:
            DirectoryError: If the directory cannot be created.
        """
        if self._existing_dir_policy == ExistingFilePolicy.CREATE_NEW and isinstance(self._dir_path, MacroPath):
            return self._create_with_versioning()
        return self._create_direct()

    def _create_with_versioning(self) -> Directory:
        """Use GetNextVersionIndexRequest to find an available version slot, then create it."""
        macro_path: MacroPath = self._dir_path  # type: ignore[assignment]

        index_result = GriptapeNodes.handle_request(GetNextVersionIndexRequest(macro_path=macro_path))
        if not isinstance(index_result, GetNextVersionIndexResultSuccess):
            msg = f"Attempted to create versioned directory. Failed to find available version index: {index_result.result_details}"
            raise DirectoryError(msg)

        index = index_result.index if index_result.index is not None else 1
        variables = {**macro_path.variables, "_index": index}
        resolve_result = GriptapeNodes.handle_request(
            GetPathForMacroRequest(parsed_macro=macro_path.parsed_macro, variables=variables)
        )
        if not isinstance(resolve_result, GetPathForMacroResultSuccess):
            msg = f"Attempted to create versioned directory. Failed to resolve macro: {resolve_result.result_details}"
            raise DirectoryError(msg)

        absolute_path = resolve_result.absolute_path
        try:
            absolute_path.mkdir(parents=self._create_parents, exist_ok=False)
        except FileExistsError as e:
            msg = f"Attempted to create versioned directory. Failed because directory '{absolute_path}' already exists."
            raise DirectoryError(msg) from e

        locked_macro = MacroPath(macro_path.parsed_macro, variables)
        return _map_to_macro_directory(absolute_path, locked_macro)

    def _create_direct(self) -> Directory:
        """Create the directory without versioning."""
        resolved = Path(_resolve_dir_path(self._dir_path))

        if resolved.exists() and self._existing_dir_policy == ExistingFilePolicy.FAIL:
            msg = f"Attempted to create directory. Failed because directory already exists: {resolved}"
            raise DirectoryError(msg)

        resolved.mkdir(parents=self._create_parents, exist_ok=True)
        return _map_to_macro_directory(resolved, self._dir_path)


def _resolve_dir_path(dir_path: str | MacroPath) -> str:
    """Resolve a directory path, handling MacroPath resolution if needed.

    Args:
        dir_path: A plain path string or a MacroPath.

    Returns:
        A resolved path string.

    Raises:
        DirectoryError: If macro resolution fails.
    """
    if isinstance(dir_path, str):
        return dir_path

    resolve_result = GriptapeNodes.handle_request(
        GetPathForMacroRequest(parsed_macro=dir_path.parsed_macro, variables=dir_path.variables)
    )

    if not isinstance(resolve_result, GetPathForMacroResultSuccess):
        msg = f"Attempted to resolve directory path. Failed: {resolve_result.result_details}"
        raise DirectoryError(msg)

    return str(resolve_result.absolute_path)


def _map_to_macro_directory(absolute_path: Path, fallback_path: str | MacroPath) -> Directory:
    """Attempt to map the created directory path to a portable macro form.

    Returns a Directory holding the macro template when the path is inside
    a project directory, so callers can store a portable reference.
    Falls back to the locked MacroPath or absolute path string if mapping fails.
    """
    map_result = GriptapeNodes.handle_request(AttemptMapAbsolutePathToProjectRequest(absolute_path=absolute_path))
    if isinstance(map_result, AttemptMapAbsolutePathToProjectResultSuccess) and map_result.mapped_path is not None:
        return Directory(map_result.mapped_path)
    if isinstance(fallback_path, MacroPath):
        return Directory(fallback_path)
    return Directory(str(absolute_path))
