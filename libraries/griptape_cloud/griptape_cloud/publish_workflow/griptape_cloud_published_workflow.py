import contextlib
import json
import logging
from enum import StrEnum
from typing import Any

from griptape_cloud_client.models.deployment_status import DeploymentStatus
from griptape_cloud_client.types import Unset

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.execution_status_component import ExecutionStatusComponent

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class PublishedWorkflowExecutionStatus(StrEnum):
    """Status enum for published workflow execution."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class GriptapeCloudPublishedWorkflow(SuccessFailureNode, BaseGriptapeCloudNode):
    def __init__(self, name: str | None = None, **kwargs) -> None:
        # Handle name as either positional or keyword argument
        if name is not None:
            kwargs["name"] = name
        super().__init__(**kwargs)

        metadata = kwargs.get("metadata", {})

        # Store workflow shape and structure info
        self.workflow_shape = metadata.get("workflow_shape", {})
        self.structure_id = metadata.get("structure_id", None)
        self.structure_name = metadata.get("structure_name", "Published Workflow")

        if self.structure_id is None:
            self.add_node_element(
                ParameterMessage(
                    name="gtc_published_workflow_parameter_message",
                    title="Griptape Cloud Published Workflow Configuration Warning",
                    variant="warning",
                    value=self.get_help_message(),
                )
            )

        self.structure_deployment_parameter_message: ParameterMessage = ParameterMessage(
            name="structure_deployment_parameter_message",
            title="Griptape Cloud Structure Deployment Warning",
            variant="warning",
            value=(
                f"The Griptape Cloud Published Workflow Node is not configured to invoke Structure: {self.structure_name} ({self.structure_id}\n\n"
                "The Structure is not ready to run! Please ensure it has a successful deployment."
                "To check the status of your Structure, you can visit Griptape Cloud here: \n"
                f"{self.base_url}/structures/{self.structure_id}"
            ),
        )
        self.has_successful_deployment = True

        # Add basic structure information parameters
        with ParameterGroup(name="Griptape Cloud Structure Details") as structure_details_group:
            Parameter(
                name="name",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=self.structure_name,
                tooltip="The name of the published workflow structure",
                allowed_modes={ParameterMode.OUTPUT},
            )

            Parameter(
                name="structure_id",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=self.structure_id,
                tooltip="The structure ID of the published workflow",
                allowed_modes={ParameterMode.OUTPUT},
            )

            Parameter(
                name="structure_run_id",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=None,
                tooltip="The ID of the structure run",
                allowed_modes={ParameterMode.OUTPUT},
            )

        structure_details_group.ui_options = {"hide": False, "collapsed": True}
        self.add_node_element(structure_details_group)

        # Add events group
        with ParameterGroup(name="Events") as events_group:
            Parameter(name="include_events", type="bool", default_value=False, tooltip="Include events details.")

            Parameter(
                name="events",
                type="str",
                tooltip="Displays processing events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Events"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        events_group.ui_options = {"hide": False, "collapsed": True}
        self.add_node_element(events_group)

        # Add status parameters
        self.status_component = ExecutionStatusComponent(
            self,
            was_successful_modes={ParameterMode.PROPERTY},
            result_details_modes={ParameterMode.OUTPUT},
            parameter_group_initially_collapsed=False,
            result_details_tooltip="Details about the published workflow execution result",
            result_details_placeholder="Details on the published workflow execution will be presented here.",
        )

    @classmethod
    def get_default_node_parameter_names(cls) -> list[str]:
        """Get the names of the parameters configured on the node by default."""
        # Execution Status Component parameters
        structure_params = ["name", "structure_id", "structure_run_id"]
        event_params = ["include_events", "events"]
        params = structure_params + event_params
        params.extend(["was_successful", "result_details"])
        params.extend(["exec_in", "exec_out", "failed"])
        return params

    @classmethod
    def get_help_message(cls) -> str:
        return (
            "The Griptape Cloud Published Workflow node is intended to be auto-generated via publishing a Workflow.\n\n "
            "To publish a Workflow to Griptape Cloud, you can:\n"
            "   1. Configure a Workflow in the GUI with Start Flow and End Flow Nodes\n"
            "   2. Click the 'Publish' button (rocket icon, top right) to publish the workflow to Griptape Cloud\n"
            "   3. Open the resulting Workflow in the GUI, which will have the Griptape Cloud Published Workflow node configured"
        )

    def process(
        self,
    ) -> AsyncResult[None]:
        yield lambda: self._process()

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("structure_id"):
                msg = "Structure ID is not set. Configure the Node with a valid Griptape Cloud Structure ID before running."
                exceptions.append(ValueError(msg))

            structure_id = self.get_parameter_value("structure_id")

            list_structure_deployments_response = self._list_structure_deployments(
                structure_id=structure_id, status=[DeploymentStatus.SUCCEEDED]
            )
            if not any(
                self._is_deployment_ready(deployment) for deployment in list_structure_deployments_response.deployments
            ):
                # Do not raise an exception, just add a warning message to the node
                # This is important for the "execute immediately on publish" use case
                # as the structure may still be deploying when the published workflow is invoked
                self.has_successful_deployment = False
                self.add_node_element(self.structure_deployment_parameter_message)

        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)

        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def _collect_input_parameters(self) -> dict[str, dict[str, Any]]:
        """Collect input parameters and structure them for the published workflow."""
        input_json = {}

        if "input" not in self.workflow_shape:
            return input_json

        for node_name, node_params in self.workflow_shape["input"].items():
            if isinstance(node_params, dict):
                node_inputs = {}
                for param_name in node_params:
                    param_value = self.get_parameter_value(param_name)

                    if param_value is not None:
                        node_inputs[param_name] = param_value

                if node_inputs:
                    input_json[node_name] = node_inputs

        return input_json

    def _map_output_parameters(self, structure_output: dict[str, Any] | None) -> None:
        """Map structure output to output parameters."""
        if not structure_output or "output" not in self.workflow_shape:
            return

        logger.info("Mapping output parameters for structure '%s' with output: %s", self.structure_id, structure_output)

        for node_name, node_params in self.workflow_shape["output"].items():
            logger.info("Processing node '%s' with parameters: %s", node_name, node_params)
            if isinstance(node_params, dict) and node_name in structure_output:
                node_outputs = structure_output[node_name]
                logger.warning("Node '%s' outputs: %s", node_name, node_outputs)
                if isinstance(node_outputs, dict):
                    for param_name in node_params:
                        logger.info("Checking parameter '%s' in node '%s'", param_name, node_name)
                        # Check if this parameter exists in the output
                        if param_name in node_outputs:
                            param_value = node_outputs[param_name]
                            logger.info("Found output parameter '%s' with value: %s", param_name, param_value)

                            # Set the output parameter value
                            self.set_parameter_value(
                                param_name=param_name,
                                value=param_value,
                            )
                            self.parameter_output_values[param_name] = param_value
                            logger.info("Set output parameter %s = %s", param_name, param_value)

    def _handle_execution_result(
        self,
        status: PublishedWorkflowExecutionStatus,
        details: str,
        exception: Exception | None = None,
    ) -> None:
        """Handle execution result for all cases."""
        match status:
            case PublishedWorkflowExecutionStatus.FAILED:
                failure_details = f"Published Workflow execution failed\nError: {details}"

                if exception:
                    failure_details += f"\nException type: {type(exception).__name__}"
                    if exception.__cause__:
                        failure_details += f"\nCause: {exception.__cause__}"

                self._set_status_results(was_successful=False, result_details=f"[{status}]: {failure_details}")
                msg = f"Error executing published workflow: {details}"
                logger.error(msg)

            case PublishedWorkflowExecutionStatus.SUCCEEDED:
                result_details = "Published Workflow executed successfully\n"
                self._set_status_results(was_successful=True, result_details=f"[{status}]: {result_details}")

    def _handle_error_with_graceful_exit(self, error_details: str, exception: Exception) -> None:
        """Handle error with graceful exit if failure output is connected."""
        self._handle_execution_result(
            status=PublishedWorkflowExecutionStatus.FAILED,
            details=error_details,
            exception=exception,
        )
        # Use the helper to handle exception based on connection status
        self._handle_failure_exception(RuntimeError(error_details))

    def _process(self) -> None:
        try:
            include_events = self.get_parameter_value("include_events")

            # Collect input parameters and construct JSON for structure run
            input_json = self._collect_input_parameters()

            # Create args list with -i flag and JSON string
            args = ["-i", json.dumps(input_json)]

            # Wait for the latest deployment to be ready
            self._wait_for_latest_structure_deployment(structure_id=self.structure_id)
            if not self.has_successful_deployment:
                self.remove_node_element(self.structure_deployment_parameter_message)
                self.has_successful_deployment = True

            # Create and run the structure
            structure_run = self._create_structure_run(structure_id=self.structure_id, args=args)

            # Poll for events if requested
            for events in self._poll_structure_run_events(structure_run_id=structure_run.structure_run_id):
                self.append_value_to_parameter(
                    parameter_name=self.status_component._result_details.name,
                    value="\n".join(f"Structure Run Event: {event.payload!s}" for event in events),
                )
                if include_events:
                    self.append_value_to_parameter("events", "\n".join(str(event.payload) for event in events))

            # Get the final structure run result
            structure_run = self._get_structure_run(structure_run_id=structure_run.structure_run_id)

            if structure_run.status in self._get_structure_run_bad_statuses():
                details = f"Structure run ended with status: {structure_run.status}"
                raise RuntimeError(details)  # noqa: TRY301

            output = structure_run.output if not isinstance(structure_run.output, Unset) else None

            if isinstance(output, dict) and "value" in output:
                with contextlib.suppress(json.JSONDecodeError):
                    # Attempt to parse the output value as JSON
                    output = json.loads(output["value"])

            # Set the structure run ID output parameter
            self.parameter_output_values["structure_run_id"] = structure_run.structure_run_id

            # Map output to output parameters
            self._map_output_parameters(output)

            self._handle_execution_result(
                status=PublishedWorkflowExecutionStatus.SUCCEEDED,
                details=f"Published workflow executed successfully with Structure Run ID: {structure_run.structure_run_id}",
            )
        except Exception as e:
            details = f"Error during published workflow execution: {e}"
            logger.exception(details)
            self._handle_error_with_graceful_exit(details, e)
            return
