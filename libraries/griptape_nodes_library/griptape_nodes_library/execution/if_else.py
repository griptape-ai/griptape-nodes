from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterGroup,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode


class IfElse(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Control flow
        self.add_parameter(
            ControlParameterInput(
                tooltip="If-Else Control Input",
                name="exec_in",
            )
        )

        then_param = ControlParameterOutput(
            tooltip="If-else connection to go down if condition is met.",
            name="Then",
        )
        then_param.ui_options = {"display_name": "Then"}
        self.add_parameter(then_param)

        else_param = ControlParameterOutput(
            tooltip="If-else connection to go down if condition is not met.",
            name="Else",
        )
        else_param.ui_options = {"display_name": "Else"}
        self.add_parameter(else_param)

        # Evaluation parameter
        self.evaluate = Parameter(
            name="evaluate",
            tooltip="Evaluates where to go",
            input_types=["bool", "int", "str"],
            output_type="bool",
            type="bool",
            default_value=False,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )

        self.add_parameter(self.evaluate)

        # Data flow outputs in a collapsible ParameterGroup
        with ParameterGroup(name="Data Outputs") as group:
            group.ui_options = {"collapsed": True}
            self.output_if_true = Parameter(
                name="output_if_true",
                tooltip="Data to output when condition is true",
                input_types=["any"],
                type="any",
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
            )

            self.output_if_false = Parameter(
                name="output_if_false",
                tooltip="Data to output when condition is false",
                input_types=["any"],
                type="any",
                allowed_modes={ParameterMode.INPUT},
                default_value=None,
            )

            self.output = Parameter(
                name="output",
                tooltip="Selected output based on condition evaluation",
                output_type=ParameterTypeBuiltin.ALL.value,
                type=ParameterTypeBuiltin.ALL.value,
                allowed_modes={ParameterMode.OUTPUT},
                default_value=None,
            )

        self.add_node_element(group)

        """
        SOPHISTICATED TYPE MANAGEMENT SYSTEM - READ THIS OR SUFFER

        This IfElse node handles complex type negotiations between:
        1. Multiple input parameters (output_if_true, output_if_false)
        2. One output parameter (output)
        3. Target nodes that may accept multiple types

        === ALL POSSIBLE SCENARIOS ===

        SCENARIO 1: Fresh node, no connections
        State: _possibility_space=[], _locked_type=None, no connections
        Result: All params accept "any", output is "ALL"

        SCENARIO 2: Connect output to single-type target (e.g., accepts only "string")
        Flow: output → target(input_types=["string"])
        State: _possibility_space=["string"], _locked_type=None, output connected
        Result: Inputs accept ["string"], output stays "ALL" (flexible until input locks it)

        SCENARIO 3: Connect output to multi-type target (e.g., accepts "string" OR "int")
        Flow: output → target(input_types=["string", "int"])
        State: _possibility_space=["string", "int"], _locked_type=None, output connected
        Result: Inputs accept ["string", "int"], output stays "ALL"

        SCENARIO 4: Input connection locks to specific type (building on scenario 2/3)
        Flow: string_source(output_type="string") → output_if_true
        State: _possibility_space=["string", "int"], _locked_type="string", input+output connected
        Result: ALL params lock to "string" type

        SCENARIO 5: Multiple compatible input connections
        Flow: string_source → output_if_true, then another_string_source → output_if_false
        State: _locked_type="string", both inputs connected
        Result: All params stay locked to "string" (compatible)

        SCENARIO 6: Attempted incompatible input connection (gracefully handled)
        Flow: int_source(output_type="int") → output_if_true (when locked to "string")
        State: _locked_type="string" (unchanged)
        Result: Connection should be prevented by type system, but tracked if somehow made

        SCENARIO 7: Remove input connection - unlock if no more inputs
        Flow: Disconnect output_if_true (from scenario 4, only input was output_if_true)
        State: _possibility_space=["string", "int"], _locked_type=None, output connected
        Result: Return to flexible state - inputs accept ["string", "int"], output "ALL"

        SCENARIO 8: Remove input connection - stay locked if other inputs remain
        Flow: Disconnect output_if_true (from scenario 5, output_if_false still connected)
        State: _locked_type="string" (unchanged), one input still connected
        Result: All params stay locked to "string"

        SCENARIO 9: Remove output connection - clear possibility space
        Flow: Disconnect output (from any scenario with output connected)
        State: _possibility_space=[], _output_connected=False
        Result: If no inputs connected → reset to default. If inputs connected → stay locked.

        SCENARIO 10: Inputs first, then output (reverse order)
        Flow: string_source → output_if_true, THEN output → multi_type_target
        State: _locked_type="string", then _possibility_space=["string", "int"]
        Result: Already locked to "string", possibility space ignored (lock wins)

        SCENARIO 11: Complete disconnection
        Flow: Remove all connections from any scenario
        State: _possibility_space=[], _locked_type=None, no connections
        Result: Reset to default - all "any"/"ALL"

        SCENARIO 12: Complex reconnection
        Flow: Any scenario → disconnect all → reconnect in different order
        Result: Behaves as if fresh node, follows same rules

        === TYPE PRIORITY RULES ===
        1. LOCKED TYPE WINS: If _locked_type exists, all params use that type
        2. POSSIBILITY SPACE: If no lock but _possibility_space exists, inputs accept those types
        3. DEFAULT FALLBACK: If neither exists, all params accept "any"/"ALL"

        === STATE TRANSITIONS ===
        DEFAULT → POSSIBILITY_SPACE (output connection made)
        DEFAULT → LOCKED (input connection made)
        POSSIBILITY_SPACE → LOCKED (input connection made)
        LOCKED → POSSIBILITY_SPACE (all inputs removed, output remains)
        LOCKED → DEFAULT (all connections removed)
        POSSIBILITY_SPACE → DEFAULT (output connection removed)
        """

        # Sophisticated connection tracking for type management
        self._possibility_space: list[str] = []  # Types acceptable to output target (from outgoing connections)
        self._locked_type: str | None = None  # Specific type locked by first input connection
        self._connected_inputs: set[str] = set()  # Track which inputs have connections
        self._output_connected: bool = False  # Track if output has connections

        # Compatible type groups - types that should be treated as interchangeable
        self._type_groups = {
            "ImageArtifact": ["ImageArtifact", "ImageUrlArtifact"],
            "ImageUrlArtifact": ["ImageArtifact", "ImageUrlArtifact"],
            "AudioArtifact": ["AudioArtifact", "AudioUrlArtifact"],
            "AudioUrlArtifact": ["AudioArtifact", "AudioUrlArtifact"],
            "VideoArtifact": ["VideoArtifact", "VideoUrlArtifact"],
            "VideoUrlArtifact": ["VideoArtifact", "VideoUrlArtifact"],
        }

    def _get_compatible_types(self, type_name: str) -> list[str]:
        """Get all types compatible with the given type (including itself).

        For artifact types that have URL variants (Image, Audio, Video), both forms
        are considered compatible. For other types, only the type itself is returned.
        """
        if type_name in self._type_groups:
            return self._type_groups[type_name]
        return [type_name]

    def _update_parameter_types(self) -> None:
        """Update all parameter types based on current state (locked type vs possibility space).

        VALIDATION: This method handles all scenarios correctly:
        - Scenarios 1,11: Default state → all "any"/"ALL"
        - Scenarios 4,5,8,10: Locked state → all use _locked_type
        - Scenarios 2,3,7: Possibility space → inputs flexible, output "ALL"
        """
        if self._locked_type:
            # We're locked to a specific type - use all compatible types
            # For artifact types with URL variants, this allows both forms
            compatible_types = self._get_compatible_types(self._locked_type)

            self.output_if_true.input_types = compatible_types
            self.output_if_true.type = self._locked_type

            self.output_if_false.input_types = compatible_types
            self.output_if_false.type = self._locked_type

            self.output.output_type = self._locked_type
            self.output.type = self._locked_type

        elif self._possibility_space:
            # We have a possibility space but no locked type
            # Inputs can accept any type in the possibility space
            self.output_if_true.input_types = self._possibility_space.copy()
            self.output_if_true.type = "any"  # Can accept multiple types

            self.output_if_false.input_types = self._possibility_space.copy()
            self.output_if_false.type = "any"  # Can accept multiple types

            # Output remains flexible since we don't know the specific type yet
            self.output.output_type = ParameterTypeBuiltin.ALL.value
            self.output.type = ParameterTypeBuiltin.ALL.value

        else:
            # Default state - no connections or constraints
            self.output_if_true.input_types = ["any"]
            self.output_if_true.type = "any"

            self.output_if_false.input_types = ["any"]
            self.output_if_false.type = "any"

            self.output.output_type = ParameterTypeBuiltin.ALL.value
            self.output.type = ParameterTypeBuiltin.ALL.value

    def _can_accept_input_type(self, input_type: str) -> bool:
        """Check if we can accept a new input connection of the given type."""
        if self._locked_type:
            # If locked, accept the locked type or any compatible type
            compatible_types = self._get_compatible_types(self._locked_type)
            return input_type in compatible_types
        if self._possibility_space:
            # If we have a possibility space, input must be in it
            return input_type in self._possibility_space
        # Default state - accept any type
        return True

    def _set_locked_type(self, type_to_lock: str) -> None:
        """Lock all parameters to a specific type."""
        self._locked_type = type_to_lock
        self._update_parameter_types()

    def _clear_locked_type(self) -> None:
        """Clear the locked type and restore flexibility."""
        self._locked_type = None
        self._update_parameter_types()

    def _set_possibility_space(self, possible_types: list[str]) -> None:
        """Set the possibility space for acceptable types."""
        self._possibility_space = possible_types.copy()
        if not self._locked_type:  # Only update if not locked
            self._update_parameter_types()

    def _clear_possibility_space(self) -> None:
        """Clear the possibility space."""
        self._possibility_space = []
        if not self._locked_type:  # Only update if not locked
            self._update_parameter_types()

    def check_evaluation(self) -> bool:
        value = self.get_parameter_value("evaluate")
        if isinstance(value, str):
            value_lower = value.lower().strip()
            false_values = [
                "false",
                "falsey",
                "f",
                "no",
                "n",
                "negative",
                "off",
                "zero",
                "0.0",
                "0",
                "",
                "nope",
                "nah",
                "none",
                "null",
                "nyet",
                "nein",
                "disabled",
            ]
            return value_lower not in false_values

        if isinstance(value, int):
            return bool(value)
        if isinstance(value, bool):
            return value
        msg = f"Unsupported type for evaluate: {type(value)}"
        raise TypeError(msg)

    def process(self) -> None:
        evaluation_result = self.check_evaluation()
        self.parameter_output_values["evaluate"] = evaluation_result

        # Select the appropriate output value based on evaluation
        if evaluation_result:
            selected_value = self.get_parameter_value("output_if_true")
        else:
            selected_value = self.get_parameter_value("output_if_false")

        # Set the output value
        self.parameter_output_values["output"] = selected_value

    # Override this method.
    def get_next_control_output(self) -> Parameter | None:
        if "evaluate" not in self.parameter_output_values:
            self.stop_flow = True
            return None
        if self.parameter_output_values["evaluate"]:
            return self.get_parameter_by_name("Then")
        return self.get_parameter_by_name("Else")

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle incoming connections to input parameters.

        VALIDATION: Handles scenarios 4,5,6,10 correctly:
        - Scenario 4: First input locks type ✓
        - Scenario 5: Compatible inputs stay locked ✓
        - Scenario 6: Incompatible inputs handled gracefully ✓
        - Scenario 10: Input-first order works ✓
        """
        if target_parameter.name in ["output_if_true", "output_if_false"]:
            source_type = source_parameter.output_type or source_parameter.type

            # Check if we can accept this type
            if self._can_accept_input_type(source_type):
                # If no locked type yet, this connection locks us to this type
                if not self._locked_type:
                    self._set_locked_type(source_type)

                # Track this connection
                self._connected_inputs.add(target_parameter.name)
            else:
                # This connection is not compatible - the system should prevent it
                # but we'll track it anyway to be safe
                self._connected_inputs.add(target_parameter.name)

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        """Handle outgoing connections from output parameter.

        VALIDATION: Handles scenarios 2,3,10 correctly:
        - Scenario 2: Single-type target sets possibility space ✓
        - Scenario 3: Multi-type target sets possibility space ✓
        - Scenario 10: Output-second order works (locked type wins) ✓
        """
        if source_parameter.name == "output":
            # The target parameter defines what types are acceptable
            target_input_types = target_parameter.input_types or [target_parameter.type]

            # Set the possibility space based on what the target accepts
            self._set_possibility_space(target_input_types)

            # Track this connection
            self._output_connected = True

        return super().after_outgoing_connection(source_parameter, target_node, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle removal of incoming connections.

        VALIDATION: Handles scenarios 7,8,11 correctly:
        - Scenario 7: Remove only input → unlock, restore possibility space ✓
        - Scenario 8: Remove one input, others remain → stay locked ✓
        - Scenario 11: Remove all inputs → reset to appropriate state ✓
        """
        if target_parameter.name in ["output_if_true", "output_if_false"]:
            # Remove this connection from tracking
            self._connected_inputs.discard(target_parameter.name)

            # If no more input connections exist, clear the locked type
            if not self._connected_inputs:
                self._clear_locked_type()

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        """Handle removal of outgoing connections.

        VALIDATION: Handles scenarios 9,11,12 correctly:
        - Scenario 9: Remove output → clear possibility space, maintain lock if inputs exist ✓
        - Scenario 11: Remove output as part of complete disconnection ✓
         - Scenario 12: Part of reconnection flow ✓
        """
        if source_parameter.name == "output":
            # Clear the possibility space
            self._clear_possibility_space()

            # Track this disconnection
            self._output_connected = False

        return super().after_outgoing_connection_removed(source_parameter, target_node, target_parameter)

    def initialize_spotlight(self) -> None:
        """Custom spotlight initialization - only include evaluate parameter initially.

        This prevents automatic dependency resolution of both input branches.
        We'll conditionally add the appropriate branch in advance_parameter().
        """
        evaluate_param = self.get_parameter_by_name("evaluate")
        if evaluate_param and ParameterMode.INPUT in evaluate_param.get_mode():
            self.current_spotlight_parameter = evaluate_param
            # Don't link to any other parameters yet - we'll decide conditionally

    def advance_parameter(self) -> bool:
        """Custom parameter advancement with conditional dependency resolution.

        After evaluate is resolved, add ONLY the appropriate input branch to the dependency chain.
        This prevents resolving the unused branch entirely.
        """
        if self.current_spotlight_parameter is None:
            return False

        # Special handling for the evaluate parameter - conditionally link to selected branch
        if self.current_spotlight_parameter is self.evaluate:
            try:
                # Evaluate the condition to determine which branch we need
                evaluation_result = self.check_evaluation()
            except Exception:  # (we are already logging the error in the check_evaluation)
                # If evaluation fails, don't resolve any input branches, stop processing
                self.current_spotlight_parameter = None
                return False
            else:
                # Evaluation succeeded, select the appropriate branch
                next_param = self.output_if_true if evaluation_result else self.output_if_false

                # Only add the selected parameter if it has input connections
                if ParameterMode.INPUT in next_param.get_mode():
                    # Link the selected parameter as the next in the chain
                    self.current_spotlight_parameter.next = next_param
                    next_param.prev = self.current_spotlight_parameter
                    self.current_spotlight_parameter = next_param
                    return True

        # Default advancement behavior (handles both evaluate failure and normal parameters)
        if self.current_spotlight_parameter.next is not None:
            self.current_spotlight_parameter = self.current_spotlight_parameter.next
            return True

        # No more parameters to advance to
        self.current_spotlight_parameter = None
        return False
