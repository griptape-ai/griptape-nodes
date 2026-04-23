import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import anyio

if TYPE_CHECKING:
    from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.workflow_events import (
    CreateWorkflowFromTemplateRequest,
    CreateWorkflowFromTemplateResultFailure,
    CreateWorkflowFromTemplateResultSuccess,
    GetWorkflowInfoRequest,
    GetWorkflowInfoResultFailure,
    GetWorkflowInfoResultSuccess,
    GetWorkflowMetadataRequest,
    GetWorkflowMetadataResultFailure,
    GetWorkflowMetadataResultSuccess,
    ImportWorkflowRequest,
    ImportWorkflowResultFailure,
    ImportWorkflowResultSuccess,
    ListAllWorkflowInfoRequest,
    ListAllWorkflowInfoResultFailure,
    ListAllWorkflowInfoResultSuccess,
    LoadWorkflowMetadataResultFailure,
    LoadWorkflowMetadataResultSuccess,
    MoveWorkflowRequest,
    MoveWorkflowResultFailure,
    MoveWorkflowResultSuccess,
    RegisterWorkflowResultFailure,
    RegisterWorkflowResultSuccess,
    SetWorkflowMetadataRequest,
    SetWorkflowMetadataResultSuccess,
    WorkflowDependencyInfo,
    WorkflowDependencyStatus,
    WorkflowInfoSummary,
    WorkflowStatus,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager


class TestWorkflowManager:
    """Test WorkflowManager functionality including parameter serialization."""

    def test_convert_parameter_to_minimal_dict_serializes_settable_correctly(self) -> None:
        """Test that _convert_parameter_to_minimal_dict properly serializes settable as boolean."""
        # Create a test parameter
        param = Parameter(
            name="test_param",
            tooltip="Test parameter",
            type="str",
            default_value="test_value",
            settable=True,
            user_defined=False,
        )

        # Call the method under test
        result = WorkflowManager._convert_parameter_to_minimal_dict(param)

        # Assert that settable is properly serialized as a boolean
        assert "settable" in result
        assert isinstance(result["settable"], bool)
        assert result["settable"] is True

        # Assert that is_user_defined is properly serialized as a boolean
        assert "is_user_defined" in result
        assert isinstance(result["is_user_defined"], bool)

        # Assert that other expected fields are present
        assert result["name"] == "test_param"
        assert result["tooltip"] == "Test parameter"
        assert result["type"] == "str"
        assert result["default_value"] == "test_value"

    def test_convert_parameter_to_minimal_dict_handles_false_settable(self) -> None:
        """Test that _convert_parameter_to_minimal_dict handles settable=False correctly."""
        # Create a test parameter with settable=False
        param = Parameter(
            name="readonly_param", tooltip="Read-only parameter", type="int", settable=False, user_defined=True
        )

        # Call the method under test
        result = WorkflowManager._convert_parameter_to_minimal_dict(param)

        # Assert that settable is properly serialized as False
        assert "settable" in result
        assert isinstance(result["settable"], bool)
        assert result["settable"] is False

        # Assert that is_user_defined is properly serialized as True
        assert "is_user_defined" in result
        assert isinstance(result["is_user_defined"], bool)
        assert result["is_user_defined"] is True

    def test_on_import_workflow_request_success(self, griptape_nodes: GriptapeNodes) -> None:
        """Test successful workflow import."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ImportWorkflowRequest(file_path="/path/to/workflow.py")

        mock_metadata = MagicMock()
        mock_metadata.name = "test_workflow"

        with (
            patch.object(
                workflow_manager,
                "on_load_workflow_metadata_request",
                return_value=LoadWorkflowMetadataResultSuccess(metadata=mock_metadata, result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "has_workflow_with_name", return_value=False),
            patch.object(
                workflow_manager,
                "on_register_workflow_request",
                # Registry key is the file path (minus extension), independent of metadata.name.
                return_value=RegisterWorkflowResultSuccess(workflow_name="workflow", result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/full/path/to/workflow.py"),
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultSuccess)
            # Registry key is derived from the file path (minus extension), not from metadata.name.
            assert result.workflow_name == "workflow"

    def test_on_import_workflow_request_already_registered(self, griptape_nodes: GriptapeNodes) -> None:
        """Test import when workflow is already registered."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ImportWorkflowRequest(file_path="/path/to/workflow.py")

        mock_metadata = MagicMock()
        mock_metadata.name = "test_workflow"

        with (
            patch.object(
                workflow_manager,
                "on_load_workflow_metadata_request",
                return_value=LoadWorkflowMetadataResultSuccess(metadata=mock_metadata, result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "has_workflow_with_name", return_value=True),
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultSuccess)
            # Registry key is derived from the file path (minus extension), not from metadata.name.
            assert result.workflow_name == "/path/to/workflow"

    def test_on_import_workflow_request_metadata_load_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """Test import when metadata loading fails."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ImportWorkflowRequest(file_path="/path/to/workflow.py")

        with patch.object(
            workflow_manager,
            "on_load_workflow_metadata_request",
            return_value=LoadWorkflowMetadataResultFailure(result_details="Failed to load metadata"),
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultFailure)
            assert isinstance(result.result_details, ResultDetails)
            assert result.result_details.result_details[0].message == "Failed to load metadata"

    def test_on_import_workflow_request_registration_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """Test import when registration fails."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ImportWorkflowRequest(file_path="/path/to/workflow.py")

        mock_metadata = MagicMock()
        mock_metadata.name = "test_workflow"

        with (
            patch.object(
                workflow_manager,
                "on_load_workflow_metadata_request",
                return_value=LoadWorkflowMetadataResultSuccess(metadata=mock_metadata, result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "has_workflow_with_name", return_value=False),
            patch.object(
                workflow_manager,
                "on_register_workflow_request",
                return_value=RegisterWorkflowResultFailure(result_details="Registration failed"),
            ),
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultFailure)
            assert isinstance(result.result_details, ResultDetails)
            assert result.result_details.result_details[0].message == "Registration failed"

    def test_get_workflow_metadata_success(self, griptape_nodes: GriptapeNodes) -> None:
        """Ensure GetWorkflowMetadataRequest returns workflow.metadata directly."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = GetWorkflowMetadataRequest(workflow_name="my_workflow")

        mock_metadata = MagicMock()
        mock_workflow = MagicMock()
        mock_workflow.metadata = mock_metadata

        with patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow):
            result = workflow_manager.on_get_workflow_metadata_request(request)

        assert isinstance(result, GetWorkflowMetadataResultSuccess)
        assert result.workflow_metadata is mock_metadata

    def test_get_workflow_metadata_not_found(self, griptape_nodes: GriptapeNodes) -> None:
        """Ensure GetWorkflowMetadataRequest returns failure when workflow missing."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = GetWorkflowMetadataRequest(workflow_name="missing_workflow")

        with patch.object(WorkflowRegistry, "get_workflow_by_name", side_effect=KeyError("not found")):
            result = workflow_manager.on_get_workflow_metadata_request(request)

        assert isinstance(result, GetWorkflowMetadataResultFailure)

    def test_set_workflow_metadata_success(self, griptape_nodes: GriptapeNodes) -> None:
        """Ensure SetWorkflowMetadataRequest replaces metadata and persists header."""
        workflow_manager = griptape_nodes.WorkflowManager()
        workflow_manager._workflows_loading_complete.set()  # type: ignore[attr-defined]

        # Provide a full metadata object (mock is fine as we stub header replacement)
        mock_new_metadata = MagicMock()
        mock_new_metadata.name = "my_workflow"
        request = SetWorkflowMetadataRequest(workflow_name="my_workflow", workflow_metadata=mock_new_metadata)

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/my_workflow.py"
        existing_content = "# /// script\n# [tool]\n# ///\nprint('body')\n"

        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "is_file", return_value=True),
            patch.object(anyio.Path, "read_text", AsyncMock(return_value=existing_content)),
            patch.object(workflow_manager, "_replace_workflow_metadata_header", return_value="updated"),
            patch.object(
                workflow_manager,
                "_write_workflow_file",
                return_value=WorkflowManager.WriteWorkflowFileResult(success=True, error_details=""),
            ) as write_mock,
        ):
            result = asyncio.run(workflow_manager.on_set_workflow_metadata_request(request))  # type: ignore[attr-defined]

        assert isinstance(result, SetWorkflowMetadataResultSuccess)
        write_mock.assert_called_once()

    def test_on_create_workflow_from_template_request_success(self, griptape_nodes: GriptapeNodes) -> None:
        """Test successful create workflow from template (Griptape or user-provided)."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = CreateWorkflowFromTemplateRequest(template_name="my_template")

        mock_template = MagicMock()
        mock_template.file_path = "libraries/lib/workflows/templates/my_template.py"
        mock_template.metadata = MagicMock()
        mock_template.metadata.is_template = True
        mock_template.metadata.schema_version = "0.16.0"
        mock_template.metadata.engine_version_created_with = "1.0.0"
        mock_template.metadata.node_libraries_referenced = []
        mock_template.metadata.node_types_used = set()
        mock_template.metadata.workflows_referenced = None
        mock_template.metadata.description = "A template"
        mock_template.metadata.image = None
        mock_template.metadata.last_modified_date = None

        template_content = "# /// script\n# [tool]\n# ///\nprint('body')\n"
        new_full_path = "/workspace/my_template_1.py"

        def get_complete_file_path(relative_path: str) -> str:
            if "templates" in relative_path:
                return "/lib/path/my_template.py"
            return new_full_path

        with (
            patch.object(
                WorkflowRegistry,
                "get_workflow_by_name",
                return_value=mock_template,
            ),
            patch.object(
                WorkflowRegistry,
                "get_complete_file_path",
                side_effect=get_complete_file_path,
            ),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "read_text", return_value=template_content),
            patch.object(
                workflow_manager,
                "_generate_unique_filename",
                return_value="my_template_1",
            ),
            patch.object(
                workflow_manager,
                "_replace_workflow_metadata_header",
                return_value="updated_content",
            ),
            patch.object(Path, "write_text"),
            patch.object(WorkflowRegistry, "generate_new_workflow"),
        ):
            result = workflow_manager.on_create_workflow_from_template_request(request)

        assert isinstance(result, CreateWorkflowFromTemplateResultSuccess)
        assert result.workflow_name == "my_template_1"
        assert result.file_path == new_full_path

    def test_on_create_workflow_from_template_request_absolute_file_path(self, griptape_nodes: GriptapeNodes) -> None:
        """Test that templates with absolute file paths save the new workflow in the workspace, not at the template path."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = CreateWorkflowFromTemplateRequest(
            template_name="/some/external/library/workflows/templates/my_template"
        )

        mock_template = MagicMock()
        mock_template.file_path = "/some/external/library/workflows/templates/my_template.py"
        mock_template.metadata = MagicMock()
        mock_template.metadata.is_template = True
        mock_template.metadata.schema_version = "0.16.0"
        mock_template.metadata.engine_version_created_with = "1.0.0"
        mock_template.metadata.node_libraries_referenced = []
        mock_template.metadata.node_types_used = set()
        mock_template.metadata.workflows_referenced = None
        mock_template.metadata.description = "A template"
        mock_template.metadata.image = None
        mock_template.metadata.last_modified_date = None

        template_content = "# /// script\n# [tool]\n# ///\nprint('body')\n"
        new_full_path = "/workspace/my_template.py"

        generate_unique_filename_calls = []

        def capture_generate_unique_filename(base_name: str) -> str:
            generate_unique_filename_calls.append(base_name)
            return "my_template"

        with (
            patch.object(
                WorkflowRegistry,
                "get_workflow_by_name",
                return_value=mock_template,
            ),
            patch.object(
                WorkflowRegistry,
                "get_complete_file_path",
                return_value=new_full_path,
            ),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "read_text", return_value=template_content),
            patch.object(
                workflow_manager,
                "_generate_unique_filename",
                side_effect=capture_generate_unique_filename,
            ),
            patch.object(
                workflow_manager,
                "_replace_workflow_metadata_header",
                return_value="updated_content",
            ),
            patch.object(Path, "write_text"),
            patch.object(WorkflowRegistry, "generate_new_workflow"),
        ):
            result = workflow_manager.on_create_workflow_from_template_request(request)

        assert isinstance(result, CreateWorkflowFromTemplateResultSuccess)
        # The base name passed to _generate_unique_filename must be just the stem,
        # not the full absolute path, so the file is saved in the workspace.
        assert generate_unique_filename_calls == ["my_template"]

    def test_on_create_workflow_from_template_request_template_not_found(self, griptape_nodes: GriptapeNodes) -> None:
        """Test create from template when template is not in registry."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = CreateWorkflowFromTemplateRequest(template_name="missing_template")

        with patch.object(
            WorkflowRegistry,
            "get_workflow_by_name",
            side_effect=KeyError("not found"),
        ):
            result = workflow_manager.on_create_workflow_from_template_request(request)

        assert isinstance(result, CreateWorkflowFromTemplateResultFailure)
        assert "missing_template" in str(result.result_details)

    def test_on_create_workflow_from_template_request_not_a_template(self, griptape_nodes: GriptapeNodes) -> None:
        """Test create from template when workflow is not marked as template."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = CreateWorkflowFromTemplateRequest(template_name="regular_workflow")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/regular_workflow.py"
        mock_workflow.metadata = MagicMock()
        mock_workflow.metadata.is_template = False

        with patch.object(
            WorkflowRegistry,
            "get_workflow_by_name",
            return_value=mock_workflow,
        ):
            result = workflow_manager.on_create_workflow_from_template_request(request)

        assert isinstance(result, CreateWorkflowFromTemplateResultFailure)
        assert "not marked as a template" in str(result.result_details)

    def test_on_create_workflow_from_template_request_template_file_not_found(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        """Test create from template when template file does not exist."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = CreateWorkflowFromTemplateRequest(template_name="my_template")

        mock_template = MagicMock()
        mock_template.file_path = "libraries/lib/workflows/templates/my_template.py"
        mock_template.metadata = MagicMock()
        mock_template.metadata.is_template = True

        with (
            patch.object(
                WorkflowRegistry,
                "get_workflow_by_name",
                return_value=mock_template,
            ),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/missing/path.py"),
            patch.object(Path, "is_file", return_value=False),
        ):
            result = workflow_manager.on_create_workflow_from_template_request(request)

        assert isinstance(result, CreateWorkflowFromTemplateResultFailure)
        assert "does not exist" in str(result.result_details)

    # Removed tests for invalid keys/types; metadata is replaced as a whole object

    def test_on_move_workflow_request_workflow_not_found(self, griptape_nodes: GriptapeNodes) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="nonexistent", target_directory="subdir")

        with patch.object(WorkflowRegistry, "get_workflow_by_name", side_effect=KeyError("not found")):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultFailure)
        assert "nonexistent" in str(result.result_details)

    def test_on_move_workflow_request_source_file_missing(self, griptape_nodes: GriptapeNodes) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "my_workflow.py"

        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "exists", return_value=False),
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultFailure)
        assert "/workspace/my_workflow.py" in str(result.result_details)

    def test_on_move_workflow_request_target_already_exists(self, griptape_nodes: GriptapeNodes) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "my_workflow.py"

        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "mkdir"),
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultFailure)
        assert "already exists" in str(result.result_details)

    def test_on_move_workflow_request_success_directory_change(self, griptape_nodes: GriptapeNodes) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "my_workflow.py"

        config_mgr = griptape_nodes.ConfigManager()
        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "exists", side_effect=[True, False]),
            patch.object(Path, "mkdir"),
            patch.object(Path, "rename"),
            patch.object(WorkflowRegistry, "rekey_workflow") as mock_rekey,
            patch.object(config_mgr, "delete_user_workflow"),
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultSuccess)
        assert result.moved_file_path == "subdir/my_workflow.py"
        assert result.new_workflow_name == "subdir/my_workflow"
        mock_rekey.assert_called_once_with("my_workflow", "subdir/my_workflow")

    def test_on_move_workflow_request_no_rekey_same_directory(self, griptape_nodes: GriptapeNodes) -> None:
        """Moving within the same directory level produces the same registry key; no rekey occurs."""
        workflow_manager = griptape_nodes.WorkflowManager()
        # Workflow already in "subdir", moving target is also "subdir" — key stays the same.
        request = MoveWorkflowRequest(workflow_name="subdir/my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "subdir/my_workflow.py"

        config_mgr = griptape_nodes.ConfigManager()
        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/subdir/my_workflow.py"),
            patch.object(Path, "exists", side_effect=[True, False]),
            patch.object(Path, "mkdir"),
            patch.object(Path, "rename"),
            patch.object(WorkflowRegistry, "rekey_workflow") as mock_rekey,
            patch.object(config_mgr, "delete_user_workflow"),
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultSuccess)
        assert result.new_workflow_name == "subdir/my_workflow"
        mock_rekey.assert_not_called()

    def test_on_move_workflow_request_updates_context_for_current_workflow(self, griptape_nodes: GriptapeNodes) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "my_workflow.py"

        context_mgr = griptape_nodes.ContextManager()
        config_mgr = griptape_nodes.ConfigManager()
        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "exists", side_effect=[True, False]),
            patch.object(Path, "mkdir"),
            patch.object(Path, "rename"),
            patch.object(WorkflowRegistry, "rekey_workflow"),
            patch.object(config_mgr, "delete_user_workflow"),
            patch.object(context_mgr, "has_current_workflow", return_value=True),
            patch.object(context_mgr, "get_current_workflow_name", return_value="my_workflow"),
            patch.object(context_mgr, "set_current_workflow_name") as mock_set_name,
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultSuccess)
        mock_set_name.assert_called_once_with("subdir/my_workflow")

    def test_on_move_workflow_request_does_not_update_context_for_other_workflow(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        workflow_manager = griptape_nodes.WorkflowManager()
        request = MoveWorkflowRequest(workflow_name="my_workflow", target_directory="subdir")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "my_workflow.py"

        context_mgr = griptape_nodes.ContextManager()
        config_mgr = griptape_nodes.ConfigManager()
        with (
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/workspace/my_workflow.py"),
            patch.object(Path, "exists", side_effect=[True, False]),
            patch.object(Path, "mkdir"),
            patch.object(Path, "rename"),
            patch.object(WorkflowRegistry, "rekey_workflow"),
            patch.object(config_mgr, "delete_user_workflow"),
            patch.object(context_mgr, "has_current_workflow", return_value=True),
            patch.object(context_mgr, "get_current_workflow_name", return_value="other_workflow"),
            patch.object(context_mgr, "set_current_workflow_name") as mock_set_name,
        ):
            result = workflow_manager.on_move_workflow_request(request)

        assert isinstance(result, MoveWorkflowResultSuccess)
        mock_set_name.assert_not_called()

    # --- WorkflowInfo payload helpers ---

    def test_build_workflow_info_key_uses_workspace_join(self, griptape_nodes: GriptapeNodes) -> None:
        """_build_workflow_info_key matches the key construction used when storing info (no symlink resolution)."""
        workflow_manager = griptape_nodes.WorkflowManager()
        workspace = griptape_nodes.ConfigManager().workspace_path

        key = workflow_manager._build_workflow_info_key("workflows/my_workflow.py")

        assert key == str(workspace / "workflows/my_workflow.py")

    def test_build_workflow_info_payload_good_status_no_problems(self, griptape_nodes: GriptapeNodes) -> None:
        """_build_workflow_info_payload produces correct payload for a GOOD workflow with no problems."""
        from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

        workflow_manager = griptape_nodes.WorkflowManager()
        wf_info = WorkflowManager.WorkflowInfo(
            status=WorkflowStatus.GOOD,
            workflow_path="/workspace/workflows/my_workflow.py",
            workflow_name="my_workflow",
        )

        payload = workflow_manager._build_workflow_info_payload(wf_info)

        assert isinstance(payload, WorkflowInfoSummary)
        assert payload.status == "GOOD"
        assert payload.workflow_name == "my_workflow"
        assert payload.workflow_path == "/workspace/workflows/my_workflow.py"
        assert payload.problems == []
        assert payload.workflow_dependencies == []

    def test_build_workflow_info_payload_collates_problems(self, griptape_nodes: GriptapeNodes) -> None:
        """_build_workflow_info_payload calls collate_problems_for_display on each problem type."""
        from griptape_nodes.retained_mode.managers.fitness_problems.workflows.library_not_registered_problem import (
            LibraryNotRegisteredProblem,
        )
        from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

        workflow_manager = griptape_nodes.WorkflowManager()
        wf_info = WorkflowManager.WorkflowInfo(
            status=WorkflowStatus.UNUSABLE,
            workflow_path="/workspace/workflows/broken.py",
            workflow_name="broken",
            problems=[
                LibraryNotRegisteredProblem(library_name="lib-a"),
                LibraryNotRegisteredProblem(library_name="lib-b"),
            ],
        )

        payload = workflow_manager._build_workflow_info_payload(wf_info)

        assert len(payload.problems) == 1
        assert "lib-a" in payload.problems[0]
        assert "lib-b" in payload.problems[0]

    def test_build_workflow_info_payload_includes_dependencies(self, griptape_nodes: GriptapeNodes) -> None:
        """_build_workflow_info_payload passes WorkflowDependencyInfo instances through directly."""
        from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

        workflow_manager = griptape_nodes.WorkflowManager()
        wf_info = WorkflowManager.WorkflowInfo(
            status=WorkflowStatus.FLAWED,
            workflow_path="/workspace/workflows/flawed.py",
            workflow_name="flawed",
            workflow_dependencies=[
                WorkflowDependencyInfo(
                    library_name="my-lib",
                    version_requested="1.0.0",
                    version_present="1.1.0",
                    status=WorkflowDependencyStatus.CAUTION,
                )
            ],
        )

        payload = workflow_manager._build_workflow_info_payload(wf_info)

        assert len(payload.workflow_dependencies) == 1
        dep = payload.workflow_dependencies[0]
        assert isinstance(dep, WorkflowDependencyInfo)
        assert dep.library_name == "my-lib"
        assert dep.version_requested == "1.0.0"
        assert dep.version_present == "1.1.0"
        assert dep.status == "CAUTION"

    # --- GetWorkflowInfoRequest ---

    def test_on_get_workflow_info_request_workflow_not_in_registry_fails(self, griptape_nodes: GriptapeNodes) -> None:
        """GetWorkflowInfoRequest with unknown workflow_name returns failure."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = GetWorkflowInfoRequest(workflow_name="missing_workflow")

        with patch.object(WorkflowRegistry, "get_workflow_by_name", side_effect=KeyError("not found")):
            result = workflow_manager.on_get_workflow_info_request(request)

        assert isinstance(result, GetWorkflowInfoResultFailure)
        assert "missing_workflow" in str(result.result_details)

    def test_on_get_workflow_info_request_no_info_for_path_fails(self, griptape_nodes: GriptapeNodes) -> None:
        """GetWorkflowInfoRequest returns failure when no WorkflowInfo is stored for the resolved path."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = GetWorkflowInfoRequest(workflow_name="my_workflow")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/my_workflow.py"

        with patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow):
            # _workflow_file_path_to_info is empty, so no info will be found
            result = workflow_manager.on_get_workflow_info_request(request)

        assert isinstance(result, GetWorkflowInfoResultFailure)

    def test_on_get_workflow_info_request_success(self, griptape_nodes: GriptapeNodes) -> None:
        """GetWorkflowInfoRequest succeeds when WorkflowInfo exists for the workflow."""
        from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

        workflow_manager = griptape_nodes.WorkflowManager()
        request = GetWorkflowInfoRequest(workflow_name="my_workflow")

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/my_workflow.py"

        workspace = griptape_nodes.ConfigManager().workspace_path
        info_key = str(workspace / "workflows/my_workflow.py")
        wf_info = WorkflowManager.WorkflowInfo(
            status=WorkflowStatus.GOOD,
            workflow_path=info_key,
            workflow_name="my_workflow",
        )
        workflow_manager._workflow_file_path_to_info[info_key] = wf_info

        with patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow):
            result = workflow_manager.on_get_workflow_info_request(request)

        assert isinstance(result, GetWorkflowInfoResultSuccess)
        assert result.status == "GOOD"
        assert result.workflow_name == "my_workflow"
        assert result.problems == []
        assert result.workflow_dependencies == []

    # --- ListAllWorkflowInfoRequest ---

    def test_on_list_all_workflow_info_request_registry_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """ListAllWorkflowInfoRequest returns failure when listing workflows raises."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ListAllWorkflowInfoRequest()

        with patch.object(WorkflowRegistry, "list_workflows", side_effect=Exception("registry error")):
            result = workflow_manager.on_list_all_workflow_info_request(request)

        assert isinstance(result, ListAllWorkflowInfoResultFailure)
        assert "registry error" in str(result.result_details)

    def test_on_list_all_workflow_info_request_success(self, griptape_nodes: GriptapeNodes) -> None:
        """ListAllWorkflowInfoRequest returns info for every workflow that has a stored WorkflowInfo."""
        from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

        workflow_manager = griptape_nodes.WorkflowManager()
        request = ListAllWorkflowInfoRequest()

        workspace = griptape_nodes.ConfigManager().workspace_path
        info_key = str(workspace / "workflows/my_workflow.py")
        wf_info = WorkflowManager.WorkflowInfo(
            status=WorkflowStatus.GOOD,
            workflow_path=info_key,
            workflow_name="my_workflow",
        )
        workflow_manager._workflow_file_path_to_info[info_key] = wf_info

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/my_workflow.py"

        with (
            patch.object(WorkflowRegistry, "list_workflows", return_value=["my_workflow"]),
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
        ):
            result = workflow_manager.on_list_all_workflow_info_request(request)

        assert isinstance(result, ListAllWorkflowInfoResultSuccess)
        assert "my_workflow" in result.workflow_infos
        assert result.workflow_infos["my_workflow"].status == "GOOD"

    def test_on_list_all_workflow_info_request_skips_workflows_without_info(
        self, griptape_nodes: GriptapeNodes
    ) -> None:
        """ListAllWorkflowInfoRequest omits workflows that have no stored WorkflowInfo."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ListAllWorkflowInfoRequest()

        mock_workflow = MagicMock()
        mock_workflow.file_path = "workflows/my_workflow.py"

        with (
            patch.object(WorkflowRegistry, "list_workflows", return_value=["my_workflow"]),
            patch.object(WorkflowRegistry, "get_workflow_by_name", return_value=mock_workflow),
        ):
            # _workflow_file_path_to_info is empty, so the workflow is skipped
            result = workflow_manager.on_list_all_workflow_info_request(request)

        assert isinstance(result, ListAllWorkflowInfoResultSuccess)
        assert result.workflow_infos == {}

    def test_on_list_all_workflow_info_request_skips_unknown_registry_keys(self, griptape_nodes: GriptapeNodes) -> None:
        """ListAllWorkflowInfoRequest skips registry keys that can't be looked up."""
        workflow_manager = griptape_nodes.WorkflowManager()
        request = ListAllWorkflowInfoRequest()

        with (
            patch.object(WorkflowRegistry, "list_workflows", return_value=["ghost_workflow"]),
            patch.object(WorkflowRegistry, "get_workflow_by_name", side_effect=KeyError("not found")),
        ):
            result = workflow_manager.on_list_all_workflow_info_request(request)

        assert isinstance(result, ListAllWorkflowInfoResultSuccess)
        assert result.workflow_infos == {}

    # --- _build_workflow_save_path ---

    def test_build_workflow_save_path_resolves_via_situation(self, griptape_nodes: GriptapeNodes) -> None:
        """Resolved paths inside the workspace yield a workspace-relative registry key."""
        workflow_manager = griptape_nodes.WorkflowManager()
        workspace = griptape_nodes.ConfigManager().workspace_path
        resolved_path = workspace / "my_workflow.py"

        fake_destination = MagicMock()
        fake_destination.resolve.return_value = str(resolved_path)

        with patch(
            "griptape_nodes.retained_mode.managers.workflow_manager.ProjectFileDestination.from_situation",
            return_value=fake_destination,
        ) as mock_from_situation:
            save_path = workflow_manager._build_workflow_save_path("my_workflow.py")

        mock_from_situation.assert_called_once_with("my_workflow.py", "save_workflow")
        assert save_path.file_path == resolved_path
        assert save_path.relative_file_path == "my_workflow.py"

    def test_build_workflow_save_path_preserves_sub_dirs(self, griptape_nodes: GriptapeNodes) -> None:
        """sub_dirs are passed to the situation and reflected in the resolved workspace-relative key."""
        workflow_manager = griptape_nodes.WorkflowManager()
        workspace = griptape_nodes.ConfigManager().workspace_path
        resolved_path = workspace / "team" / "my_workflow.py"

        fake_destination = MagicMock()
        fake_destination.resolve.return_value = str(resolved_path)

        with patch(
            "griptape_nodes.retained_mode.managers.workflow_manager.ProjectFileDestination.from_situation",
            return_value=fake_destination,
        ) as mock_from_situation:
            save_path = workflow_manager._build_workflow_save_path("my_workflow.py", sub_dirs="team")

        mock_from_situation.assert_called_once_with("my_workflow.py", "save_workflow", sub_dirs="team")
        assert save_path.file_path == resolved_path
        assert save_path.relative_file_path == str(Path("team") / "my_workflow.py")

    def test_build_workflow_save_path_uses_absolute_when_outside_workspace(
        self, griptape_nodes: GriptapeNodes, tmp_path: Path
    ) -> None:
        """Paths outside the workspace fall back to the absolute path as the registry key."""
        workflow_manager = griptape_nodes.WorkflowManager()
        outside_path = tmp_path / "elsewhere" / "my_workflow.py"

        fake_destination = MagicMock()
        fake_destination.resolve.return_value = str(outside_path)

        with patch(
            "griptape_nodes.retained_mode.managers.workflow_manager.ProjectFileDestination.from_situation",
            return_value=fake_destination,
        ):
            save_path = workflow_manager._build_workflow_save_path("my_workflow.py")

        assert save_path.file_path == outside_path
        assert save_path.relative_file_path == str(outside_path)

    def test_build_workflow_save_path_falls_back_on_file_load_error(self, griptape_nodes: GriptapeNodes) -> None:
        """If the situation cannot resolve, we fall back to joining against the workspace path."""
        from griptape_nodes.files.file import FileLoadError
        from griptape_nodes.retained_mode.events.os_events import FileIOFailureReason

        workflow_manager = griptape_nodes.WorkflowManager()
        workspace = griptape_nodes.ConfigManager().workspace_path

        fake_destination = MagicMock()
        fake_destination.resolve.side_effect = FileLoadError(FileIOFailureReason.UNKNOWN, "no project loaded")

        with patch(
            "griptape_nodes.retained_mode.managers.workflow_manager.ProjectFileDestination.from_situation",
            return_value=fake_destination,
        ):
            save_path = workflow_manager._build_workflow_save_path("my_workflow.py", sub_dirs="team")

        assert save_path.file_path == workspace / "team" / "my_workflow.py"
        assert save_path.relative_file_path == str(Path("team") / "my_workflow.py")


class TestWorkflowVariablePersistence:
    """Round-trip tests: variables created in a flow must survive save + load."""

    def _fresh_metadata(self, name: str = "test_workflow") -> "WorkflowMetadata":
        from griptape_nodes.node_library.workflow_registry import WorkflowMetadata

        return WorkflowMetadata(
            name=name,
            schema_version=WorkflowMetadata.LATEST_SCHEMA_VERSION,
            engine_version_created_with="0.0.0",
            node_libraries_referenced=[],
        )

    def test_generate_create_variable_code_emits_expected_call(self, griptape_nodes: GriptapeNodes) -> None:
        """The AST helper should produce a single CreateVariableRequest call per command."""
        import ast

        from griptape_nodes.retained_mode.events.flow_events import SerializedFlowCommands
        from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands
        from griptape_nodes.retained_mode.events.variable_events import CreateVariableRequest
        from griptape_nodes.retained_mode.managers.workflow_manager import ImportRecorder

        workflow_manager = griptape_nodes.WorkflowManager()
        import_recorder = ImportRecorder()

        serialized_command = SerializedFlowCommands.SerializedVariableCommand(
            create_variable_command=CreateVariableRequest(
                name="my_var",
                type="str",
                is_global=False,
                value=None,
                owning_flow="ControlFlow_1",
                initial_setup=True,
            ),
            unique_value_uuid=SerializedNodeCommands.UniqueParameterValueUUID("abc-uuid"),
        )

        stmts = workflow_manager._generate_create_variable_code(
            serialized_variable_commands=[serialized_command],
            unique_values_dict_name="top_level_unique_values_dict",
            import_recorder=import_recorder,
        )

        assert len(stmts) == 1
        rendered = ast.unparse(stmts[0])
        assert "CreateVariableRequest(" in rendered
        assert "name='my_var'" in rendered
        assert "type='str'" in rendered
        assert "is_global=False" in rendered
        assert "owning_flow='ControlFlow_1'" in rendered
        assert "initial_setup=True" in rendered
        assert "top_level_unique_values_dict['abc-uuid']" in rendered

        # Import recorder should have captured the CreateVariableRequest import.
        imports_text = import_recorder.generate_imports()
        assert "CreateVariableRequest" in imports_text

    def _push_clean_flow_context(self, griptape_nodes: GriptapeNodes, flow_name: str = "ControlFlow_1") -> str:
        """Clear state, push a workflow context, and create a single empty flow. Returns the flow name."""
        from griptape_nodes.retained_mode.events.flow_events import (
            CreateFlowRequest,
            CreateFlowResultSuccess,
        )

        variables_manager = griptape_nodes.VariablesManager()
        context_manager = griptape_nodes.ContextManager()

        GriptapeNodes.clear_data()
        variables_manager.on_clear_object_state()

        if not context_manager.has_current_workflow():
            context_manager.push_workflow(workflow_name="round_trip_workflow")

        flow_result = GriptapeNodes.handle_request(
            CreateFlowRequest(parent_flow_name=None, flow_name=flow_name, set_as_new_context=False)
        )
        assert isinstance(flow_result, CreateFlowResultSuccess)
        return flow_result.flow_name

    def test_declared_variable_gets_serialized(self, griptape_nodes: GriptapeNodes) -> None:
        """A flow-scoped variable that is declared via a VariableReference should be serialized."""
        from griptape_nodes.exe_types.node_types import VariableReference
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )
        from griptape_nodes.retained_mode.variable_types import VariableScope

        flow_manager = griptape_nodes.FlowManager()
        flow_name = self._push_clean_flow_context(griptape_nodes)

        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="declared_var", type="str", is_global=False, value="dog", owning_flow=flow_name
                )
            ),
            CreateVariableResultSuccess,
        )

        unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        commands = flow_manager._serialize_variables_for_flow(
            flow_name=flow_name,
            unique_parameter_uuid_to_values=unique_values,
            variable_references={VariableReference(name="declared_var", scope=VariableScope.CURRENT_FLOW_ONLY)},
        )

        assert {cmd.create_variable_command.name for cmd in commands} == {"declared_var"}
        assert len(unique_values) == 1

    def test_orphan_variable_is_dropped(self, griptape_nodes: GriptapeNodes) -> None:
        """A variable in engine state with no declared reference must not be serialized."""
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )

        flow_manager = griptape_nodes.FlowManager()
        flow_name = self._push_clean_flow_context(griptape_nodes)

        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="orphan_var", type="str", is_global=False, value="cat", owning_flow=flow_name
                )
            ),
            CreateVariableResultSuccess,
        )

        unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        commands = flow_manager._serialize_variables_for_flow(
            flow_name=flow_name,
            unique_parameter_uuid_to_values=unique_values,
            variable_references=set(),
        )

        assert commands == []
        assert unique_values == {}

    def test_declared_but_missing_variable_is_dropped(self, griptape_nodes: GriptapeNodes) -> None:
        """A reference to a variable that does not exist in the flow should not produce a command."""
        from griptape_nodes.exe_types.node_types import VariableReference
        from griptape_nodes.retained_mode.variable_types import VariableScope

        flow_manager = griptape_nodes.FlowManager()
        flow_name = self._push_clean_flow_context(griptape_nodes)

        unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        commands = flow_manager._serialize_variables_for_flow(
            flow_name=flow_name,
            unique_parameter_uuid_to_values=unique_values,
            variable_references={VariableReference(name="ghost", scope=VariableScope.CURRENT_FLOW_ONLY)},
        )

        assert commands == []

    def test_global_only_scope_is_skipped(self, griptape_nodes: GriptapeNodes) -> None:
        """GLOBAL_ONLY references are deferred for now and must not produce a command."""
        from griptape_nodes.exe_types.node_types import VariableReference
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )
        from griptape_nodes.retained_mode.variable_types import VariableScope

        flow_manager = griptape_nodes.FlowManager()
        flow_name = self._push_clean_flow_context(griptape_nodes)

        # Create a flow-scoped variable with the same name as a pretend-global. It should not match,
        # because the GLOBAL_ONLY scope is unsupported for serialization and must be skipped.
        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="shared_name", type="str", is_global=False, value="local", owning_flow=flow_name
                )
            ),
            CreateVariableResultSuccess,
        )

        unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        commands = flow_manager._serialize_variables_for_flow(
            flow_name=flow_name,
            unique_parameter_uuid_to_values=unique_values,
            variable_references={VariableReference(name="shared_name", scope=VariableScope.GLOBAL_ONLY)},
        )

        assert commands == []

    def test_hierarchical_reference_only_serializes_at_owning_flow(self, griptape_nodes: GriptapeNodes) -> None:
        """A HIERARCHICAL reference resolved against a child flow must not serialize an ancestor-owned variable."""
        from griptape_nodes.exe_types.node_types import VariableReference
        from griptape_nodes.retained_mode.events.flow_events import (
            CreateFlowRequest,
            CreateFlowResultSuccess,
        )
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )
        from griptape_nodes.retained_mode.variable_types import VariableScope

        flow_manager = griptape_nodes.FlowManager()
        parent_flow_name = self._push_clean_flow_context(griptape_nodes, flow_name="ParentFlow")

        child_flow_result = GriptapeNodes.handle_request(
            CreateFlowRequest(parent_flow_name=parent_flow_name, flow_name="ChildFlow", set_as_new_context=False)
        )
        assert isinstance(child_flow_result, CreateFlowResultSuccess)
        child_flow_name = child_flow_result.flow_name

        # Variable lives on the parent.
        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="ancestor_var",
                    type="str",
                    is_global=False,
                    value="from_parent",
                    owning_flow=parent_flow_name,
                )
            ),
            CreateVariableResultSuccess,
        )

        ref = VariableReference(name="ancestor_var", scope=VariableScope.HIERARCHICAL)

        # Child flow should not claim the parent-owned variable.
        child_unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        child_commands = flow_manager._serialize_variables_for_flow(
            flow_name=child_flow_name,
            unique_parameter_uuid_to_values=child_unique_values,
            variable_references={ref},
        )
        assert child_commands == []

        # Parent flow should claim it.
        parent_unique_values: dict[SerializedNodeCommands.UniqueParameterValueUUID, object] = {}
        parent_commands = flow_manager._serialize_variables_for_flow(
            flow_name=parent_flow_name,
            unique_parameter_uuid_to_values=parent_unique_values,
            variable_references={ref},
        )
        assert {cmd.create_variable_command.name for cmd in parent_commands} == {"ancestor_var"}

    def test_save_load_preserves_flow_scoped_variables(self, griptape_nodes: GriptapeNodes) -> None:
        """Round-trip: declare a flow-scoped variable, serialize, clear, exec, confirm it is restored."""
        from griptape_nodes.exe_types.node_types import NodeDependencies, VariableReference
        from griptape_nodes.retained_mode.events.flow_events import (
            SerializeFlowToCommandsRequest,
            SerializeFlowToCommandsResultSuccess,
        )
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
            GetVariableValueRequest,
            GetVariableValueResultSuccess,
        )
        from griptape_nodes.retained_mode.variable_types import VariableScope

        workflow_manager = griptape_nodes.WorkflowManager()
        variables_manager = griptape_nodes.VariablesManager()
        flow_name = self._push_clean_flow_context(griptape_nodes)

        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="flow_scoped_var", type="str", is_global=False, value="dog", owning_flow=flow_name
                )
            ),
            CreateVariableResultSuccess,
        )

        # Normally a node declares the reference via get_node_dependencies(); for this test we
        # inject the declaration directly onto the flow's aggregated NodeDependencies after
        # serialization gathers them. We do that by patching _aggregate_flow_dependencies to append
        # a VariableReference for our variable.
        from griptape_nodes.retained_mode.events.flow_events import SerializedFlowCommands
        from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands

        flow_manager = griptape_nodes.FlowManager()
        original_aggregate = flow_manager._aggregate_flow_dependencies

        def aggregate_with_declared_ref(
            serialized_node_commands: list[SerializedNodeCommands],
            sub_flows_commands: list[SerializedFlowCommands],
        ) -> NodeDependencies:
            deps = original_aggregate(serialized_node_commands, sub_flows_commands)
            deps.variable_references.add(
                VariableReference(name="flow_scoped_var", scope=VariableScope.CURRENT_FLOW_ONLY)
            )
            return deps

        with patch.object(
            flow_manager,
            "_aggregate_flow_dependencies",
            side_effect=aggregate_with_declared_ref,
        ):
            serialize_result = GriptapeNodes.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name))

        assert isinstance(serialize_result, SerializeFlowToCommandsResultSuccess)
        serialized_commands = serialize_result.serialized_flow_commands

        names_serialized = {
            cmd.create_variable_command.name for cmd in serialized_commands.serialized_variable_commands
        }
        assert names_serialized == {"flow_scoped_var"}

        # Generate the workflow script.
        metadata = self._fresh_metadata(name="test_round_trip")
        script_source = workflow_manager._generate_workflow_file_content(
            serialized_flow_commands=serialized_commands,
            workflow_metadata=metadata,
        )

        # Script must reference CreateVariableRequest for the flow-scoped variable.
        assert "CreateVariableRequest(" in script_source
        assert "name='flow_scoped_var'" in script_source

        # Clear everything, then exec the script and confirm the variable is rebuilt.
        GriptapeNodes.clear_data()
        variables_manager.on_clear_object_state()

        exec_globals: dict[str, object] = {"__file__": "test_workflow.py"}
        exec(compile(script_source, "<round_trip_test>", "exec"), exec_globals)  # noqa: S102

        flow_value = GriptapeNodes.handle_request(
            GetVariableValueRequest(
                name="flow_scoped_var", starting_flow=flow_name, lookup_scope=VariableScope.CURRENT_FLOW_ONLY
            )
        )
        assert isinstance(flow_value, GetVariableValueResultSuccess)
        assert flow_value.value == "dog"

    def test_save_drops_orphan_variables_end_to_end(self, griptape_nodes: GriptapeNodes) -> None:
        """The var.py scenario: a variable with no declaring node must not survive serialization."""
        from griptape_nodes.retained_mode.events.flow_events import (
            SerializeFlowToCommandsRequest,
            SerializeFlowToCommandsResultSuccess,
        )
        from griptape_nodes.retained_mode.events.variable_events import (
            CreateVariableRequest,
            CreateVariableResultSuccess,
        )

        flow_name = self._push_clean_flow_context(griptape_nodes)

        # Simulate the bug: a variable was created (via some now-deleted SetVariable node) but no
        # node currently declares it.
        assert isinstance(
            GriptapeNodes.handle_request(
                CreateVariableRequest(
                    name="orphan_var", type="str", is_global=False, value="stale", owning_flow=flow_name
                )
            ),
            CreateVariableResultSuccess,
        )

        serialize_result = GriptapeNodes.handle_request(SerializeFlowToCommandsRequest(flow_name=flow_name))
        assert isinstance(serialize_result, SerializeFlowToCommandsResultSuccess)
        assert serialize_result.serialized_flow_commands.serialized_variable_commands == []
