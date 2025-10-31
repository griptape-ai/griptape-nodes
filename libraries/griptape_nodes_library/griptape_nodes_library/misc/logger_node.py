import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options


class LoggerNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.hide_parameter_by_name("exec_in")
        self.hide_parameter_by_name("exec_out")
        self.LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.default_log_level = "INFO"
        self.add_parameter(
            ParameterString(
                name="log_level",
                default_value=self.default_log_level,
                traits={Options(choices=self.LOG_LEVELS)},
                tooltip="The log level to use",
            )
        )
        self.add_parameter(
            ParameterString(
                name="log_message",
                tooltip="The log message to log",
                input_types=["str"],
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="This message will be logged to the console...",
            )
        )
        self.add_parameter(
            ParameterBool(
                name="include_node_name",
                default_value=True,
                tooltip="Whether to include a node name in the log messages",
            )
        )
        self.add_parameter(
            ParameterString(
                name="output",
                tooltip="The output log messages",
                output_type="str",
                allow_input=False,
                allow_output=True,
                allow_property=False,
                multiline=True,
                markdown=True,
            )
        )
        self.add_parameter(
            Parameter(
                type="any",
                name="passthrough",
                default_value=None,
                tooltip="[Optional] You can use this to force the logger to evaluate by connecting to downstream nodes.",
            )
        )

    def _generate_log_message(self) -> str:
        """Generate the display message for the output parameter."""
        log_message = self.get_parameter_value("log_message") or ""
        include_node_name = self.get_parameter_value("include_node_name")

        # Build the display message
        msg = ""

        if include_node_name:
            msg += f"[{self.name}] "
        # Check and see if the message has multiple lines. If so, add a newline before the message so it looks better.
        if "\n" in log_message:
            msg += "\n"
        msg += f"{log_message}"
        return msg

    def _add_log_level_to_message(self, log_level: str, log_message: str) -> str:
        """Add the log level to the message with markdown formatting.

        Uses markdown code block for monospace display and proper alignment.

        Examples:
        ```
        INFO     [Node Name] This is a simple log message
        ERROR    [Node Name] This is an error log message
        WARNING  [Node Name]
                 This is a multiline
                 warning log message
        ```
        """
        # Pad log level to 8 characters for alignment (longest is CRITICAL)
        padded_level = log_level.ljust(8)

        # For multiline messages, indent continuation lines to align with first line
        if "\n" in log_message:
            lines = log_message.split("\n")
            indent = " " * 9  # Match the length of "LEVEL    "
            formatted_lines = [lines[0]] + [indent + line for line in lines[1:]]
            log_message = "\n".join(formatted_lines)

        # Wrap in markdown code block for monospace font and proper alignment
        return f"```\n{padded_level} {log_message}\n```"

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name not in ["output"]:
            log_message = self._generate_log_message()
            simulated_log_message = self._add_log_level_to_message(self.get_parameter_value("log_level"), log_message)
            GriptapeNodes.handle_request(
                SetParameterValueRequest(parameter_name="output", value=simulated_log_message, node_name=self.name)
            )
            self.publish_update_to_parameter("output", simulated_log_message)
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        log_level = self.get_parameter_value("log_level")

        # Note: An empty message is fine because users might want to just plop in a blank message, log the node, or timestamp.
        log_message = self._generate_log_message()

        # Display the log message in the output parameter
        simulated_log_message = self._add_log_level_to_message(log_level, log_message)
        self.parameter_output_values["output"] = simulated_log_message

        # Log the message using ResultsDetails which uses the "griptape_nodes" logger by default
        ResultDetails(message=log_message, level=getattr(logging, log_level, logging.INFO))
