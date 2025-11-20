import logging
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString

logger = logging.getLogger("griptape_nodes")

DEFAULT_MERGE_STRING = "\\n\\n"


class MergeTexts(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        self.default_num_inputs = 4

        for i in range(self.default_num_inputs):
            self.add_parameter(
                ParameterString(
                    name=f"input_{i + 1}",
                    allow_output=False,
                    placeholder_text=f"Input {i + 1}",
                    tooltip="Text inputs to merge together.",
                )
            )
        # Add parameter for the separator string
        self.add_parameter(
            ParameterString(
                name="merge_string",
                allow_output=False,
                placeholder_text="text separator",
                default_value=DEFAULT_MERGE_STRING,
                tooltip="The string to use as separator between inputs.",
            )
        )
        self.add_parameter(
            ParameterBool(
                name="whitespace",
                default_value=False,
                tooltip="Whether to trim whitespace from the merged text.",
                allow_output=False,
                on_label="trim",
                off_label="keep",
            )
        )

        # Add output parameter for the merged text
        self.add_parameter(
            ParameterString(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                multiline=True,
                placeholder_text="The merged text result.",
                tooltip="The merged text result.",
            )
        )

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        # Check if this is the merge_string parameter during initial setup
        if (
            param_name == "merge_string"
            and initial_setup
            and self.metadata.get("empty_merge_string_migrated") is not True
            and (value is None or value == "")
        ):
            logger.info("%s: Migrating empty merge_string to default value", self.name)
            value = DEFAULT_MERGE_STRING
            self.metadata["empty_merge_string_migrated"] = True

        # Call the parent implementation
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # If merge_string is set manually (not during initial_setup), mark migration as complete
        # This ensures user's explicit choice is preserved on future loads
        if parameter.name == "merge_string":
            self.metadata["empty_merge_string_migrated"] = True

        if parameter.name.startswith("input_") or parameter.name in ["merge_string", "whitespace"]:
            self._merge_texts()
        return super().after_value_set(parameter, value)

    def _merge_texts(self) -> None:
        # Get the whitespace trim value
        trim_whitespace = self.get_parameter_value("whitespace")

        # Get all input texts dynamically
        input_texts = []
        for i in range(1, self.default_num_inputs + 1):
            input_value = self.get_parameter_value(f"input_{i}")
            if input_value is not None:
                text = str(input_value)
                # If trim_whitespace is True, trim the text
                if trim_whitespace:
                    text = text.strip()
                # Filter out blank inputs (after trimming if trim_whitespace is True)
                if text == "":
                    continue
                input_texts.append(text)

        # Get the separator string and replace \n with actual newlines
        separator = self.get_parameter_value("merge_string") or ""
        formatted_separator = separator.replace("\\n", "\n")

        # Join all the inputs with the formatted_separator
        merged_text = formatted_separator.join(input_texts)
        # Only strip the final result if trim_whitespace is True
        if trim_whitespace:
            merged_text = merged_text.strip()

        # Set the output
        self.set_parameter_value("output", merged_text)
        self.publish_update_to_parameter("output", merged_text)
        self.parameter_output_values["output"] = merged_text

    def process(self) -> None:
        # Merge the texts
        self._merge_texts()
