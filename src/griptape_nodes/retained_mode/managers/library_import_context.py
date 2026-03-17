from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

if TYPE_CHECKING:
    from types import ModuleType, TracebackType

    from griptape_nodes.exe_types.node_types import BaseNode


class LibraryImportContext:
    """Context manager that scopes sys.path and sys.modules to a specific library's paths during module loading.

    This prevents dependency conflicts between libraries by ensuring each library's modules
    are loaded against only that library's own paths plus the engine baseline paths,
    rather than the accumulated global sys.path that includes all other libraries' paths.

    Additionally, modules imported from library-specific paths are cached per-library and
    removed from sys.modules on exit. This prevents a module imported for Library A (e.g.,
    a specific version of numpy) from being reused by Library B, which may require a
    different version.
    """

    # Per-library module caches. Maps library_name -> {module_name: module}.
    # Cached modules are restored when entering a library's context and removed from
    # sys.modules when exiting, preventing cross-library module contamination.
    _library_module_caches: ClassVar[dict[str, dict[str, ModuleType]]] = {}

    def __init__(self, library_name: str, library_paths: list[str], engine_baseline_path: list[str]) -> None:
        self._library_name = library_name
        self._library_paths = library_paths
        self._engine_baseline_path = engine_baseline_path
        self._saved_path: list[str] = []
        self._modules_before: set[str] = set()

    def __enter__(self) -> Self:
        self._saved_path = sys.path.copy()
        # Record which modules exist before this context so we can detect new imports.
        self._modules_before = set(sys.modules.keys())
        # Restore any modules previously cached for this library so they don't get
        # re-imported from scratch (preserving object identity and avoiding re-execution).
        if self._library_name and self._library_name in self._library_module_caches:
            sys.modules.update(self._library_module_caches[self._library_name])
        # Scope sys.path to only this library's paths plus the engine baseline.
        # This prevents the library from resolving imports against other libraries' paths.
        sys.path[:] = self._library_paths + self._engine_baseline_path
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        sys.path[:] = self._saved_path
        if not self._library_name:
            return
        # Find all modules imported during this context.
        new_module_names = set(sys.modules.keys()) - self._modules_before
        # Identify library-specific modules: those whose file resolves under a library path.
        # Engine baseline modules (stdlib, engine packages) are left in sys.modules.
        library_specific: dict[str, ModuleType] = {}
        for name in new_module_names:
            module = sys.modules[name]
            module_file = getattr(module, "__file__", None)
            if module_file is not None and self._is_under_library_path(module_file):
                library_specific[name] = module
        # Cache this library's modules so they can be restored on re-entry.
        if library_specific:
            if self._library_name not in self._library_module_caches:
                self._library_module_caches[self._library_name] = {}
            self._library_module_caches[self._library_name].update(library_specific)
        # Remove library-specific modules from sys.modules so the next library's
        # context doesn't accidentally pick up this library's versions.
        for name in library_specific:
            del sys.modules[name]

    def _is_under_library_path(self, file_path: str) -> bool:
        """Check if a file path resolves under one of this library's registered paths."""
        module_path = Path(file_path)
        for library_path in self._library_paths:
            if module_path.is_relative_to(Path(library_path)):
                return True
        return False


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
    return LibraryImportContext(library_name, library_paths, manager._engine_baseline_path)


def library_scope_for_node(node: BaseNode) -> LibraryImportContext:
    """Create a LibraryImportContext scoped to the library that owns the given node.

    Uses node.metadata["library"] (injected during Library.create_node()) to look up
    the correct sys.path entries for that library's environment.
    """
    library_name = node.metadata.get("library", "")
    return library_scope_for_library_name(library_name)
