import ast
import json
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import logger


class TextToList(SuccessFailureNode):
    """Convert a text string into a list.

    This node intelligently parses text input and converts it to a list format.
    It supports multiple input formats and provides robust parsing with fallback options.

    Key Features:
    - Supports JSON-formatted lists (double quotes): '["one", "two", "three"]'
    - Supports Python literal lists (single quotes): "['one', 'two', 'three']"
    - Falls back to space-separated parsing: "one two three"
    - Handles edge cases and provides detailed success/failure feedback
    - Maintains data integrity with proper type validation

    Use Cases:
    - Parsing user input from forms or APIs
    - Converting configuration strings to lists
    - Processing CSV-like data
    - Handling dynamic list inputs from various sources

    Examples:
    - JSON: '["apple", "banana", "cherry"]' → ['apple', 'banana', 'cherry']
    - Python: "['red', 'green', 'blue']" → ['red', 'green', 'blue']
    - Space-separated: "hello world test" → ['hello', 'world', 'test']
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        """Initialize the TextToList node with input/output parameters and status tracking.

        This method sets up the node's parameters for text input and list output,
        along with comprehensive status tracking for professional user feedback.
        """
        super().__init__(name, metadata)

        # Input parameter for the text string to be converted
        # Supports multiple formats: JSON, Python literals, and space-separated
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                tooltip='Text string to convert to a list. Example: "["one", "two", "three"]"',
            )
        )

        # Output parameter for the converted list
        # This contains the parsed list result from the input text
        self.add_parameter(
            Parameter(
                name="list",
                output_type="list",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=[],
                tooltip="List of dictionary values",
                ui_options={"hide_property": True},
            )
        )

        # Add status parameters for success/failure feedback
        # These provide detailed information about the parsing process and results
        self._create_status_parameters(
            result_details_tooltip="Details about the text-to-list conversion result",
            result_details_placeholder="Details on the text parsing will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def _convert_text_to_list(self) -> None:
        """Convert the input text to a list and set the output.

        This method implements intelligent text parsing with multiple fallback strategies:
        1. JSON parsing for double-quoted lists: '["item1", "item2"]'
        2. Python literal evaluation for single-quoted lists: "['item1', 'item2']"
        3. Space-separated parsing as final fallback: "item1 item2 item3"

        The method ensures type safety and handles edge cases gracefully.
        """
        # Get the input text string
        input_text = self.get_parameter_value("text")

        # Ensure it's actually a text string to prevent type errors
        if not isinstance(input_text, str):
            input_text = ""

        # Convert the text string to a list using intelligent parsing
        # Try different parsing methods in order of preference
        value_list = []

        # First try JSON parsing (for double-quoted lists like '["one", "two"]')
        try:
            value_list = json.loads(input_text)
            if not isinstance(value_list, list):
                value_list = [str(value_list)]
        except (json.JSONDecodeError, ValueError):
            # Try Python literal evaluation (for single-quoted lists like "['one', 'two']")
            try:
                value_list = ast.literal_eval(input_text)
                if not isinstance(value_list, list):
                    value_list = [str(value_list)]
            except (ValueError, SyntaxError):
                # Fallback to space-separated parsing (for simple cases)
                value_list = input_text.split(" ")

        # Set output values in both the output dictionary and parameter
        self.parameter_output_values["list"] = value_list
        self.set_parameter_value("list", value_list)

    def _get_success_message(self) -> str:
        """Generate success message with list details."""
        try:
            result_list = self.get_parameter_value("list")
            if result_list and isinstance(result_list, list):
                item_count = len(result_list)
                non_empty_items = sum(1 for item in result_list if item and str(item).strip())
                return f"Successfully converted text to list with {item_count} items ({non_empty_items} non-empty)"
        except Exception as e:
            logger.warning(f"{self.name}: Error getting list: {e}")
        return "Successfully converted text to list"

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["list"] = []

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "text":
            self._convert_text_to_list()

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by converting text to list.

        This is the main execution method that:
        1. Resets the execution state and sets failure defaults
        2. Attempts to convert the input text to a list using intelligent parsing
        3. Handles any errors that occur during the conversion process
        4. Sets success status with detailed result information

        The method follows the SuccessFailureNode pattern with comprehensive error handling
        and status reporting for a professional user experience.
        """
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        logger.debug(f"{self.name}: Called for node")

        # FAILURE CASES FIRST - Attempt to convert text to list
        try:
            self._convert_text_to_list()
        except Exception as e:
            error_details = f"Failed to convert text to list: {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            self._handle_failure_exception(e)
            return

        # SUCCESS PATH AT END - Set success status with detailed information
        success_details = self._get_success_message()
        self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
        logger.debug(f"{self.name}: {success_details}")
