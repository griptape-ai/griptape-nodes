"""Tests for WorkflowPackager transitive library dependency resolution."""

from unittest.mock import MagicMock, patch

from griptape_nodes.node_library.library_registry import LibraryDependency, LibraryNameAndVersion
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.publishing.workflow_packager import WorkflowPackager


def _make_lib_info(name: str, version: str = "1.0.0") -> LibraryManager.LibraryInfo:
    return LibraryManager.LibraryInfo(
        lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
        library_path=f"/workspace/libraries/{name}/griptape_nodes_library.json",
        is_sandbox=False,
        library_name=name,
        library_version=version,
        fitness=LibraryManager.LibraryFitness.GOOD,
        problems=[],
    )


def _make_library_data_mock(
    pip_dependencies: list[str] | None = None,
    pip_install_flags: list[str] | None = None,
    library_dependencies: list[LibraryDependency] | None = None,
) -> MagicMock:
    """Return a mock library.get_library_data() with the given dependency fields."""
    deps_mock = MagicMock()
    deps_mock.pip_dependencies = pip_dependencies
    deps_mock.pip_install_flags = pip_install_flags
    deps_mock.library_dependencies = library_dependencies

    metadata_mock = MagicMock()
    metadata_mock.dependencies = deps_mock

    schema_mock = MagicMock()
    schema_mock.metadata = metadata_mock

    library_mock = MagicMock()
    library_mock.get_library_data.return_value = schema_mock

    return library_mock


def _make_workflow_mock(library_names: list[str]) -> MagicMock:
    workflow = MagicMock()
    workflow.metadata.node_libraries_referenced = [
        LibraryNameAndVersion(library_name=name, library_version="1.0.0") for name in library_names
    ]
    return workflow


class TestResolveAllLibraryDeps:
    """Tests for WorkflowPackager._resolve_all_library_deps()."""

    def test_no_library_deps_returns_initial(self) -> None:
        """A library with no library_dependencies returns just the initial set."""
        packager = WorkflowPackager("test_workflow")
        lib_a = _make_library_data_mock(library_dependencies=None)

        with patch(
            "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
            side_effect=lambda name: lib_a if name == "lib-a" else (_ for _ in ()).throw(KeyError(name)),
        ):
            initial = [LibraryNameAndVersion("lib-a", "1.0.0")]
            result = packager._resolve_all_library_deps(initial)

        assert [r.library_name for r in result] == ["lib-a"]

    def test_direct_dep_added(self) -> None:
        """Library A declaring a library_dependency on Library B adds B to the result."""
        packager = WorkflowPackager("test_workflow")
        dep_b = LibraryDependency(url="griptape-ai/lib-b@v1.0.0", required=True)
        lib_a = _make_library_data_mock(library_dependencies=[dep_b])
        lib_b = _make_library_data_mock(library_dependencies=None)
        info_b = _make_lib_info("lib-b")

        def get_library(name: str) -> MagicMock:
            return {"lib-a": lib_a, "lib-b": lib_b}[name]

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                side_effect=get_library,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(
                    get_library_info_by_library_name=lambda name: info_b if name == "lib-b" else None
                ),
            ),
        ):
            initial = [LibraryNameAndVersion("lib-a", "1.0.0")]
            result = packager._resolve_all_library_deps(initial)

        names = {r.library_name for r in result}
        assert "lib-a" in names
        assert "lib-b" in names

    def test_transitive_dep_added(self) -> None:
        """A→B→C chain results in all three libraries being included."""
        packager = WorkflowPackager("test_workflow")
        dep_b = LibraryDependency(url="griptape-ai/lib-b@v1.0.0", required=True)
        dep_c = LibraryDependency(url="griptape-ai/lib-c@v1.0.0", required=True)
        lib_a = _make_library_data_mock(library_dependencies=[dep_b])
        lib_b = _make_library_data_mock(library_dependencies=[dep_c])
        lib_c = _make_library_data_mock(library_dependencies=None)
        info_b = _make_lib_info("lib-b")
        info_c = _make_lib_info("lib-c")

        def get_library(name: str) -> MagicMock:
            return {"lib-a": lib_a, "lib-b": lib_b, "lib-c": lib_c}[name]

        def get_lib_info(name: str) -> LibraryManager.LibraryInfo | None:
            return {"lib-b": info_b, "lib-c": info_c}.get(name)

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                side_effect=get_library,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(get_library_info_by_library_name=get_lib_info),
            ),
        ):
            initial = [LibraryNameAndVersion("lib-a", "1.0.0")]
            result = packager._resolve_all_library_deps(initial)

        names = {r.library_name for r in result}
        assert names == {"lib-a", "lib-b", "lib-c"}

    def test_cycle_does_not_loop(self) -> None:
        """A→B→A cycle terminates without infinite loop and includes both libraries once."""
        packager = WorkflowPackager("test_workflow")
        dep_b = LibraryDependency(url="griptape-ai/lib-b@v1.0.0", required=True)
        dep_a = LibraryDependency(url="griptape-ai/lib-a@v1.0.0", required=True)
        lib_a = _make_library_data_mock(library_dependencies=[dep_b])
        lib_b = _make_library_data_mock(library_dependencies=[dep_a])
        info_a = _make_lib_info("lib-a")
        info_b = _make_lib_info("lib-b")

        def get_library(name: str) -> MagicMock:
            return {"lib-a": lib_a, "lib-b": lib_b}[name]

        def get_lib_info(name: str) -> LibraryManager.LibraryInfo | None:
            return {"lib-a": info_a, "lib-b": info_b}.get(name)

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                side_effect=get_library,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(get_library_info_by_library_name=get_lib_info),
            ),
        ):
            initial = [LibraryNameAndVersion("lib-a", "1.0.0")]
            result = packager._resolve_all_library_deps(initial)

        names = {r.library_name for r in result}
        assert names == {"lib-a", "lib-b"}

    def test_unregistered_dep_skipped(self) -> None:
        """A dep URL that resolves to an unregistered library is skipped without raising."""
        packager = WorkflowPackager("test_workflow")
        dep_missing = LibraryDependency(url="griptape-ai/lib-missing@v1.0.0", required=True)
        lib_a = _make_library_data_mock(library_dependencies=[dep_missing])

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                return_value=lib_a,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(get_library_info_by_library_name=lambda _: None),
            ),
        ):
            initial = [LibraryNameAndVersion("lib-a", "1.0.0")]
            result = packager._resolve_all_library_deps(initial)

        assert [r.library_name for r in result] == ["lib-a"]


