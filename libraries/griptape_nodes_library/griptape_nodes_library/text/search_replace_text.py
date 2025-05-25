import re
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class SearchReplaceText(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input text parameter
        self.add_parameter(
            Parameter(
                name="input_text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                input_types=["str"],
                ui_options={"multiline": True},
                tooltip="The multiline text to perform search and replace on.",
            )
        )

        # Add search pattern parameter
        self.add_parameter(
            Parameter(
                name="search_pattern",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                input_types=["str"],
                tooltip="The text or pattern to search for. Can include newlines when using regex mode.",
            )
        )

        # Add replacement text parameter
        self.add_parameter(
            Parameter(
                name="replacement_text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                input_types=["str"],
                tooltip="The multiline text to replace the search pattern with.",
            )
        )

        # Create options group
        with ParameterGroup(name="Options", ui_options={"hide": True}) as options_group:
            # Add case sensitive option
            Parameter(
                name="case_sensitive",
                allowed_modes={ParameterMode.PROPERTY},
                type="bool",
                default_value=True,
                tooltip="Whether the search should be case sensitive.",
            )

            # Add regex option
            Parameter(
                name="use_regex",
                allowed_modes={ParameterMode.PROPERTY},
                type="bool",
                default_value=False,
                tooltip="Whether to treat the search pattern as a regular expression. When enabled, you can use patterns like \\n for newlines.",
            )

            # Add replace all option
            Parameter(
                name="replace_all",
                allowed_modes={ParameterMode.PROPERTY},
                type="bool",
                default_value=True,
                tooltip="Whether to replace all occurrences or just the first one.",
            )

        self.add_node_element(options_group)

        # Add output parameter
        self.add_parameter(
            Parameter(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                ui_options={"multiline": True},
                default_value="",
                tooltip="The multiline text after performing search and replace.",
            )
        )

    def _search_replace(self) -> str:
        """Perform search and replace using regex under the hood."""
        # Get input parameters
        input_text = self.parameter_values.get("input_text", "")
        search_pattern = self.parameter_values.get("search_pattern", "")
        replacement_text = self.parameter_values.get("replacement_text", "")
        options = {
            "case_sensitive": self.parameter_values.get("case_sensitive", True),
            "use_regex": self.parameter_values.get("use_regex", False),
            "replace_all": self.parameter_values.get("replace_all", True),
        }

        if not input_text or not search_pattern:
            return input_text

        try:
            # If not using regex, escape the search pattern
            pattern = search_pattern if options["use_regex"] else re.escape(search_pattern)

            # Set up regex flags
            flags = 0 if options["case_sensitive"] else re.IGNORECASE

            # Perform the replacement
            if options["replace_all"]:
                return re.sub(pattern, replacement_text, input_text, flags=flags)
            return re.sub(pattern, replacement_text, input_text, count=1, flags=flags)

        except Exception:
            # If there's an error (e.g., invalid regex), return the original text
            return input_text

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name != "output":
            result = self._search_replace()
            self.parameter_output_values["output"] = result
            self.set_parameter_value("output", result)
            modified_parameters_set.add("output")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        # Perform the search and replace
        result = self._search_replace()

        # Set the output
        self.parameter_output_values["output"] = result
