from typing import Any

from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString


class Group(BaseNodeGroup):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.metadata["hideaddparameter"] = True
        self.metadata["showConnectionsCollapsed"] = True

        self.description = ParameterString(
            name="description",
            allow_input=False,
            allow_property=True,
            allow_output=False,
            multiline=True,
            placeholder_text="Enter your group description here...",
            markdown=True,
            is_full_width=False,
            tooltip="A helpful description for this group",
        )
        self.add_parameter(self.description)
        self.add_parameter_to_group_settings(self.description)

    def process(self) -> None:
        pass
