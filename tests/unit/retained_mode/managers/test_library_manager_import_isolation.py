"""Tests verifying that _load_module_from_file scopes sys.path to the loading library."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

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
