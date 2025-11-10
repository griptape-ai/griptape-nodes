from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class PathJoin(DataNode):
    """Join multiple path components together to create a file path."""

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add ParameterList for path components
        self.path_components_list = ParameterList(
            name="path_components",
            tooltip="Path components to join together.",
            input_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        self.add_parameter(self.path_components_list)

        # Add output parameter for the joined path
        self.add_parameter(
            ParameterString(
                name="output",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The joined path result.",
                tooltip="The joined path result using appropriate path separators.",
            )
        )

    def _join_paths(self) -> None:
        """Join path components and update output parameter."""
        # Get the list of path components from the ParameterList
        components_list = self.get_parameter_value("path_components")
        if components_list is None:
            components_list = []

        # Ensure we have a list
        if not isinstance(components_list, list):
            components_list = [components_list] if components_list is not None else []

        # Filter and process path components
        path_components = []
        for component_value in components_list:
            if component_value is not None:
                component_str = str(component_value).strip()
                # Filter out empty inputs
                if component_str == "":
                    continue
                path_components.append(component_str)

        # Join paths using pathlib.Path for proper cross-platform handling
        if path_components:
            joined_path = str(Path(*path_components))
        else:
            joined_path = ""

        # Set the output
        self.set_parameter_value("output", joined_path)
        self.publish_update_to_parameter("output", joined_path)
        self.parameter_output_values["output"] = joined_path

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "path_components":
            self._join_paths()
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Join the paths
        self._join_paths()
