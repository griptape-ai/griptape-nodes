import re
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class SearchReplaceText(DataNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input text parameter
        self.add_parameter(
            ParameterString(
                name="input_text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                multiline=True,
                placeholder_text="Replace this text: wombat...",
                tooltip="The multiline text to perform search and replace on.",
            )
        )

        # Add search pattern parameter
        self.add_parameter(
            ParameterString(
                name="search_pattern",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                placeholder_text="wombat",
                tooltip="The text or pattern to search for. Can include newlines when using regex mode.",
            )
        )

        # Add replacement text parameter
        self.add_parameter(
            ParameterString(
                name="replacement_text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="",
                placeholder_text="capybara",
                tooltip="The text to replace the search pattern with.",
            )
        )

        # Create options group
        with ParameterGroup(name="Options", ui_options={"hide": True}) as options_group:
            # Add case sensitive option
            ParameterBool(
                name="case_sensitive",
                allowed_modes={ParameterMode.PROPERTY},
                default_value=True,
                tooltip="Whether the search should be case sensitive.",
            )

            # Add regex option
            ParameterBool(
                name="use_regex",
                allowed_modes={ParameterMode.PROPERTY},
                default_value=False,
                tooltip="Whether to treat the search pattern as a regular expression. When enabled, you can use patterns like \\n for newlines.",
            )

            # Add replace all option
            ParameterBool(
                name="replace_all",
                allowed_modes={ParameterMode.PROPERTY},
                default_value=True,
                tooltip="Whether to replace all occurrences or just the first one.",
            )

        self.add_node_element(options_group)

        # Add output parameter
        self.add_parameter(
            ParameterString(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                allow_input=False,
                allow_property=False,
                multiline=True,
                placeholder_text="The text after performing search and replace.",
            )
        )

    def _search_replace(self) -> str:
        """Perform search and replace using regex under the hood."""
        # Get input parameters
        input_text = self.get_parameter_value("input_text")
        search_pattern = self.get_parameter_value("search_pattern")
        replacement_text = self.get_parameter_value("replacement_text")
        options = {
            "case_sensitive": self.get_parameter_value("case_sensitive"),
            "use_regex": self.get_parameter_value("use_regex"),
            "replace_all": self.get_parameter_value("replace_all"),
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

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name != "output":
            result = self._search_replace()
            self.parameter_output_values["output"] = result
            self.set_parameter_value("output", result)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Perform the search and replace
        result = self._search_replace()

        # Set the output
        self.parameter_output_values["output"] = result
