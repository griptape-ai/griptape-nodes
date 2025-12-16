import tempfile
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode, DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class TempDirectory(DataNode):
    """Get the system temporary directory path.

    Returns the path to the temporary directory used by the operating system.
    Works cross-platform (Windows, macOS, Linux).
    """

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add output parameter for the temp directory path
        self.add_parameter(
            ParameterString(
                name="path",
                allow_input=False,
                allow_property=False,
                default_value="",
                tooltip="The system temporary directory path.",
                placeholder_text="Example: /tmp (Linux/macOS) or C:\\Users\\...\\Temp (Windows)",
            )
        )

    def _get_temp_directory(self) -> str:
        """Get the system temporary directory path.

        Returns:
            The temporary directory path as a string
        """
        temp_dir = tempfile.gettempdir()
        return temp_dir

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        return super().after_value_set(parameter, value)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        pass

    def process(self) -> None:
        """Get and set the temporary directory path."""
        temp_path = self._get_temp_directory()

        # Set the output value
        self.set_parameter_value("path", temp_path)
        self.publish_update_to_parameter("path", temp_path)
        self.parameter_output_values["path"] = temp_path
