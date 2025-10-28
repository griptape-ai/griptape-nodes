"""WorkflowBuilder for generating a Griptape Nodes workflow that can invoke a published workflow in the form of a Griptape Cloud structure.

This module provides simple script generation for creating workflows that follow the pattern:
StartNode -> PublishedWorkflow -> EndNode

The generated workflows can execute published structures in Griptape Cloud using the
PublishedWorkflow node which handles parameter mapping automatically.
"""

import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from griptape_cloud.publish_workflow.griptape_cloud_published_workflow import GriptapeCloudPublishedWorkflow
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")


@dataclass
class GriptapeCloudWorkflowBuilderInput:
    workflow_name: str
    workflow_shape: dict[str, Any]
    executor_workflow_name: str
    structure_id: str
    libraries: list[str] = field(default_factory=list)
    pickle_control_flow_result: bool = False


class GriptapeCloudWorkflowBuilder:
    """Builder class for generating executor workflows using simple script generation."""

    def __init__(
        self,
        workflow_builder_input: GriptapeCloudWorkflowBuilderInput,
    ) -> None:
        """Initialize the WorkflowBuilder.

        Args:
            workflow_builder_input: Configuration input for the workflow builder
        """
        self.workflow_builder_input = workflow_builder_input

    def generate_executor_workflow(self) -> Path:
        """Generate an executor workflow that can invoke the published structure."""
        # Generate a simple workflow creation script using PublishedWorkflow node
        workflow_script = self._build_simple_workflow_script(
            self.workflow_builder_input.structure_id,
            self.workflow_builder_input.workflow_shape,
            self.workflow_builder_input.libraries,
        )

        # Execute the script in a subprocess to create the workflow
        self._execute_workflow_script(workflow_script)

        # Verify the workflow was created successfully
        executor_workflow_path = GriptapeNodes.ConfigManager().workspace_path / (
            self.workflow_builder_input.executor_workflow_name + ".py"
        )
        if not executor_workflow_path.exists():
            error_msg = (
                f"Executor workflow {self.workflow_builder_input.executor_workflow_name} was not created successfully."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        return executor_workflow_path

    def _build_library_registration_script(self, libraries: list[str]) -> str:
        """Build a script to register libraries for the workflow.

        Args:
            libraries: List of library paths to register

        Returns:
            Complete Python script as string
        """
        if not libraries:
            return ""

        # Build the library registration script
        script = ""

        for i, lib in enumerate(libraries):
            if lib.endswith(".json"):
                script += f"""
    request_{i!s} = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path="{lib}"))
"""
            else:
                script += f"""
    request_{i!s} = GriptapeNodes.handle_request(RegisterLibraryFromRequirementSpecifierRequest(requirement_specifier="{lib}"))
"""
        return script

    def _extract_parameters_from_shape(self, workflow_shape: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """Extract input and output parameters from workflow shape.

        Args:
            workflow_shape: The workflow shape containing input/output parameter structure

        Returns:
            Tuple of (input_params, output_params)
        """
        input_params = []
        if "input" in workflow_shape:
            for node_params in workflow_shape["input"].values():
                if isinstance(node_params, dict):
                    input_params.extend(node_params.values())

        output_params = []
        if "output" in workflow_shape:
            for node_params in workflow_shape["output"].values():
                if isinstance(node_params, dict):
                    output_params.extend(node_params.values())

        return input_params, output_params

    def _build_script_header(self, structure_id: str, libraries: list[str]) -> str:
        """Build the header section of the workflow script.

        Args:
            structure_id: The Griptape Cloud structure ID
            libraries: List of libraries needed for the workflow

        Returns:
            Script header as string
        """
        return f'''
"""
Generated executor workflow for invoking published Griptape Cloud structure.
This workflow was automatically created to execute structure: {structure_id}
"""

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.events.flow_events import CreateFlowRequest
from griptape_nodes.retained_mode.events.node_events import CreateNodeRequest
from griptape_nodes.retained_mode.events.library_events import (
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromRequirementSpecifierRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import AddParameterToNodeRequest
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest
from griptape_nodes.retained_mode.events.workflow_events import SaveWorkflowRequest

def main():
    {self._build_library_registration_script(libraries)}

    context_manager = GriptapeNodes.ContextManager()
    if not context_manager.has_current_workflow():
        context_manager.push_workflow(workflow_name="{self.workflow_builder_input.executor_workflow_name}")

    # Create the main flow
    flow_response = GriptapeNodes.handle_request(CreateFlowRequest(parent_flow_name=None))
    flow_name = flow_response.flow_name

    with GriptapeNodes.ContextManager().flow(flow_name):'''

    def _build_node_creation_script(self, structure_id: str, workflow_shape: dict[str, Any]) -> str:
        """Build the node creation section of the workflow script.

        Args:
            structure_id: The Griptape Cloud structure ID
            workflow_shape: Input/output parameter structure

        Returns:
            Node creation script as string
        """
        return f"""
        # Create StartNode
        start_node_response = GriptapeNodes.handle_request(CreateNodeRequest(
            node_type="StartFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="Start Flow",
            initial_setup=True
        ))
        start_node_name = start_node_response.node_name

        # Create GriptapeCloudPublishedWorkflow node
        published_wf_response = GriptapeNodes.handle_request(CreateNodeRequest(
            node_type="GriptapeCloudPublishedWorkflow",
            specific_library_name="Griptape Cloud Library",
            node_name="Griptape Cloud Published Workflow",
            metadata={{
                "workflow_shape": {workflow_shape!r},
                "structure_id": "{structure_id}",
                "structure_name": "{self.workflow_builder_input.workflow_name}"
            }},
            initial_setup=True
        ))
        published_wf_name = published_wf_response.node_name

        # Create EndNode
        end_node_response = GriptapeNodes.handle_request(CreateNodeRequest(
            node_type="EndFlow",
            specific_library_name="Griptape Nodes Library",
            node_name="End Flow",
            initial_setup=True
        ))
        end_node_name = end_node_response.node_name"""

    def _build_parameter_configuration_script(self, input_params: list[dict], output_params: list[dict]) -> str:
        """Build the parameter configuration section of the workflow script.

        Args:
            input_params: List of input parameter configurations
            output_params: List of output parameter configurations

        Returns:
            Parameter configuration script as string
        """
        script = """

        # Configure StartNode parameters
        with GriptapeNodes.ContextManager().node(start_node_name):"""

        script += self._build_node_parameters(
            input_params,
            "StartNode",
            mode_input=False,
            mode_property=True,
            mode_output=True,
            omit_parameters=["exec_out"],
        )

        script += """

        # Configure GriptapeCloudPublishedWorkflow parameters
        with GriptapeNodes.ContextManager().node(published_wf_name):"""

        script += self._build_node_parameters(
            input_params,
            "GriptapeCloudPublishedWorkflow input",
            mode_input=True,
            mode_property=True,
            mode_output=False,
            omit_parameters=GriptapeCloudPublishedWorkflow.get_default_node_parameter_names(),
        )
        script += self._build_node_parameters(
            output_params,
            "GriptapeCloudPublishedWorkflow output",
            mode_input=False,
            mode_property=True,
            mode_output=True,
            omit_parameters=GriptapeCloudPublishedWorkflow.get_default_node_parameter_names(),
        )

        script += """

        # Configure EndNode parameters
        with GriptapeNodes.ContextManager().node(end_node_name):"""

        script += self._build_node_parameters(
            output_params,
            "EndNode",
            mode_input=True,
            mode_property=True,
            mode_output=False,
            omit_parameters=["was_successful", "result_details", "exec_in", "failed"],
        )

        return script

    def _build_node_parameters(
        self,
        params: list[dict],
        _node_type: str,
        *,
        mode_input: bool,
        mode_property: bool,
        mode_output: bool,
        omit_parameters: list[str] | None = None,
    ) -> str:
        """Build parameter configuration for a specific node.

        Args:
            params: List of parameter configurations
            _node_type: Type of node (for documentation purposes)
            mode_input: Whether input mode is allowed
            mode_property: Whether property mode is allowed
            mode_output: Whether output mode is allowed
            omit_parameters: List of parameter names to omit from configuration

        Returns:
            Parameter configuration script as string
        """
        if omit_parameters is None:
            omit_parameters = []
        omit_parameters.append("execution_environment")  # Always omit this parameter

        # Check if there are any parameters left after omitting
        param_names = {param["name"] for param in params}
        remaining_params = param_names - set(omit_parameters)

        if len(remaining_params) == 0:
            return """
            pass
        """

        script = ""
        for param in params:
            param_config = dict(param)
            param_name = param_config.pop("name")
            param_config["parameter_name"] = param_name
            param_config.pop("settable", None)
            if param_name not in omit_parameters:
                script += f"""
            GriptapeNodes.handle_request(AddParameterToNodeRequest(
                **{param_config},
                mode_allowed_input={mode_input},
                mode_allowed_property={mode_property},
                mode_allowed_output={mode_output},
                initial_setup=True
            ))"""
        return script

    def _build_connection_creation_script(self, input_params: list[dict], output_params: list[dict]) -> str:
        """Build the connection creation section of the workflow script.

        Args:
            input_params: List of input parameter configurations
            output_params: List of output parameter configurations

        Returns:
            Connection creation script as string
        """
        script = """

    # Create connections between StartNode and GriptapeCloudPublishedWorkflow"""

        # Add connections for each input parameter
        for param in input_params:
            script += f"""
    GriptapeNodes.handle_request(CreateConnectionRequest(
        source_node_name=start_node_name,
        source_parameter_name="{param["name"]}",
        target_node_name=published_wf_name,
        target_parameter_name="{param["name"]}",
        initial_setup=True
    ))"""

        script += """

    # Create connections between GriptapeCloudPublishedWorkflow and EndNode"""

        # Add connections for each output parameter
        for param in output_params:
            if param["name"] not in ["exec_out", "failure"]:
                script += f"""
    GriptapeNodes.handle_request(CreateConnectionRequest(
        source_node_name=published_wf_name,
        source_parameter_name="{param["name"]}",
        target_node_name=end_node_name,
        target_parameter_name="{param["name"]}",
        initial_setup=True
    ))"""

        control_flow: dict = {"exec_out": "exec_in", "failure": "failed"}
        for key, val in control_flow.items():
            script += f"""
    GriptapeNodes.handle_request(CreateConnectionRequest(
        source_node_name=published_wf_name,
        source_parameter_name="{key}",
        target_node_name=end_node_name,
        target_parameter_name="{val}",
        initial_setup=True
    ))"""

        return script

    def _build_script_footer(self) -> str:
        """Build the footer section of the workflow script.

        Returns:
            Script footer as string
        """
        return f"""

    # Save the workflow
    save_response = GriptapeNodes.handle_request(SaveWorkflowRequest(
        file_name="{self.workflow_builder_input.executor_workflow_name}",
        pickle_control_flow_result={self.workflow_builder_input.pickle_control_flow_result}))

    if save_response.succeeded():
        print(f"Successfully created executor workflow: {self.workflow_builder_input.executor_workflow_name}")
    else:
        print(f"Failed to create executor workflow")
        exit(1)

if __name__ == "__main__":
    main()
"""

    def _build_simple_workflow_script(
        self, structure_id: str, workflow_shape: dict[str, Any], libraries: list[str]
    ) -> str:
        """Build a simple workflow creation script using PublishedWorkflow node.

        Args:
            structure_id: The Griptape Cloud structure ID
            workflow_shape: Input/output parameter structure
            libraries: List of libraries needed for the workflow

        Returns:
            Complete Python script as string
        """
        # Extract parameters from workflow shape
        input_params, output_params = self._extract_parameters_from_shape(workflow_shape)

        # Build script sections
        header = self._build_script_header(structure_id, libraries)
        nodes = self._build_node_creation_script(structure_id, workflow_shape)
        params = self._build_parameter_configuration_script(input_params, output_params)
        connections = self._build_connection_creation_script(input_params, output_params)
        footer = self._build_script_footer()

        return header + nodes + params + connections + footer

    def _execute_workflow_script(self, script: str) -> None:
        """Execute the workflow creation script in a subprocess."""
        temp_script_path = Path(__file__).parent / f"temp_executor_{uuid.uuid4().hex}.py"

        try:
            with temp_script_path.open("w", encoding="utf-8") as f:
                f.write(script)

            # Execute the script in a subprocess to isolate the GriptapeNodes state
            result = subprocess.run(  # noqa: S603
                [sys.executable, str(temp_script_path)],
                capture_output=True,
                text=True,
                cwd=temp_script_path.parent,
                timeout=300,
                check=False,
            )

            # Print subprocess output
            if result.stdout:
                logger.debug(result.stdout)
            if result.stderr:
                logger.debug(result.stderr)

            if result.returncode != 0:
                error_msg = f"Executor workflow generation failed: {result.stderr}"
                logger.error("Failed to generate executor workflow: %s", result.stderr)
                raise RuntimeError(error_msg)

            logger.info(
                "Successfully generated executor workflow: %s", self.workflow_builder_input.executor_workflow_name
            )

        finally:
            # Clean up temporary script
            if temp_script_path.exists():
                temp_script_path.unlink()
