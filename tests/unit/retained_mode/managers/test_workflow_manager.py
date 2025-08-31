from griptape_nodes.exe_types.core_types import Parameter
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
