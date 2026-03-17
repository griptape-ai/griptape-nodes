"""Unit tests for LibraryImportContext."""

from __future__ import annotations

import sys
import types

import pytest

from griptape_nodes.retained_mode.managers.library_import_context import LibraryImportContext


class TestLibraryImportContext:
    def test_scopes_sys_path_inside_context(self) -> None:
        """sys.path inside the context contains only library_paths + engine_baseline."""
        library_paths = ["/lib/a/base", "/lib/a/site-packages"]
        engine_baseline = ["/engine/src", "/usr/lib/python3"]
        original = sys.path.copy()

        with LibraryImportContext("lib_a", library_paths, engine_baseline):
            assert sys.path == library_paths + engine_baseline

        assert sys.path == original

    def test_restores_sys_path_after_context(self) -> None:
        """sys.path is fully restored to its original value after the context exits."""
        original = sys.path.copy()
        with LibraryImportContext("lib_a", ["/fake/lib"], ["/fake/baseline"]):
            pass
        assert sys.path == original

    def test_restores_sys_path_on_exception(self) -> None:
        """sys.path is restored even when an exception is raised inside the context."""
        original = sys.path.copy()
        with pytest.raises(RuntimeError), LibraryImportContext("lib_a", ["/fake/lib"], ["/fake/baseline"]):
            raise RuntimeError
        assert sys.path == original

    def test_empty_library_paths_uses_engine_baseline_only(self) -> None:
        """An empty library_paths list scopes sys.path to just the engine baseline."""
        engine_baseline = ["/engine/src"]
        with LibraryImportContext("lib_a", [], engine_baseline):
            assert sys.path == engine_baseline

    def test_library_paths_take_precedence_over_engine_baseline(self) -> None:
        """Library paths appear before engine_baseline paths so they are searched first."""
        library_paths = ["/lib/site-packages"]
        engine_baseline = ["/engine/site-packages"]
        with LibraryImportContext("lib_a", library_paths, engine_baseline):
            assert sys.path.index("/lib/site-packages") < sys.path.index("/engine/site-packages")

    def test_nested_contexts_restore_correctly(self) -> None:
        """Nested contexts each restore sys.path to what it was before they entered."""
        original = sys.path.copy()
        with LibraryImportContext("lib_a", ["/lib/a"], ["/engine"]):
            after_outer_enter = sys.path.copy()
            with LibraryImportContext("lib_b", ["/lib/b"], ["/engine"]):
                assert sys.path == ["/lib/b", "/engine"]
            assert sys.path == after_outer_enter
        assert sys.path == original

    def test_library_specific_modules_are_cached_on_exit(self) -> None:
        """Modules imported from a library path are cached for that library on context exit."""
        library_paths = ["/lib/a/site-packages"]
        engine_baseline = ["/engine/src"]
        library_name = "_test_lib_cache_a"
        module_name = "_test_fake_lib_module_cache"

        LibraryImportContext._library_module_caches.pop(library_name, None)
        sys.modules.pop(module_name, None)

        fake_module = types.ModuleType(module_name)
        fake_module.__file__ = "/lib/a/site-packages/fake_lib_module/__init__.py"

        with LibraryImportContext(library_name, library_paths, engine_baseline):
            sys.modules[module_name] = fake_module

        assert library_name in LibraryImportContext._library_module_caches
        assert module_name in LibraryImportContext._library_module_caches[library_name]
        assert module_name not in sys.modules

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)

    def test_cached_modules_restored_on_context_reentry(self) -> None:
        """Re-entering a library's context restores its previously cached modules."""
        library_paths = ["/lib/a/site-packages"]
        engine_baseline = ["/engine/src"]
        library_name = "_test_lib_restore_a"
        module_name = "_test_fake_lib_module_restore"

        fake_module = types.ModuleType(module_name)
        fake_module.__file__ = "/lib/a/site-packages/fake_lib_module/__init__.py"
        LibraryImportContext._library_module_caches[library_name] = {module_name: fake_module}
        sys.modules.pop(module_name, None)

        with LibraryImportContext(library_name, library_paths, engine_baseline):
            assert module_name in sys.modules
            assert sys.modules[module_name] is fake_module

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)
        sys.modules.pop(module_name, None)

    def test_library_a_modules_not_visible_in_library_b_context(self) -> None:
        """Modules cached from Library A are not present when Library B's context is active."""
        lib_a_paths = ["/lib/a/site-packages"]
        lib_b_paths = ["/lib/b/site-packages"]
        engine_baseline = ["/engine/src"]
        lib_a_name = "_test_isolation_lib_a"
        lib_b_name = "_test_isolation_lib_b"
        module_name = "_test_conflicting_dep"

        LibraryImportContext._library_module_caches.pop(lib_a_name, None)
        LibraryImportContext._library_module_caches.pop(lib_b_name, None)
        sys.modules.pop(module_name, None)

        fake_a_module = types.ModuleType(module_name)
        fake_a_module.__file__ = "/lib/a/site-packages/conflicting_dep/__init__.py"

        # Import a module under lib_a's context
        with LibraryImportContext(lib_a_name, lib_a_paths, engine_baseline):
            sys.modules[module_name] = fake_a_module

        # Module was removed from sys.modules on exit
        assert module_name not in sys.modules

        # Entering lib_b's context does NOT restore lib_a's cached module
        with LibraryImportContext(lib_b_name, lib_b_paths, engine_baseline):
            assert module_name not in sys.modules

        # Cleanup
        LibraryImportContext._library_module_caches.pop(lib_a_name, None)
        LibraryImportContext._library_module_caches.pop(lib_b_name, None)

    def test_engine_baseline_modules_not_removed_on_exit(self) -> None:
        """Modules not under any library path (e.g. stdlib) are not removed on context exit."""
        library_paths = ["/lib/a/site-packages"]
        engine_baseline = ["/engine/src"]
        library_name = "_test_lib_engine_baseline"

        # os is a stdlib module always present in sys.modules
        assert "os" in sys.modules

        with LibraryImportContext(library_name, library_paths, engine_baseline):
            pass

        assert "os" in sys.modules

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)

    def test_no_caching_on_exception(self) -> None:
        """Modules imported during a failed context are not cached, only cleaned up."""
        library_paths = ["/lib/a/site-packages"]
        engine_baseline = ["/engine/src"]
        library_name = "_test_lib_no_cache_on_exception"
        module_name = "_test_failed_import_module"

        LibraryImportContext._library_module_caches.pop(library_name, None)
        sys.modules.pop(module_name, None)

        fake_module = types.ModuleType(module_name)
        fake_module.__file__ = "/lib/a/site-packages/failed_module/__init__.py"

        def _failing_import() -> None:
            sys.modules[module_name] = fake_module
            err_msg = "simulated DLL load failure"
            raise ImportError(err_msg)

        with pytest.raises(ImportError), LibraryImportContext(library_name, library_paths, engine_baseline):
            _failing_import()

        # Module should be cleaned up from sys.modules
        assert module_name not in sys.modules
        # But it should NOT be cached — the import was partial/broken
        assert library_name not in LibraryImportContext._library_module_caches

        # Cleanup
        LibraryImportContext._library_module_caches.pop(library_name, None)

    def test_no_caching_when_library_name_is_empty(self) -> None:
        """When library_name is empty, no modules are cached or removed on exit."""
        library_paths = ["/lib/a/site-packages"]
        engine_baseline = ["/engine/src"]
        module_name = "_test_no_cache_module"

        fake_module = types.ModuleType(module_name)
        fake_module.__file__ = "/lib/a/site-packages/fake/__init__.py"

        with LibraryImportContext("", library_paths, engine_baseline):
            sys.modules[module_name] = fake_module

        # Module should still be in sys.modules (no cleanup for unnamed library)
        assert module_name in sys.modules
        assert "" not in LibraryImportContext._library_module_caches

        # Cleanup
        sys.modules.pop(module_name, None)
