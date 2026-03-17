"""Unit tests for LibraryImportContext."""

from __future__ import annotations

import sys

import pytest

from griptape_nodes.retained_mode.managers.library_import_context import LibraryImportContext


class TestLibraryImportContext:
    def test_scopes_sys_path_inside_context(self) -> None:
        """sys.path inside the context contains only library_paths + engine_baseline."""
        library_paths = ["/lib/a/base", "/lib/a/site-packages"]
        engine_baseline = ["/engine/src", "/usr/lib/python3"]
        original = sys.path.copy()

        with LibraryImportContext(library_paths, engine_baseline):
            assert sys.path == library_paths + engine_baseline

        assert sys.path == original

    def test_restores_sys_path_after_context(self) -> None:
        """sys.path is fully restored to its original value after the context exits."""
        original = sys.path.copy()
        with LibraryImportContext(["/fake/lib"], ["/fake/baseline"]):
            pass
        assert sys.path == original

    def test_restores_sys_path_on_exception(self) -> None:
        """sys.path is restored even when an exception is raised inside the context."""
        original = sys.path.copy()
        with pytest.raises(RuntimeError), LibraryImportContext(["/fake/lib"], ["/fake/baseline"]):
            raise RuntimeError
        assert sys.path == original

    def test_empty_library_paths_uses_engine_baseline_only(self) -> None:
        """An empty library_paths list scopes sys.path to just the engine baseline."""
        engine_baseline = ["/engine/src"]
        with LibraryImportContext([], engine_baseline):
            assert sys.path == engine_baseline

    def test_library_paths_take_precedence_over_engine_baseline(self) -> None:
        """Library paths appear before engine_baseline paths so they are searched first."""
        library_paths = ["/lib/site-packages"]
        engine_baseline = ["/engine/site-packages"]
        with LibraryImportContext(library_paths, engine_baseline):
            assert sys.path.index("/lib/site-packages") < sys.path.index("/engine/site-packages")

    def test_nested_contexts_restore_correctly(self) -> None:
        """Nested contexts each restore sys.path to what it was before they entered."""
        original = sys.path.copy()
        with LibraryImportContext(["/lib/a"], ["/engine"]):
            after_outer_enter = sys.path.copy()
            with LibraryImportContext(["/lib/b"], ["/engine"]):
                assert sys.path == ["/lib/b", "/engine"]
            assert sys.path == after_outer_enter
        assert sys.path == original
