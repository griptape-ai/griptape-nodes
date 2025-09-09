from unittest.mock import MagicMock, patch

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.workflow_events import (
    ImportWorkflowRequest,
    ImportWorkflowResultFailure,
    ImportWorkflowResultSuccess,
    LoadWorkflowMetadataResultFailure,
    LoadWorkflowMetadataResultSuccess,
    RegisterWorkflowResultFailure,
    RegisterWorkflowResultSuccess,
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
                return_value=RegisterWorkflowResultSuccess(workflow_name="test_workflow", result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/full/path/to/workflow.py"),
            patch.object(griptape_nodes.ConfigManager(), "save_user_workflow_json") as mock_save,
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultSuccess)
            assert result.workflow_name == "test_workflow"
            mock_save.assert_called_once_with("/full/path/to/workflow.py")

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
            assert result.workflow_name == "test_workflow"

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

    def test_on_import_workflow_request_config_save_failure(self, griptape_nodes: GriptapeNodes) -> None:
        """Test import when saving to user configuration fails."""
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
                return_value=RegisterWorkflowResultSuccess(workflow_name="test_workflow", result_details="Success"),
            ),
            patch.object(WorkflowRegistry, "get_complete_file_path", return_value="/full/path/to/workflow.py"),
            patch.object(
                griptape_nodes.ConfigManager(), "save_user_workflow_json", side_effect=Exception("Config save failed")
            ),
        ):
            result = workflow_manager.on_import_workflow_request(request)

            assert isinstance(result, ImportWorkflowResultFailure)
            assert isinstance(result.result_details, ResultDetails)
            error_message = result.result_details.result_details[0].message
            assert "Failed to add workflow 'test_workflow' to user configuration" in error_message
            assert "Config save failed" in error_message
