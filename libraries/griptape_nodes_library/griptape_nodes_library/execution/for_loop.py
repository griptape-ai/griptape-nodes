import time
from typing import Any, cast

from griptape_nodes.exe_types.core_types import (
    ControlParameter,
    ControlParameterOutput,
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode, NodeResolutionState
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class RepeatNode(BaseNode):
    times: int
    sub_flow: ControlFlow | None
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.sub_flow = None
        self.add_parameter(
            ParameterList(
                name="for_each",
                input_types=["str"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
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
        self.repeat_parameter = ControlParameterOutput(
                name="repeat",
                tooltip="Continue iteration",
            )
        self.repeat_parameter.ui_options = {"display_name":"Repeat"}
        self.add_parameter(
            self.repeat_parameter
        )
        self.special_subflow = ControlParameter(
            name="SubFlow_Connection",
            tooltip="Connect to a subflow",
        )
        self.add_parameter(
            self.special_subflow
        )
        self.continue_parameter = ControlParameterOutput(
            name="Continue_On",
            tooltip="Continue down flow"
        )
        self.add_parameter(self.continue_parameter)
        self.times = 0

    def process(self) -> None:
        flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
        flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        exec_in = self.get_parameter_by_name("exec_in")
        if exec_in is not None and flow is not None:
            flow.add_connection(self,self.iterate_more,self,exec_in)
        loop = self.get_parameter_value("looped_input")
        self.loop = len(loop)
        # Get the list we are going to loop over. ForEach Loop
        flow = self.get_parameter_value("flow")
        if flow is not None:
            flow = cast("ControlFlow", flow)
            self.parameter_output_values["list_output"] = []
            for prompt in loop:
                start_node_queue = flow.get_start_node_queue()
                start_node = start_node_queue.queue[0] if start_node_queue is not None and not start_node_queue.empty() else None
                if start_node is not None:
                    start_node = cast("ControlNode", start_node)
                    start_node.set_parameter_value("prompt",prompt)
                    #yield lambda: self._process(flow=flow)
                    flow.start_flow(start_node)
                    while flow.check_for_existing_running_flow():
                        time.sleep(0.1)
                    self.loop = self.loop - 1
                    end_node = flow.end_node
                    if end_node is not None:
                        self.parameter_output_values["list_output"].append(end_node.parameter_output_values["output"])


    def get_next_control_output(self) -> Parameter | None:
        while self.times > 0:
            # Set the state to unresolved so it will run again.
            self.state = NodeResolutionState.UNRESOLVED
            if self.sub_flow:
                self.sub_flow.unresolve_whole_flow()
            return self.repeat_parameter
        # Continue on in the main flow
        return self.get_parameter_by_name("exec_out")


    # def _process(self, flow:ControlFlow) -> ControlFlow:
    #     GriptapeNodes.handle_request(StartFlowRequest("SubFlow_1"))
    #         # Flow then executes. Hooray!
    #     while flow.check_for_existing_running_flow():
    #         time.sleep(0.1)
    #     end_node = flow.end_node
    #     if end_node is not None:
    #         self.parameter_output_values["list_output"].append(end_node.parameter_output_values["output"])
    #     return flow

