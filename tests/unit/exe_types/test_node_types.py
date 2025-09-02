from unittest.mock import MagicMock

import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options

from .mocks import MockNode


class TestBaseNode:
    """Test suite for BaseNode class, particularly the _update_option_choices method."""

    @pytest.fixture
    def mock_node(self) -> MockNode:
        """Create a mock node with a parameter that has Options trait."""
        node = MockNode(name="test_node")
        # Create a parameter with Options trait
        param = Parameter(
            name="model",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="Model selection",
        )
        # Add Options trait
        options_trait = Options(choices=["model1", "model2"])
        param.add_child(options_trait)
        # Simulate the parameter having UI options
        param._ui_options = {"simple_dropdown": ["model1", "model2"]}
        # Add parameter to node's root_ui_element so it can be found by get_parameter_by_name
        node.root_ui_element.add_child(param)
        return node

    def test_update_option_choices_updates_ui_options(self, mock_node: MockNode) -> None:
        """Test that _update_option_choices updates the UI options when choices change."""
        new_choices = ["model3", "model4", "model5"]
        default_model = "model4"

        # Mock the set_parameter_value method
        mock_node.set_parameter_value = MagicMock()

        # Call _update_option_choices
        mock_node._update_option_choices("model", new_choices, default_model)

        # Get the parameter
        param = mock_node.get_parameter_by_name("model")
        assert param is not None

        # Check that Options trait was updated
        options_traits = param.find_elements_by_type(Options)
        assert len(options_traits) == 1
        assert options_traits[0].choices == new_choices

        # Check that UI options were updated with new simple_dropdown choices
        assert param._ui_options["simple_dropdown"] == new_choices

        # Check that default value was set
        assert param.default_value == default_model

        # Check that set_parameter_value was called with the default
        mock_node.set_parameter_value.assert_called_once_with("model", default_model)

    def test_update_option_choices_without_ui_options(self, mock_node: MockNode) -> None:
        """Test that _update_option_choices works when parameter has no _ui_options."""
        # Remove the _ui_options attribute
        param = mock_node.get_parameter_by_name("model")
        assert param is not None
        delattr(param, "_ui_options")

        new_choices = ["model3", "model4"]
        default_model = "model3"

        # Mock the set_parameter_value method
        mock_node.set_parameter_value = MagicMock()

        # Should not raise an error
        mock_node._update_option_choices("model", new_choices, default_model)

        # Check that Options trait was still updated
        options_traits = param.find_elements_by_type(Options)
        assert len(options_traits) == 1
        assert options_traits[0].choices == new_choices

    def test_update_option_choices_invalid_default(self, mock_node: MockNode) -> None:
        """Test that _update_option_choices raises error when default is not in choices."""
        new_choices = ["model3", "model4"]
        invalid_default = "model5"  # Not in choices

        # Should raise ValueError
        with pytest.raises(ValueError, match="Default model 'model5' is not in the provided choices"):
            mock_node._update_option_choices("model", new_choices, invalid_default)

    def test_update_option_choices_no_options_trait(self, mock_node: MockNode) -> None:
        """Test that _update_option_choices raises error when parameter has no Options trait."""
        # Create a parameter without Options trait
        param_without_options = Parameter(
            name="param_no_options",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="Parameter without options",
        )
        mock_node.root_ui_element.add_child(param_without_options)

        new_choices = ["choice1", "choice2"]
        default_choice = "choice1"

        # Should raise ValueError
        with pytest.raises(ValueError, match="No Options trait found for parameter 'param_no_options'"):
            mock_node._update_option_choices("param_no_options", new_choices, default_choice)

    def test_update_option_choices_nonexistent_parameter(self, mock_node: MockNode) -> None:
        """Test that _update_option_choices raises error for nonexistent parameter."""
        new_choices = ["choice1", "choice2"]
        default_choice = "choice1"

        # Should raise ValueError for nonexistent parameter
        with pytest.raises(ValueError, match="Parameter 'nonexistent_param' not found for updating model choices"):
            mock_node._update_option_choices("nonexistent_param", new_choices, default_choice)

    def test_update_option_choices_with_alter_element_event(self, mock_node: MockNode) -> None:
        """Test that updating options preserves UI options for AlterElementEvent emission."""
        new_choices = ["model3", "model4", "model5"]
        default_model = "model4"

        # Get the parameter before update
        param = mock_node.get_parameter_by_name("model")
        assert param is not None

        # Verify initial state
        assert hasattr(param, "_ui_options")
        assert param._ui_options["simple_dropdown"] == ["model1", "model2"]

        # Mock set_parameter_value to avoid execution errors
        mock_node.set_parameter_value = MagicMock()

        # Call _update_option_choices
        mock_node._update_option_choices("model", new_choices, default_model)

        # Verify that ui_options were updated correctly
        assert param._ui_options["simple_dropdown"] == new_choices

        # Verify Options trait was updated
        options_traits = param.find_elements_by_type(Options)
        assert len(options_traits) == 1
        assert options_traits[0].choices == new_choices

        # This ensures that when AlterElementEvent is emitted (via set_parameter_value),
        # the UI will receive the updated choices through the parameter's ui_options