class TestCollectDependenciesTransitive:
    """collect_dependencies includes pip deps from transitive library dependencies."""

    def test_includes_pip_deps_from_transitive_library(self) -> None:
        """Workflow uses Library A; A depends on Library B; B's pip deps appear in result."""
        packager = WorkflowPackager("test_workflow")
        workflow = _make_workflow_mock(["lib-a"])

        dep_b = LibraryDependency(url="griptape-ai/lib-b@v1.0.0", required=True)
        lib_a = _make_library_data_mock(pip_dependencies=["requests>=2.0"], library_dependencies=[dep_b])
        lib_b = _make_library_data_mock(pip_dependencies=["numpy>=1.0"], library_dependencies=None)
        info_b = _make_lib_info("lib-b")

        def get_library(name: str) -> MagicMock:
            return {"lib-a": lib_a, "lib-b": lib_b}[name]

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                side_effect=get_library,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(
                    get_library_info_by_library_name=lambda name: info_b if name == "lib-b" else None
                ),
            ),
            patch.object(packager, "get_engine_version", return_value="0.0.0"),
            patch.object(packager, "get_install_source", return_value=("pypi", None)),
        ):
            result = packager.collect_dependencies(workflow)

        assert "numpy>=1.0" in result
        assert "requests>=2.0" in result


class TestCollectPipInstallFlagsTransitive:
    """collect_pip_install_flags includes flags from transitive library dependencies."""

    def test_includes_flags_from_transitive_library(self) -> None:
        """Workflow uses Library A; A depends on Library B; B's pip flags appear in result."""
        packager = WorkflowPackager("test_workflow")
        workflow = _make_workflow_mock(["lib-a"])

        dep_b = LibraryDependency(url="griptape-ai/lib-b@v1.0.0", required=True)
        lib_a = _make_library_data_mock(
            pip_install_flags=["--extra-index-url=https://a.example.com"], library_dependencies=[dep_b]
        )
        lib_b = _make_library_data_mock(
            pip_install_flags=["--extra-index-url=https://b.example.com"], library_dependencies=None
        )
        info_b = _make_lib_info("lib-b")

        def get_library(name: str) -> MagicMock:
            return {"lib-a": lib_a, "lib-b": lib_b}[name]

        with (
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.LibraryRegistry.get_library",
                side_effect=get_library,
            ),
            patch(
                "griptape_nodes.retained_mode.publishing.workflow_packager.GriptapeNodes.LibraryManager",
                return_value=MagicMock(
                    get_library_info_by_library_name=lambda name: info_b if name == "lib-b" else None
                ),
            ),
        ):
            result = packager.collect_pip_install_flags(workflow)

        assert "--extra-index-url=https://a.example.com" in result
        assert "--extra-index-url=https://b.example.com" in result
