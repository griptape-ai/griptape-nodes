"""Tests verifying that _load_module_from_file scopes sys.path to the loading library."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from griptape_nodes.retained_mode.events.library_events import UnloadLibraryFromRegistryRequest
from griptape_nodes.retained_mode.managers.library_import_context import LibraryImportContext

if TYPE_CHECKING:
    from collections.abc import Generator

    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestLoadModuleFromFileSysPathScoping:
    """Verify that _load_module_from_file uses LibraryImportContext to scope sys.path."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def _write_path_capture_module(self, directory: Path) -> Path:
        """Write a Python file that captures sys.path at import time into a module global."""
        module_file = directory / "capture_path.py"
        module_file.write_text("import sys\nCAPTURED_SYS_PATH = sys.path.copy()\n")
        return module_file

    def test_sys_path_is_scoped_to_library_paths_plus_engine_baseline(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Inside exec_module, sys.path contains only library_paths + engine_baseline."""
        library_manager = griptape_nodes.LibraryManager()
        module_file = self._write_path_capture_module(temp_dir)

        library_name = "Test Library"
        library_paths = ["/fake/lib/base", "/fake/lib/site-packages"]
        engine_baseline = ["/fake/engine/src"]

        library_manager._library_to_path_entries[library_name] = library_paths
        library_manager._engine_baseline_path = engine_baseline

        module = library_manager._load_module_from_file(module_file, library_name)

        assert library_paths + engine_baseline == module.CAPTURED_SYS_PATH

    def test_sys_path_is_restored_after_module_load(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """sys.path is back to its original value after _load_module_from_file returns."""
        library_manager = griptape_nodes.LibraryManager()
        module_file = self._write_path_capture_module(temp_dir)

        library_name = "Test Library"
        library_manager._library_to_path_entries[library_name] = ["/fake/lib"]
        library_manager._engine_baseline_path = ["/fake/engine"]

        path_before = sys.path.copy()
        library_manager._load_module_from_file(module_file, library_name)
        assert sys.path == path_before

    def test_other_library_paths_are_excluded_from_scoped_path(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Paths belonging to other libraries are not visible during module loading."""
        library_manager = griptape_nodes.LibraryManager()
        module_file = self._write_path_capture_module(temp_dir)

        library_name = "Library A"
        other_library_path = "/fake/library_b/site-packages"

        library_manager._library_to_path_entries[library_name] = ["/fake/library_a/site-packages"]
        library_manager._library_to_path_entries["Library B"] = [other_library_path]
        library_manager._engine_baseline_path = ["/fake/engine"]

        module = library_manager._load_module_from_file(module_file, library_name)

        assert other_library_path not in module.CAPTURED_SYS_PATH

    def test_library_with_no_path_entries_uses_engine_baseline_only(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """A library with no entries in _library_to_path_entries loads against only the engine baseline."""
        library_manager = griptape_nodes.LibraryManager()
        module_file = self._write_path_capture_module(temp_dir)

        engine_baseline = ["/fake/engine"]
        library_manager._engine_baseline_path = engine_baseline
        # Do NOT add the library to _library_to_path_entries

        module = library_manager._load_module_from_file(module_file, "Unknown Library")

        assert engine_baseline == module.CAPTURED_SYS_PATH

    def test_hot_reload_also_scopes_sys_path(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """sys.path is scoped on hot reload (second load of the same module file)."""
        library_manager = griptape_nodes.LibraryManager()
        module_file = self._write_path_capture_module(temp_dir)

        library_name = "Test Library"
        library_paths = ["/fake/lib/base"]
        engine_baseline = ["/fake/engine"]

        library_manager._library_to_path_entries[library_name] = library_paths
        library_manager._engine_baseline_path = engine_baseline

        # First load
        library_manager._load_module_from_file(module_file, library_name)
        # Second load (hot reload path)
        module = library_manager._load_module_from_file(module_file, library_name)

        assert library_paths + engine_baseline == module.CAPTURED_SYS_PATH

    def test_dependency_imported_by_lib_a_not_leaked_to_lib_b(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """A dependency imported during Library A's module load is not visible to Library B's load."""
        import types

        from griptape_nodes.retained_mode.managers.library_import_context import LibraryImportContext

        library_manager = griptape_nodes.LibraryManager()

        lib_a_dir = temp_dir / "lib_a"
        lib_a_dir.mkdir()
        lib_b_dir = temp_dir / "lib_b"
        lib_b_dir.mkdir()

        # Library A's module captures which modules are present at import time
        module_a_file = lib_a_dir / "node_a.py"
        module_a_file.write_text("import sys\nCAPTURED_MODULES = set(sys.modules.keys())\n")

        # Library B's module also captures which modules are present
        module_b_file = lib_b_dir / "node_b.py"
        module_b_file.write_text("import sys\nCAPTURED_MODULES = set(sys.modules.keys())\n")

        lib_a_name = "Isolation Test Library A"
        lib_b_name = "Isolation Test Library B"
        fake_dep_name = "_test_fake_shared_dep_xyz"

        library_manager._library_to_path_entries[lib_a_name] = [str(lib_a_dir)]
        library_manager._library_to_path_entries[lib_b_name] = [str(lib_b_dir)]
        library_manager._engine_baseline_path = ["/fake/engine"]

        # Simulate a dependency that Library A loaded into sys.modules
        fake_dep = types.ModuleType(fake_dep_name)
        fake_dep.__file__ = str(lib_a_dir / "fake_dep/__init__.py")
        LibraryImportContext._library_module_caches.pop(lib_a_name, None)
        LibraryImportContext._library_module_caches.pop(lib_b_name, None)
        LibraryImportContext._library_module_caches[lib_a_name] = {fake_dep_name: fake_dep}

        # Load Library B's module — it should NOT see lib_a's cached dep
        module_b = library_manager._load_module_from_file(module_b_file, lib_b_name)

        assert fake_dep_name not in module_b.CAPTURED_MODULES

        # Cleanup
        LibraryImportContext._library_module_caches.pop(lib_a_name, None)
        LibraryImportContext._library_module_caches.pop(lib_b_name, None)


class TestUnloadLibraryClearsModuleCache:
    """Verify that unloading a library clears its entry from LibraryImportContext._library_module_caches."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_unload_clears_library_module_cache(self, griptape_nodes: GriptapeNodes) -> None:
        """unload_library_from_registry_request removes the library's entry from _library_module_caches."""
        library_manager = griptape_nodes.LibraryManager()
        library_name = "_test_unload_cache_lib"

        fake_dep = types.ModuleType("_test_dep")
        fake_dep.__file__ = "/fake/lib/site-packages/dep/__init__.py"
        LibraryImportContext._library_module_caches[library_name] = {"_test_dep": fake_dep}

        with patch("griptape_nodes.node_library.library_registry.LibraryRegistry.unregister_library"):
            result = library_manager.unload_library_from_registry_request(
                UnloadLibraryFromRegistryRequest(library_name=library_name)
            )

        assert result.succeeded()
        assert library_name not in LibraryImportContext._library_module_caches

    def test_unload_does_not_clear_other_libraries_caches(self, griptape_nodes: GriptapeNodes) -> None:
        """Unloading one library leaves other libraries' module caches intact."""
        library_manager = griptape_nodes.LibraryManager()
        target_lib = "_test_unload_target_lib"
        other_lib = "_test_unload_other_lib"

        fake_dep = types.ModuleType("_test_other_dep")
        fake_dep.__file__ = "/fake/other/site-packages/dep/__init__.py"
        LibraryImportContext._library_module_caches[target_lib] = {}
        LibraryImportContext._library_module_caches[other_lib] = {"_test_other_dep": fake_dep}

        with patch("griptape_nodes.node_library.library_registry.LibraryRegistry.unregister_library"):
            library_manager.unload_library_from_registry_request(
                UnloadLibraryFromRegistryRequest(library_name=target_lib)
            )

        assert other_lib in LibraryImportContext._library_module_caches
        assert "_test_other_dep" in LibraryImportContext._library_module_caches[other_lib]

        # Cleanup
        LibraryImportContext._library_module_caches.pop(other_lib, None)

    def test_unload_failure_does_not_clear_cache(self, griptape_nodes: GriptapeNodes) -> None:
        """When unregistering fails, the module cache is NOT cleared (library is still loaded)."""
        library_manager = griptape_nodes.LibraryManager()
        library_name = "_test_unload_fail_lib"

        fake_dep = types.ModuleType("_test_fail_dep")
        fake_dep.__file__ = "/fake/lib/site-packages/dep/__init__.py"
        LibraryImportContext._library_module_caches[library_name] = {"_test_fail_dep": fake_dep}

        # Simulate unregister raising (library not registered)
        with patch(
            "griptape_nodes.node_library.library_registry.LibraryRegistry.unregister_library",
            side_effect=KeyError("not registered"),
        ):
            result = library_manager.unload_library_from_registry_request(
                UnloadLibraryFromRegistryRequest(library_name=library_name)
            )

        assert not result.succeeded()
        assert library_name in LibraryImportContext._library_module_caches

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)

    def test_reload_after_unload_does_not_restore_stale_deps(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """After unload, a module load in that library's context does not see the old cached deps."""
        library_manager = griptape_nodes.LibraryManager()
        library_name = "_test_reload_stale_lib"
        stale_dep_name = "_test_stale_dep_module"

        lib_dir = temp_dir / "lib"
        lib_dir.mkdir()
        # Module that records which dep modules are visible at import time
        module_file = lib_dir / "node.py"
        module_file.write_text("import sys\nCAPTURED_MODULES = set(sys.modules.keys())\n")

        library_manager._library_to_path_entries[library_name] = [str(lib_dir)]
        library_manager._engine_baseline_path = ["/fake/engine"]

        # Seed the cache with a stale dep as if the library had been loaded before
        stale_dep = types.ModuleType(stale_dep_name)
        stale_dep.__file__ = str(lib_dir / "site-packages/stale_dep/__init__.py")
        LibraryImportContext._library_module_caches[library_name] = {stale_dep_name: stale_dep}

        # Unload clears the cache
        with patch("griptape_nodes.node_library.library_registry.LibraryRegistry.unregister_library"):
            library_manager.unload_library_from_registry_request(
                UnloadLibraryFromRegistryRequest(library_name=library_name)
            )

        # Reload — the stale dep should NOT be visible during module execution
        module = library_manager._load_module_from_file(module_file, library_name)

        assert stale_dep_name not in module.CAPTURED_MODULES

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)
