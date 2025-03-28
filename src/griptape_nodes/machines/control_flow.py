# Control flow machine
from __future__ import annotations

from typing import TYPE_CHECKING

from griptape.events import EventBus

from griptape_nodes.exe_types.node_types import BaseNode, NodeResolutionState
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.machines.fsm import FSM, State
from griptape_nodes.machines.node_resolution import NodeResolutionMachine
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowResolvedEvent,
    CurrentControlNodeEvent,
    SelectedControlOutputEvent,
)

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow


# This is the control flow context. Owns the Resolution Machine
class ControlFlowContext:
    flow: ControlFlow
    current_node: BaseNode
    resolution_machine: NodeResolutionMachine
    selected_output: Parameter | None
    paused: bool = False

    def __init__(self, flow: ControlFlow) -> None:
        self.resolution_machine = NodeResolutionMachine(flow)
        self.flow = flow

    def get_next_node(self, output_parameter: Parameter) -> BaseNode | None:
        node = self.flow.connections.get_connected_node(self.current_node, output_parameter)
        if node:
            node, _ = node
        return node


# GOOD!
class ResolveNodeState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        # The state machine has started, but it hasn't began to execute yet.
        context.current_node.state = NodeResolutionState.UNRESOLVED
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(payload=CurrentControlNodeEvent(node_name=context.current_node.name))
            )
        )
        # Print statement for retained mode
        print(f"Resolving {context.current_node.name}")
        if not context.paused:
            # Call the update. Otherwise wait
            return ResolveNodeState
        return None

    # This is necessary to transition to the next step.
    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:
        # If node has not already been resolved!
        if context.current_node.state != NodeResolutionState.RESOLVED:
            context.resolution_machine.resolve_node(context.current_node)

        if context.resolution_machine.is_complete():
            return NextNodeState
        return None


class NextNodeState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        # I did define this on the ControlNode.
        if context.current_node.stop_flow:
            # We're done here.
            context.current_node.stop_flow = False
            return CompleteState
        next_output = context.current_node.get_next_control_output()
        if next_output is None:
            return CompleteState
        # The parameter that will be evaluated next
        context.selected_output = next_output
        next_node = context.get_next_node(context.selected_output)
        if next_node is None:
            # If no node attached
            return CompleteState
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=SelectedControlOutputEvent(
                        node_name=context.current_node.name,
                        selected_output_parameter_name=next_output.name,
                    )
                )
            )
        )
        context.current_node = next_node
        context.selected_output = None
        if not context.paused:
            return ResolveNodeState
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return ResolveNodeState


class CompleteState(State):
    @staticmethod
    def on_enter(context: ControlFlowContext) -> type[State] | None:
        EventBus.publish_event(
            ExecutionGriptapeNodeEvent(
                wrapped_event=ExecutionEvent(
                    payload=ControlFlowResolvedEvent(
                        end_node_name=context.current_node.name,
                        parameter_output_values=TypeValidator.safe_serialize(
                            context.current_node.parameter_output_values
                        ),
                    )
                )
            )
        )
        print("Flow is complete.")
        return None

    @staticmethod
    def on_update(context: ControlFlowContext) -> type[State] | None:  # noqa: ARG004
        return None


# MACHINE TIME!!!
class ControlFlowMachine(FSM[ControlFlowContext]):
    def __init__(self, flow: ControlFlow) -> None:
        context = ControlFlowContext(flow)
        super().__init__(context)

    def start_flow(self, start_node: BaseNode, debug_mode: bool = False) -> None:  # noqa: FBT001, FBT002
        self._context.current_node = start_node
        # Set up to debug
        self._context.paused = debug_mode
        self.start(ResolveNodeState)  # Begins the flow

    def update(self) -> None:
        if self._current_state is None:
            msg = "Cannot step machine that has not started"
            raise RuntimeError(msg)
        super().update()

    def change_debug_mode(self, debug_mode: bool) -> None:  # noqa: FBT001
        self._context.paused = debug_mode
        self._context.resolution_machine.change_debug_mode(debug_mode)

    def granular_step(self) -> None:
        self._context.resolution_machine.change_debug_mode(True)
        if self._context.resolution_machine.is_complete() or (not self._context.resolution_machine.is_started()):
            self.update()
        else:
            self._context.resolution_machine.update()

    def node_step(self) -> None:
        resolution_machine = self._context.resolution_machine
        resolution_machine.change_debug_mode(False)
        if resolution_machine.is_complete() or (not resolution_machine.is_started()):
            self.update()
        else:
            resolution_machine.update()
