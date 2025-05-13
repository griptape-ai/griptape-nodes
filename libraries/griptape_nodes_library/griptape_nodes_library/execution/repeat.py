import time
from typing import Any, cast

from griptape_nodes.exe_types.core_types import (
    ControlParameter,
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode, NodeResolutionState
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class Repeat(BaseNode):
    index: int
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        # Set the sub_flow if it exists later
        self.repeat_parameter = ControlParameterOutput(
                name="repeat",
                tooltip="Continue iteration",
            )
        self.repeat_parameter.ui_options = {"display_name":"Repeat"}
        self.add_parameter(
            self.repeat_parameter
        )
        # This is the parameter that finally continues the flow.
        self.continue_parameter = ControlParameterOutput(
            name="Continue_On",
            tooltip="Continue Flow"
        )
        self.continue_parameter.ui_options={"display_name":"Continue"}
        self.add_parameter(self.continue_parameter)

        self.start_in = ControlParameterInput(
            name="StartFlow",
            tooltip="Continue Flow"
        )
        self.add_parameter(ControlParameterInput(
            name="exec_in",
            tooltip="Continue Flow"
        ))
        self.start_in.ui_options={"display_name":"StartFlow"}
        self.add_parameter(self.start_in)
        # state for how many times it should be looped.
        self.add_parameter(
            ParameterList(
                name="Prompts",
                tooltip="",
                type="str",
                allowed_modes={ParameterMode.PROPERTY}
            )
        )
        self.add_parameter(
            Parameter(
                name="Output_Parameter",
                tooltip="",
                type="str",
                allowed_modes={ParameterMode.OUTPUT}
            )
        )
        self.index = 0

    def process(self) -> None:
        # Gets the list of prompts to iterate on!
        value_list = self.get_parameter_value("Prompts")
        try:
            value = value_list[self.index]
            self.parameter_output_values["Output_Parameter"] = value
        except Exception:
            pass
        self.index = self.index + 1


    # Define get_next_control_output to allow for a loop of connections.
    def get_next_control_output(self) -> Parameter | None:
        while self.index < len(self.get_parameter_value("Prompts")):
            # Return parameter that links back to itself.
            self.state = NodeResolutionState.RESOLVING
            #self.make_node_unresolved({NodeResolutionState.RESOLVING, NodeResolutionState.RESOLVED})
            return self.repeat_parameter
        # Continue on in the main flow
        # If it's gone through everything, no more loops needed
        # Reset the index.
        self.index = 0
        return self.continue_parameter


