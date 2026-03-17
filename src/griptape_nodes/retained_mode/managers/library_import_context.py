from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

    from griptape_nodes.exe_types.node_types import BaseNode


class LibraryImportContext:
    """Context manager that scopes sys.path to a specific library's paths during module loading.

    This prevents dependency conflicts between libraries by ensuring each library's modules
    are loaded against only that library's own paths plus the engine baseline paths,
    rather than the accumulated global sys.path that includes all other libraries' paths.
    """

    def __init__(self, library_paths: list[str], engine_baseline_path: list[str]) -> None:
        self._library_paths = library_paths
        self._engine_baseline_path = engine_baseline_path
        self._saved_path: list[str] = []

    def __enter__(self) -> Self:
        self._saved_path = sys.path.copy()
        # Scope sys.path to only this library's paths plus the engine baseline.
        # This prevents the library from resolving imports against other libraries' paths.
        sys.path[:] = self._library_paths + self._engine_baseline_path
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        sys.path[:] = self._saved_path


def library_scope_for_library_name(library_name: str) -> LibraryImportContext:
    """Create a LibraryImportContext scoped to the named library.

    Looks up sys.path entries registered for the given library name.
    Returns an empty-paths context (engine baseline only) when the name is unknown.
    """
    # Lazy import required: library_import_context is imported by library_manager,
    # which is loaded by GriptapeNodes. Importing GriptapeNodes at module level here
    # would create a circular dependency.
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    manager = GriptapeNodes.LibraryManager()
    library_paths = manager._library_to_path_entries.get(library_name, [])
    return LibraryImportContext(library_paths, manager._engine_baseline_path)


def library_scope_for_node(node: BaseNode) -> LibraryImportContext:
    """Create a LibraryImportContext scoped to the library that owns the given node.

    Uses node.metadata["library"] (injected during Library.create_node()) to look up
    the correct sys.path entries for that library's environment.
    """
    library_name = node.metadata.get("library", "")
    return library_scope_for_library_name(library_name)
