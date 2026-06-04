"""Tests for inter-library dependency resolution (GH#4740)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.node_library.library_registry import Dependencies, LibraryDependency, LibrarySchema
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.library_events import (
    DownloadLibraryResultFailure,
    DownloadLibraryResultSuccess,
    InstallLibraryDependenciesResultFailure,
    LoadLibraryMetadataFromFileResultSuccess,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromFileResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.fitness_problems.libraries import LibraryDependencyProblem
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.managers.settings import LibraryDependencyInstallBehavior


class TestDependenciesSchema:
    """Tests for the Dependencies model schema changes."""

    def test_library_dependencies_field_exists(self) -> None:
        deps = Dependencies()
        assert deps.library_dependencies is None

    def test_library_dependencies_coerces_string_to_object(self) -> None:
        # Simulate JSON deserialization where bare strings must be coerced to LibraryDependency
        deps = Dependencies.model_validate({"library_dependencies": ["griptape-ai/nodes-opencolorio@v1.2.0"]})
        assert deps.library_dependencies is not None
        assert len(deps.library_dependencies) == 1
        dep = deps.library_dependencies[0]
        assert dep.url == "griptape-ai/nodes-opencolorio@v1.2.0"
        assert dep.required is True

    def test_library_dependencies_accepts_object_form(self) -> None:
        deps = Dependencies.model_validate(
            {"library_dependencies": [{"url": "griptape-ai/nodes-opencolorio@v1.2.0", "required": False}]}
        )
        assert deps.library_dependencies is not None
        dep = deps.library_dependencies[0]
        assert dep.url == "griptape-ai/nodes-opencolorio@v1.2.0"
        assert dep.required is False

    def test_library_dependencies_empty_list(self) -> None:
        deps = Dependencies(library_dependencies=[])
        assert deps.library_dependencies == []

    def test_schema_version_bumped(self) -> None:
        assert LibrarySchema.LATEST_SCHEMA_VERSION == "0.9.0"


class TestLibraryDependencyProblem:
    """Tests for the LibraryDependencyProblem fitness problem."""

    def test_single_problem_message(self) -> None:
        problem = LibraryDependencyProblem(
            dependency_name="griptape-ai/nodes-opencolorio@v1.2.0",
            error_message="Clone failed",
        )
        msg = LibraryDependencyProblem.collate_problems_for_display([problem])
        assert "griptape-ai/nodes-opencolorio@v1.2.0" in msg
        assert "Clone failed" in msg

    def test_multiple_problems_message_includes_errors(self) -> None:
        problems = [
            LibraryDependencyProblem(dependency_name="dep-a@v1", error_message="err1"),
            LibraryDependencyProblem(dependency_name="dep-b@v2", error_message="err2"),
        ]
        msg = LibraryDependencyProblem.collate_problems_for_display(problems)
        assert "dep-a@v1" in msg
        assert "dep-b@v2" in msg
        assert "err1" in msg
        assert "err2" in msg


def _make_lib_info() -> LibraryManager.LibraryInfo:
    """Create a LibraryInfo in EVALUATED state ready for the dep-resolution step."""
    return LibraryManager.LibraryInfo(
        lifecycle_state=LibraryManager.LibraryLifecycleState.EVALUATED,
        library_path="/mock.json",
        is_sandbox=False,
        library_name="test_lib",
        library_version="1.0.0",
        fitness=LibraryManager.LibraryFitness.GOOD,
        problems=[],
    )


def _make_schema_mock(library_dependencies: list[str] | None, *, optional: bool = False) -> MagicMock:
    schema = MagicMock()
    schema.name = "test_lib"
    schema.metadata.library_version = "1.0.0"
    if library_dependencies is None:
        schema.metadata.dependencies.library_dependencies = None
    else:
        schema.metadata.dependencies.library_dependencies = [
            LibraryDependency(url=url, required=not optional) for url in library_dependencies
        ]
    return schema


def _metadata_success(schema: MagicMock) -> LoadLibraryMetadataFromFileResultSuccess:
    return LoadLibraryMetadataFromFileResultSuccess(
        library_schema=schema,
        file_path="/mock.json",
        git_remote=None,
        git_ref=None,
        result_details=ResultDetails(message="OK", level=20),
    )


# Sentinel failure used to stop the lifecycle after EVALUATED without entering the LOADED step.
_INSTALL_STOP = InstallLibraryDependenciesResultFailure(result_details="stop-sentinel")


class TestLibraryDependencyResolution:
    """Tests for library dependency resolution in the EVALUATED lifecycle step.

    Each test drives _progress_library_through_lifecycle with a LibraryInfo pre-set
    to EVALUATED and mocks install_library_dependencies_request to return failure so
    the lifecycle stops cleanly after the dependency-resolution block, without needing
    to mock the full LOADED phase (node imports, LibraryRegistry, sys.path, etc.).
    """

    @pytest.mark.asyncio
    async def test_no_library_dependencies_skips_download(self, griptape_nodes: GriptapeNodes) -> None:
        """A library with no library_dependencies does not call download_library_request."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()

        with (
            patch.object(
                mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(_make_schema_mock(None))
            ),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(mgr, "download_library_request") as mock_download,
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_library_dependencies_skips_download(self, griptape_nodes: GriptapeNodes) -> None:
        """A library with library_dependencies=[] does not call download_library_request."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()

        with (
            patch.object(
                mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(_make_schema_mock([]))
            ),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(mgr, "download_library_request") as mock_download,
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_tracked_dependency_skips_download(self, griptape_nodes: GriptapeNodes) -> None:
        """If the dep repo name appears in an existing tracked path, download is skipped."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-opencolorio@v1.2.0"])

        existing_paths = {
            "/workspace/libraries/nodes-opencolorio/griptape_nodes_library.json": MagicMock(),
            "/mock.json": lib_info,
        }

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(mgr, "download_library_request") as mock_download,
            patch.object(mgr, "_library_file_path_to_info", existing_paths),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_dependency_triggers_download(self, griptape_nodes: GriptapeNodes) -> None:
        """A dep not yet tracked causes download_library_request to be called with correct args."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-dep@v1.0.0"])

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(
                mgr,
                "download_library_request",
                new_callable=AsyncMock,
                return_value=DownloadLibraryResultSuccess(
                    library_name="nodes-dep",
                    library_path="/workspace/libraries/nodes-dep/griptape_nodes_library.json",
                    result_details="Downloaded",
                ),
            ) as mock_download,
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_called_once()
        req = mock_download.call_args[0][0]
        assert req.git_url == "https://github.com/griptape-ai/nodes-dep.git"
        assert req.branch_tag_commit == "v1.0.0"
        assert req.fail_on_exists is False
        assert req.auto_register is True

    @pytest.mark.asyncio
    async def test_dependency_failure_marks_library_unusable(self, griptape_nodes: GriptapeNodes) -> None:
        """When a dependency download fails, the library gets LibraryDependencyProblem and UNUSABLE fitness."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-bad@v1.0.0"])

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request") as mock_install,
            patch.object(
                mgr,
                "download_library_request",
                new_callable=AsyncMock,
                return_value=DownloadLibraryResultFailure(result_details="Clone failed"),
            ),
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            result = await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        assert isinstance(result, RegisterLibraryFromFileResultFailure)
        mock_install.assert_not_called()
        assert lib_info.fitness == LibraryManager.LibraryFitness.UNUSABLE
        dep_problems = [p for p in lib_info.problems if isinstance(p, LibraryDependencyProblem)]
        assert len(dep_problems) == 1
        assert "griptape-ai/nodes-bad@v1.0.0" in dep_problems[0].dependency_name

    @pytest.mark.asyncio
    async def test_dependency_resolved_before_pip_install(self, griptape_nodes: GriptapeNodes) -> None:
        """Library dependency download happens before pip package installation."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-dep@v1.0.0"])

        call_order: list[str] = []

        async def mock_download(_request: object) -> DownloadLibraryResultSuccess:
            call_order.append("download")
            return DownloadLibraryResultSuccess(
                library_name="nodes-dep",
                library_path="/workspace/libraries/nodes-dep/griptape_nodes_library.json",
                result_details="Downloaded",
            )

        async def mock_install(_request: object) -> InstallLibraryDependenciesResultFailure:
            call_order.append("install")
            return _INSTALL_STOP

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", side_effect=mock_install),
            patch.object(mgr, "download_library_request", side_effect=mock_download),
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        assert "download" in call_order
        assert "install" in call_order
        assert call_order.index("download") < call_order.index("install")

    @pytest.mark.asyncio
    async def test_never_behavior_skips_required_dep_and_marks_flawed(self, griptape_nodes: GriptapeNodes) -> None:
        """When install behavior is 'never', required deps are skipped and library is FLAWED."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-dep@v1.0.0"])

        config_mock = MagicMock()
        config_mock.get_config_value.return_value = LibraryDependencyInstallBehavior.NEVER

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(mgr, "download_library_request") as mock_download,
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
            patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn,
        ):
            mock_gtn.ConfigManager.return_value = config_mock
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_not_called()
        assert lib_info.fitness == LibraryManager.LibraryFitness.FLAWED
        dep_problems = [p for p in lib_info.problems if isinstance(p, LibraryDependencyProblem)]
        assert len(dep_problems) == 1
        assert "nodes-dep" in dep_problems[0].dependency_name

    @pytest.mark.asyncio
    async def test_never_behavior_skips_optional_dep_without_problem(self, griptape_nodes: GriptapeNodes) -> None:
        """When install behavior is 'never', optional deps are silently skipped."""
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-dep@v1.0.0"], optional=True)

        config_mock = MagicMock()
        config_mock.get_config_value.return_value = LibraryDependencyInstallBehavior.NEVER

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP),
            patch.object(mgr, "download_library_request") as mock_download,
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
            patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn,
        ):
            mock_gtn.ConfigManager.return_value = config_mock
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        mock_download.assert_not_called()
        assert lib_info.fitness == LibraryManager.LibraryFitness.GOOD
        dep_problems = [p for p in lib_info.problems if isinstance(p, LibraryDependencyProblem)]
        assert len(dep_problems) == 0

    @pytest.mark.asyncio
    async def test_optional_dep_failure_does_not_fail_registration(self, griptape_nodes: GriptapeNodes) -> None:
        """When an optional dep download fails, the lifecycle continues past the dep block.

        Unlike a required dep failure (which returns early before pip install), an optional
        dep failure only logs a warning. The lifecycle proceeds to install_library_dependencies,
        so mock_install must be called and no LibraryDependencyProblem must be recorded.
        """
        mgr = griptape_nodes.LibraryManager()
        lib_info = _make_lib_info()
        schema = _make_schema_mock(["griptape-ai/nodes-optional@v1.0.0"], optional=True)

        with (
            patch.object(mgr, "load_library_metadata_from_file_request", return_value=_metadata_success(schema)),
            patch.object(mgr, "install_library_dependencies_request", return_value=_INSTALL_STOP) as mock_install,
            patch.object(
                mgr,
                "download_library_request",
                new_callable=AsyncMock,
                return_value=DownloadLibraryResultFailure(result_details="Clone failed"),
            ),
            patch.object(mgr, "_library_file_path_to_info", {"/mock.json": lib_info}),
        ):
            await mgr._progress_library_through_lifecycle(
                library_info=lib_info,
                file_path="/mock.json",
                request=RegisterLibraryFromFileRequest(file_path="/mock.json"),
            )

        # install was reached (we did NOT return early like required deps do)
        mock_install.assert_called()
        # no dependency problem recorded for an optional dep
        dep_problems = [p for p in lib_info.problems if isinstance(p, LibraryDependencyProblem)]
        assert len(dep_problems) == 0
