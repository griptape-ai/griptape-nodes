from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameter,
    ControlParameterOutput,
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class ForEach(BaseNode):
    index: int
    sub_flow: ControlFlow | None
    flow: ControlFlow
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        # Set the sub_flow if it exists later
        self.sub_flow = None
        # This will determine how many times we loop
        self.add_parameter(
            ParameterList(
                name="for_each",
                input_types=["str"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        # This is where the output is going to be set
        self.add_parameter(
            ParameterList(
                name="output",
                tooltip = "",
                type="ImageArtifact",
                output_type="ImageArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                settable=True
            )
        )
        # This is the control parameter that loops back to the input control parameter
        self.repeat_parameter = ControlParameterOutput(
                name="repeat",
                tooltip="Continue iteration",
            )
        self.repeat_parameter.ui_options = {"display_name":"Repeat"}
        self.add_parameter(
            self.repeat_parameter
        )
        # This is the input control parameter that is going to allow an output connection
        self.special_subflow = ControlParameter(
            name="SubFlow_Connection",
            tooltip="Connect to a subflow",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT}
        )
        self.add_parameter(
            self.special_subflow
        )
        # This is the parameter that finally continues the flow.
        self.continue_parameter = ControlParameterOutput(
            name="Continue_On",
            tooltip="Continue Flow"
        )
        self.add_parameter(self.continue_parameter)
        # state for how many times it should be looped.
        self.times = 0
        # Creates a connection between the input exec_in and the repeat out.
        #TODO: ask if this works properly in the way I am intending.
        flow_name = GriptapeNodes.ContextManager().get_current_flow_name()
        flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        self.flow = flow
        self.flow.add_connection(self,self.repeat_parameter,self, self.special_subflow)

        # TODO: Change to be based on list
        self.index = 0

    def process(self) -> None:
        # Gets the list of prompts to iterate on!
        items_to_iterate = self.get_parameter_value("for_each")
        prompt = items_to_iterate[self.index]

        self.parameter_output_values["list_output"] = []


    # Define get_next_control_output to allow for a loop of connections.
    def get_next_control_output(self) -> Parameter | None:
        while self.index < len(self.get_parameter_value("for_each")):
            # Set the state to unresolved so it will run again.
            self.state = NodeResolutionState.UNRESOLVED
            if self.sub_flow:
                self.sub_flow.unresolve_whole_flow()
            # Return parameter that links back to itself.
            return self.repeat_parameter
        # Continue on in the main flow
        # If it's gone through everything, no more loops needed
        # Reset the index.
        self.index = 0
        return self.continue_parameter


