from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options


class TestDynamicGroup(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Free text entry parameter
        self.add_parameter(
            Parameter(
                name="selector",
                tooltip="Select a thing",
                type="str",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=["text", "image"])},
            )
        )
        with ParameterGroup(name="group1") as group:
            Parameter(
                name="free_text",
                tooltip="Enter any text",
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                ui_options={"hide": True},
            )
        self.add_node_element(group)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "selector":
            if value == "text":
                param = self.get_parameter_by_name("free_text")
                if param: param.type = "str"
            else:
                param = self.get_parameter_by_name("free_text")
                if param: param.type = "ImageArtifact"
            modified_parameters_set.add("free_text")
        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        pass
