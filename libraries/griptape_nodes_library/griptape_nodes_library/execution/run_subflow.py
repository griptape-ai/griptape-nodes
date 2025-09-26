import json
import logging
from dataclasses import dataclass
from typing import Any, NamedTuple

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMessage,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    CreateFlowResultSuccess,
    DeleteFlowRequest,
)

# WorkflowMetadata will be imported when needed for proper typing
from griptape_nodes.retained_mode.events.node_events import (
    GetFlowForNodeRequest,
    GetFlowForNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultSuccess,
    RemoveParameterFromNodeRequest,
    RemoveParameterFromNodeResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    ListAllWorkflowsRequest,
    ListAllWorkflowsResultSuccess,
    RunWorkflowWithCurrentStateRequest,
    RunWorkflowWithCurrentStateResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger(__name__)


class WorkflowProblem(NamedTuple):
    """Represents a problem preventing a workflow from being runnable."""

    issue: str  # What's wrong
    remedy: str  # What the user can do to fix it


@dataclass
class WorkflowInfo:
    """Information about a workflow and its runnability status."""

    name: str
    metadata: Any  # Mock WorkflowMetadata object created from dict
    problems: list[WorkflowProblem]

    @property
    def is_runnable(self) -> bool:
        """True if workflow has no problems preventing execution."""
        return len(self.problems) == 0


class ParameterCreationSpec(NamedTuple):
    """Specification for creating a dynamic parameter."""

    name: str
    param_type: str
    input_types: list[str] | None
    output_type: str | None
    tooltip: str
    default_value: Any
    ui_options: dict
    is_input: bool  # True for input parameters, False for output parameters


class RunSubflow(SuccessFailureNode):
    """Node that executes a registered workflow as a subflow.

    Dynamically populates input and output parameters based on the selected
    workflow's WorkflowShape, which describes the Start and End nodes.
    """

    # Default selection option constant
    _DEFAULT_SELECTION_TEXT = "Select a workflow to run"

    # Parameter name prefixes for tracking dynamic parameters
    _INPUT_PARAMETER_PREFIX = "input_"
    _OUTPUT_PARAMETER_PREFIX = "output_"

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)

        # Track dynamic parameters using Python lists (not string manipulation)
        self._dynamic_input_parameters: list[Parameter] = []
        self._dynamic_output_parameters: list[Parameter] = []

        # Discover available workflows and assess fitness
        self._available_workflows = self._discover_workflows()

        # Create workflow selector dropdown
        self._create_workflow_selector()

        # Create fitness info message
        self.fitness_message = ParameterMessage(
            variant="info",
            value="Select a workflow to see execution details.",
            name="fitness_info",
        )
        self.add_node_element(self.fitness_message)

        # Create status parameters using SuccessFailureNode helper
        self._create_status_parameters(
            result_details_tooltip="Details about the subflow execution result",
            result_details_placeholder="Details on the subflow execution will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def _discover_workflows(self) -> dict[str, WorkflowInfo]:
        """Discover available workflows and assess their fitness for execution.

        Returns:
            Dictionary mapping workflow names to WorkflowInfo objects

        Raises:
            RuntimeError: If workflow discovery fails
        """
        workflows = {}

        # Use the proper event system to list workflows
        list_request = ListAllWorkflowsRequest()
        list_result = GriptapeNodes.handle_request(list_request)

        if not isinstance(list_result, ListAllWorkflowsResultSuccess):
            msg = f"Failed to list workflows: {list_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Extract workflows from the successful result
        all_workflows = list_result.workflows

        for workflow_name, workflow_metadata_dict in all_workflows.items():
            try:
                # Assess workflow fitness
                problems = self._assess_workflow_fitness(workflow_metadata_dict)

                # Create a mock WorkflowMetadata object from the dictionary
                # This is a temporary approach until the event system returns proper objects
                mock_metadata = type("WorkflowMetadata", (), workflow_metadata_dict)()

                workflows[workflow_name] = WorkflowInfo(
                    name=workflow_name,
                    metadata=mock_metadata,
                    problems=problems,
                )

            except Exception as e:
                logger.error("Failed to process workflow '%s': %s", workflow_name, e)
                # Create a workflow with a processing error
                problems = [
                    WorkflowProblem(
                        issue=f"Failed to process workflow metadata: {e}",
                        remedy="Check workflow metadata format and try reloading workflows",
                    )
                ]
                mock_metadata = type("WorkflowMetadata", (), {"name": workflow_name})()
                workflows[workflow_name] = WorkflowInfo(
                    name=workflow_name,
                    metadata=mock_metadata,
                    problems=problems,
                )

            for workflow_name, workflow_metadata_dict in all_workflows.items():
                try:
                    # Assess workflow fitness
                    problems = self._assess_workflow_fitness(workflow_metadata_dict)

                    # Create a mock WorkflowMetadata object from the dictionary
                    # This is a temporary approach until the event system returns proper objects
                    mock_metadata = type("WorkflowMetadata", (), workflow_metadata_dict)()

                    workflows[workflow_name] = WorkflowInfo(
                        name=workflow_name,
                        metadata=mock_metadata,
                        problems=problems,
                    )

                except Exception as e:
                    logger.error("Failed to process workflow '%s': %s", workflow_name, e)
                    # Create a workflow with a processing error
                    problems = [
                        WorkflowProblem(
                            issue=f"Failed to process workflow metadata: {e}",
                            remedy="Check workflow metadata format and try reloading workflows",
                        )
                    ]
                    mock_metadata = type("WorkflowMetadata", (), {"name": workflow_name})()
                    workflows[workflow_name] = WorkflowInfo(
                        name=workflow_name,
                        metadata=mock_metadata,
                        problems=problems,
                    )

        return workflows

    def _assess_workflow_fitness(self, workflow_metadata_dict: dict) -> list[WorkflowProblem]:
        """Assess workflow fitness and return list of problems preventing execution.

        Args:
            workflow_metadata_dict: The workflow metadata dictionary to assess

        Returns:
            List of WorkflowProblem objects, empty if workflow is runnable
        """
        problems = []

        # Check for workflow_shape presence
        if not workflow_metadata_dict.get("workflow_shape"):
            problems.append(
                WorkflowProblem(
                    issue="Missing Start/End nodes",
                    remedy="Add a Start node and End node to make this workflow runnable",
                )
            )

        # Future fitness criteria can be added here:
        # - Check for circular dependencies
        # - Validate required libraries are available
        # - Check for missing node types
        # - Validate parameter compatibility

        return problems

    def _create_workflow_selector(self) -> None:
        """Create the workflow selector dropdown parameter."""
        # Build options list: runnable workflows first, then non-runnable with asterisk
        workflow_options = [self._DEFAULT_SELECTION_TEXT]

        # Add runnable workflows first
        for name, info in self._available_workflows.items():
            if info.is_runnable:
                workflow_options.append(name)

        # Add non-runnable workflows with asterisk
        for name, info in self._available_workflows.items():
            if not info.is_runnable:
                workflow_options.append(f"{name} *")

        self.workflow_selector = Parameter(
            name="workflow",
            tooltip="Select the workflow to execute as a subflow",
            type="str",
            default_value=self._DEFAULT_SELECTION_TEXT,
            traits={Options(choices=workflow_options)},
        )
        self.add_parameter(self.workflow_selector)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to handle workflow selector parameter changes."""
        # Store old value before updating if this is the workflow selector
        old_value = None
        if param_name == self.workflow_selector.name:
            old_value = self.get_parameter_value(self.workflow_selector.name)

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        if param_name == self.workflow_selector.name:
            self._update_parameters_for_workflow(value, old_value)

    def _update_parameters_for_workflow(self, selected_workflow: str, _old_workflow: str | None = None) -> None:
        """Update node parameters based on selected workflow.

        Args:
            selected_workflow: The newly selected workflow name
            old_workflow: The previously selected workflow name (if any)
        """
        # Clean up the workflow name (remove asterisk if present)
        clean_workflow_name = selected_workflow.rstrip(" *")

        # Handle default selection
        if clean_workflow_name == self._DEFAULT_SELECTION_TEXT:
            self._clear_dynamic_parameters()
            self.fitness_message.variant = "info"
            self.fitness_message.value = "Select a workflow to see execution details."
            return

        # Check if workflow exists
        if clean_workflow_name not in self._available_workflows:
            self._clear_dynamic_parameters()
            self.fitness_message.variant = "error"
            self.fitness_message.value = f"Unknown workflow: {clean_workflow_name}"
            return

        workflow_info = self._available_workflows[clean_workflow_name]

        # Update fitness message based on workflow status
        if not workflow_info.is_runnable:
            self._clear_dynamic_parameters()
            self.fitness_message.variant = "error"
            issues = "\n".join([f"• {problem.issue}: {problem.remedy}" for problem in workflow_info.problems])
            self.fitness_message.value = f"Workflow '{clean_workflow_name}' is not runnable:\n\n{issues}"
            return

        # Workflow is runnable - update fitness message and create parameters
        self.fitness_message.variant = "success"
        self.fitness_message.value = f"Workflow '{clean_workflow_name}' is ready for execution."

        # Create dynamic parameters based on WorkflowShape
        self._create_dynamic_parameters(workflow_info.metadata)

    def _create_dynamic_parameters(self, workflow_metadata: Any) -> None:
        """Create dynamic input and output parameters based on WorkflowShape.

        Args:
            workflow_metadata: The workflow metadata object containing workflow_shape

        Raises:
            RuntimeError: If workflow_shape is missing or invalid
        """
        # Clear existing dynamic parameters first
        self._clear_dynamic_parameters()

        # Get workflow_shape from metadata
        try:
            workflow_shape_json = getattr(workflow_metadata, "workflow_shape", None)
            if not workflow_shape_json:
                msg = "Workflow metadata is missing workflow_shape - this should have been caught in fitness assessment"
                raise RuntimeError(msg)
        except AttributeError as e:
            msg = f"Invalid workflow metadata object: {e}"
            raise RuntimeError(msg) from e

        # Parse the WorkflowShape JSON
        try:
            workflow_shape = json.loads(workflow_shape_json)
        except json.JSONDecodeError as e:
            msg = f"Invalid workflow_shape JSON format: {e}"
            raise RuntimeError(msg) from e

        # Create parameters from workflow shape
        try:
            inputs_shape = workflow_shape.get("inputs", {})
            outputs_shape = workflow_shape.get("outputs", {})

            # Create input and output parameters
            self._create_parameters_from_shape(inputs_shape, is_input=True)
            self._create_parameters_from_shape(outputs_shape, is_input=False)

        except Exception as e:
            # Clean up any partially created parameters on failure
            self._clear_dynamic_parameters()
            msg = f"Failed to create dynamic parameters: {e}"
            raise RuntimeError(msg) from e

    def _create_parameters_from_shape(self, shape: dict, *, is_input: bool) -> None:
        """Create parameters from workflow_shape section (unified method for inputs/outputs).

        Args:
            shape: The inputs or outputs section of the workflow_shape
            is_input: True for input parameters, False for output parameters

        Raises:
            RuntimeError: If parameter creation fails
        """
        # shape format: {node_name: {param_name: param_dict}}
        parameter_specs = []

        # Extract all parameter specifications first
        for node_params in shape.values():
            for param_name, param_dict in node_params.items():
                try:
                    spec = self._build_parameter_spec(param_name, param_dict, is_input=is_input)
                    parameter_specs.append(spec)
                except Exception as e:
                    msg = f"Failed to build parameter spec for '{param_name}': {e}"
                    raise RuntimeError(msg) from e

        # Create all parameters
        for spec in parameter_specs:
            try:
                self._create_parameter_from_spec(spec)
            except Exception as e:
                msg = f"Failed to create parameter '{spec.name}': {e}"
                raise RuntimeError(msg) from e

    def _build_parameter_spec(self, param_name: str, param_dict: dict, *, is_input: bool) -> ParameterCreationSpec:
        """Build a parameter creation specification from workflow shape data.

        Args:
            param_name: Name of the parameter
            param_dict: Parameter dictionary from workflow_shape
            is_input: True for input parameters, False for output parameters

        Returns:
            ParameterCreationSpec object with all parameter details
        """
        prefix = self._INPUT_PARAMETER_PREFIX if is_input else self._OUTPUT_PARAMETER_PREFIX
        prefixed_name = f"{prefix}{param_name}"

        param_type = param_dict.get("type", "str")
        tooltip = param_dict.get(
            "tooltip", f"{'Input' if is_input else 'Output'} parameter {param_name} for subworkflow"
        )
        default_value = param_dict.get("default_value") if is_input else None
        ui_options = param_dict.get("ui_options", {})

        if is_input:
            input_types = param_dict.get("input_types", [param_type])
            output_type = None
        else:
            input_types = None
            output_type = param_dict.get("output_type", param_type)

        return ParameterCreationSpec(
            name=prefixed_name,
            param_type=param_type,
            input_types=input_types,
            output_type=output_type,
            tooltip=tooltip,
            default_value=default_value,
            ui_options=ui_options,
            is_input=is_input,
        )

    def _create_parameter_from_spec(self, spec: ParameterCreationSpec) -> None:
        """Create a parameter from a specification.

        Args:
            spec: Parameter creation specification

        Raises:
            RuntimeError: If parameter creation fails
        """
        if spec.is_input:
            add_request = AddParameterToNodeRequest(
                node_name=self.name,
                parameter_name=spec.name,
                input_types=spec.input_types,
                tooltip=spec.tooltip,
                mode_allowed_input=True,
                mode_allowed_property=True,
                mode_allowed_output=False,
                default_value=spec.default_value,
                ui_options=spec.ui_options,
                is_user_defined=True,
            )
        else:
            add_request = AddParameterToNodeRequest(
                node_name=self.name,
                parameter_name=spec.name,
                output_type=spec.output_type,
                tooltip=spec.tooltip,
                mode_allowed_input=False,
                mode_allowed_property=False,
                mode_allowed_output=True,
                ui_options=spec.ui_options,
                is_user_defined=True,
            )

        result = GriptapeNodes.handle_request(add_request)
        if not isinstance(result, AddParameterToNodeResultSuccess):
            msg = f"Parameter creation failed: {result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Get the created parameter and add to tracking
        param = self.get_parameter_by_name(spec.name)
        if not param:
            msg = f"Parameter '{spec.name}' was not created successfully"
            raise RuntimeError(msg)

        if spec.is_input:
            self._dynamic_input_parameters.append(param)
        else:
            self._dynamic_output_parameters.append(param)

    def _clear_dynamic_parameters(self) -> None:
        """Clear all dynamic parameters."""
        # Remove all dynamic input parameters
        for param in self._dynamic_input_parameters[:]:  # Copy list to avoid modification during iteration
            self._remove_parameter(param)
        self._dynamic_input_parameters.clear()

        # Remove all dynamic output parameters
        for param in self._dynamic_output_parameters[:]:  # Copy list to avoid modification during iteration
            self._remove_parameter(param)
        self._dynamic_output_parameters.clear()

    def _remove_parameter(self, parameter: Parameter) -> None:
        """Remove a parameter from the node using the event system.

        Raises:
            RuntimeError: If parameter removal fails
        """
        remove_request = RemoveParameterFromNodeRequest(parameter_name=parameter.name, node_name=self.name)
        result = GriptapeNodes.handle_request(remove_request)
        if not isinstance(result, RemoveParameterFromNodeResultSuccess):
            msg = f"Failed to remove parameter '{parameter.name}': {result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

    def process(self) -> None:
        """Execute the selected subflow."""
        # Step 1: Reset execution state
        self._clear_execution_status()

        # Step 2: Get selected workflow
        selected_workflow = self.get_parameter_value(self.workflow_selector.name)
        if not selected_workflow or selected_workflow == self._DEFAULT_SELECTION_TEXT:
            logger.error("No workflow selected")
            self._set_status_results(
                was_successful=False, result_details="No workflow selected. Please choose a workflow from the dropdown."
            )
            return

        # Step 3: Clean up workflow name and validate
        clean_workflow_name = selected_workflow.rstrip(" *")
        if clean_workflow_name not in self._available_workflows:
            logger.error("Unknown workflow: %s", clean_workflow_name)
            self._set_status_results(
                was_successful=False,
                result_details=f"Unknown workflow '{clean_workflow_name}'. Please select a valid workflow.",
            )
            return

        # Step 4: Re-assess fitness before execution
        workflow_info = self._available_workflows[clean_workflow_name]
        if not workflow_info.is_runnable:
            logger.error("Workflow is not runnable: %s", clean_workflow_name)
            issues = "; ".join([f"{problem.issue}: {problem.remedy}" for problem in workflow_info.problems])
            self._set_status_results(
                was_successful=False, result_details=f"Workflow '{clean_workflow_name}' is not runnable: {issues}"
            )
            return

        # Step 5: Execute the workflow
        try:
            self._execute_workflow(clean_workflow_name, workflow_info)
        except Exception as e:
            logger.error("Failed to execute workflow '%s': %s", clean_workflow_name, e)
            self._set_status_results(
                was_successful=False, result_details=f"Failed to execute workflow '{clean_workflow_name}': {e!s}"
            )

    def _execute_workflow(self, workflow_name: str, workflow_info: WorkflowInfo) -> None:
        """Execute the selected workflow using the registry.

        Args:
            workflow_name: Name of the workflow to execute
            workflow_info: WorkflowInfo object containing metadata and status

        Raises:
            RuntimeError: If workflow execution fails
        """
        # Get our current flow name to establish proper context
        get_flow_request = GetFlowForNodeRequest(node_name=self.name)
        flow_result = GriptapeNodes.handle_request(get_flow_request)

        if not isinstance(flow_result, GetFlowForNodeResultSuccess):
            msg = f"Failed to find flow for node '{self.name}': {flow_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        current_flow_name = flow_result.flow_name

        # Create a temporary child flow for the subworkflow execution
        temp_flow_name = f"RunSubflow_{workflow_name}_{self.name}"
        create_flow_request = CreateFlowRequest(
            parent_flow_name=current_flow_name,
            flow_name=temp_flow_name,
            set_as_new_context=False,
            metadata={"created_by": "RunSubflow", "source_workflow": workflow_name},
        )
        create_result = GriptapeNodes.handle_request(create_flow_request)

        if not isinstance(create_result, CreateFlowResultSuccess):
            msg = f"Failed to create temporary flow: {create_result.result_details}"
            raise RuntimeError(msg)  # noqa: TRY004

        # Execute the workflow within the temporary flow context
        with GriptapeNodes.ContextManager().flow(temp_flow_name):
            try:
                # Step 1: Prepare input mapping from our parameters to workflow inputs
                try:
                    workflow_input = self._build_workflow_input(workflow_info.metadata)
                    logger.info("Built workflow input with %d entries", len(workflow_input))
                except Exception as e:
                    msg = f"Failed to build workflow input: {e}"
                    raise RuntimeError(msg) from e

                # Step 2: Execute the workflow using RunWorkflowWithCurrentStateRequest
                # Get workflow from registry to get the proper file path
                try:
                    workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)
                    workflow_file_path = workflow.file_path
                    logger.debug("Found workflow file path: %s", workflow_file_path)
                except KeyError as e:
                    msg = f"Failed to get workflow '{workflow_name}' from registry: {e}"
                    raise RuntimeError(msg) from e

                run_request = RunWorkflowWithCurrentStateRequest(file_path=workflow_file_path)

                # TODO: We need to figure out how to pass the input parameters to the workflow
                # RunWorkflowWithCurrentStateRequest preserves state but may not support input parameters
                # This may require a different approach or request type

                run_result = GriptapeNodes.handle_request(run_request)

                if not isinstance(run_result, RunWorkflowWithCurrentStateResultSuccess):
                    msg = f"Workflow execution failed: {run_result.result_details}"
                    raise RuntimeError(msg)  # noqa: TRY301, TRY004

                # Step 3: Extract output values and populate our output parameters
                self._extract_workflow_outputs(run_result, workflow_info.metadata)

                # Success path
                self._set_status_results(
                    was_successful=True, result_details=f"Successfully executed workflow '{workflow_name}'"
                )

            except Exception as e:
                logger.error("Failed to execute workflow '%s': %s", workflow_name, e)
                self._set_status_results(was_successful=False, result_details=f"Error during workflow execution: {e!s}")
                raise
            finally:
                # Always clean up the temporary flow (cascades to all children)
                delete_request = DeleteFlowRequest(flow_name=temp_flow_name)
                delete_result = GriptapeNodes.handle_request(delete_request)
                if delete_result.succeeded():
                    logger.debug("Successfully deleted temporary flow '%s'", temp_flow_name)
                else:
                    logger.warning(
                        "Failed to delete temporary flow '%s': %s", temp_flow_name, delete_result.result_details
                    )

    def _build_workflow_input(self, workflow_metadata: Any) -> dict:
        """Build input dictionary from our parameters for workflow execution.

        Args:
            workflow_metadata: The workflow metadata object containing workflow_shape

        Returns:
            Dictionary mapping start node names to parameter values

        Raises:
            RuntimeError: If workflow_shape is missing or invalid
        """
        workflow_input = {}

        try:
            workflow_shape_json = getattr(workflow_metadata, "workflow_shape", None)
            if not workflow_shape_json:
                msg = "Workflow metadata is missing workflow_shape"
                raise RuntimeError(msg)
        except AttributeError as e:
            msg = f"Invalid workflow metadata object: {e}"
            raise RuntimeError(msg) from e

        try:
            workflow_shape = json.loads(workflow_shape_json)
            inputs_shape = workflow_shape.get("inputs", {})
        except json.JSONDecodeError as e:
            msg = f"Invalid workflow_shape JSON format: {e}"
            raise RuntimeError(msg) from e

        # Build input mapping: {start_node_name: {param_name: value}}
        for start_node_name, node_params in inputs_shape.items():
            workflow_input[start_node_name] = {}

            for param_name in node_params:
                # Get value from our prefixed input parameter
                prefixed_name = f"{self._INPUT_PARAMETER_PREFIX}{param_name}"
                param_value = self.get_parameter_value(prefixed_name)

                if param_value is not None:
                    workflow_input[start_node_name][param_name] = param_value

        return workflow_input

    def _extract_workflow_outputs(self, _run_result: Any, workflow_metadata: Any) -> None:
        """Extract output values from workflow execution and populate our output parameters.

        Args:
            _run_result: The result from workflow execution (unused for now)
            workflow_metadata: The workflow metadata object containing workflow_shape

        Raises:
            RuntimeError: If workflow_shape is missing or invalid
        """
        # TODO: This needs to be implemented once we understand how to get outputs
        # from the workflow execution result. The structure of run_result needs exploration.

        try:
            workflow_shape_json = getattr(workflow_metadata, "workflow_shape", None)
            if not workflow_shape_json:
                msg = "Workflow metadata is missing workflow_shape"
                raise RuntimeError(msg)
        except AttributeError as e:
            msg = f"Invalid workflow metadata object: {e}"
            raise RuntimeError(msg) from e

        try:
            workflow_shape = json.loads(workflow_shape_json)
            outputs_shape = workflow_shape.get("outputs", {})
        except json.JSONDecodeError as e:
            msg = f"Invalid workflow_shape JSON format: {e}"
            raise RuntimeError(msg) from e

        # For now, just log what we have and set placeholder values
        logger.info("TODO: Extract outputs from workflow result for shapes: %s", list(outputs_shape.keys()))

        # Set placeholder values in our output parameters
        for node_params in outputs_shape.values():
            for param_name in node_params:
                prefixed_name = f"{self._OUTPUT_PARAMETER_PREFIX}{param_name}"
                # TODO: Extract actual value from run_result
                self.parameter_output_values[prefixed_name] = f"TODO: Extract {param_name} from result"
