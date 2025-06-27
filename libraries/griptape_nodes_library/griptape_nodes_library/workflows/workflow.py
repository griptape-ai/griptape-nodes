import json
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

logger = logging.getLogger(__name__)


class Workflow(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.workflow_file_path: str | None = None
        self.workflow_shape: dict[str, Any] | None = None

        self.add_parameter(
            Parameter(
                name="workflow_file",
                type="str",
                input_types=["str"],
                output_type="str",
                default_value="",
                tooltip="Path to the workflow Python file to execute",
                allowed_modes={
                    ParameterMode.INPUT,
                    ParameterMode.PROPERTY,
                },
            )
        )

    def _extract_workflow_shape_in_subprocess(self, file_path: str) -> dict[str, Any]:
        """Extract workflow shape by running the workflow file in a separate process for complete isolation."""
        if not Path(file_path).exists():
            msg = f"Workflow file not found: {file_path}"
            raise FileNotFoundError(msg)

        # Create temporary file for output
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_output:
            temp_output_path = temp_output.name

        # Create extraction script that runs in isolated subprocess
        extraction_script = f"""
import sys
import json
import os

# Add current directory to path to find griptape_nodes
sys.path.insert(0, "{Path.cwd()}")
sys.path.insert(0, "{Path.cwd() / "src"}")

output_file = "{temp_output_path}"

try:
    # Execute the workflow file (set __name__ to avoid running main block)
    with open("{file_path}", encoding="utf-8") as file:
        workflow_content = file.read()

    # Create a namespace that prevents the main block from running
    namespace = {{"__name__": "workflow_module", "__file__": "{file_path}"}}
    exec(workflow_content, namespace)

    # Import here to avoid import-time side effects
    from griptape_nodes.retained_mode.events.flow_events import GetTopLevelFlowRequest, GetTopLevelFlowResultSuccess
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    # Get the flow that was created
    flow_request = GetTopLevelFlowRequest()
    flow_result = GriptapeNodes.handle_request(flow_request)

    if isinstance(flow_result, GetTopLevelFlowResultSuccess) and flow_result.flow_name:
        # Extract the flow shape using the workflow manager
        workflow_manager = GriptapeNodes.WorkflowManager()
        workflow_shape = workflow_manager.extract_workflow_shape(flow_result.flow_name)

        # Write result to output file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({{"success": True, "shape": workflow_shape}}, f)
    else:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({{"success": False, "error": "No flow created by workflow file"}}, f)

except Exception as e:
    import traceback
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({{"success": False, "error": str(e), "traceback": traceback.format_exc()}}, f)
"""

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_script:
            temp_script.write(extraction_script)
            temp_script_path = temp_script.name

        try:
            # Run extraction script in subprocess
            result = subprocess.run(  # noqa: S603
                [sys.executable, temp_script_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=Path.cwd(),
                env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
                check=False,
            )

            if result.returncode != 0:
                msg = f"Extraction subprocess failed (code {result.returncode}): {result.stderr}"
                raise RuntimeError(msg)

            # Read result from output file
            if not Path(temp_output_path).exists():
                msg = f"Output file not created. STDERR: {result.stderr}"
                raise ValueError(msg)

            with Path(temp_output_path).open(encoding="utf-8") as f:
                output_data = json.load(f)

            if not output_data.get("success"):
                error_msg = output_data.get("error", "Unknown extraction error")
                if "traceback" in output_data:
                    error_msg += f"\nTraceback: {output_data['traceback']}"
                raise ValueError(error_msg)

            return output_data["shape"]

        except subprocess.TimeoutExpired as e:
            msg = "Workflow shape extraction timed out after 30 seconds"
            raise TimeoutError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse JSON from output file: {e}"
            raise ValueError(msg) from e
        finally:
            # Clean up temporary files
            Path(temp_script_path).unlink(missing_ok=True)
            Path(temp_output_path).unlink(missing_ok=True)

    def _purge_old_parameters(self, valid_parameter_names: set[str]) -> None:
        """Remove parameters that are no longer valid for the current workflow."""
        # Always maintain these core parameters
        valid_parameter_names.update(
            [
                "exec_in",
                "exec_out",
                "workflow_file",
            ]
        )

        for param in list(self.parameters):
            if param.name not in valid_parameter_names:
                self.remove_parameter_element(param)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Callback after a value has been set on this Node."""
        if parameter.name == "workflow_file" and value:
            try:
                # Extract the workflow shape in a subprocess
                workflow_shape = self._extract_workflow_shape_in_subprocess(value)

                self.workflow_file_path = value
                self.workflow_shape = workflow_shape

                # Get all parameter names that should exist
                valid_parameter_names = set()

                # Add input parameters
                for params in workflow_shape.get("input", {}).values():
                    for param_name, param_info in params.items():
                        valid_parameter_names.add(param_name)

                        # Create parameter for workflow input - use list[type] for collection
                        base_type = param_info.get("type", "str")
                        list_type = f"list[{base_type}]"
                        base_input_types = param_info.get("input_types", ["str"])
                        list_input_types = [f"list[{t}]" for t in base_input_types]
                        base_output_type = param_info.get("output_type", "str")
                        list_output_type = f"list[{base_output_type}]"

                        self.add_parameter(
                            Parameter(
                                name=param_name,
                                type=list_type,
                                input_types=list_input_types,
                                output_type=list_output_type,
                                tooltip=param_info.get("tooltip", f"Input parameter {param_name} (list)"),
                                allowed_modes={ParameterMode.INPUT},
                                user_defined=False,
                            )
                        )

                # Add output parameters
                for params in workflow_shape.get("output", {}).values():
                    for param_name, param_info in params.items():
                        valid_parameter_names.add(param_name)

                        # Create parameter for workflow output - use list[type] for collection
                        base_type = param_info.get("type", "str")
                        list_type = f"list[{base_type}]"
                        base_input_types = param_info.get("input_types", ["str"])
                        list_input_types = [f"list[{t}]" for t in base_input_types]
                        base_output_type = param_info.get("output_type", "str")
                        list_output_type = f"list[{base_output_type}]"

                        self.add_parameter(
                            Parameter(
                                name=param_name,
                                type=list_type,
                                input_types=list_input_types,
                                output_type=list_output_type,
                                tooltip=param_info.get("tooltip", f"Output parameter {param_name} (list)"),
                                allowed_modes={ParameterMode.OUTPUT},
                                user_defined=False,
                            )
                        )

                # Remove old parameters that are no longer valid
                self._purge_old_parameters(valid_parameter_names)

            except Exception as e:
                logger.error("Error loading workflow file %s: %s", value, str(e))
                msg = f"Failed to load workflow file: {e}"
                raise ValueError(msg) from e

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate the node before workflow execution."""
        exceptions = []

        if not self.workflow_file_path:
            exceptions.append(ValueError("No workflow file specified"))

        if not Path(self.workflow_file_path or "").exists():
            exceptions.append(FileNotFoundError(f"Workflow file not found: {self.workflow_file_path}"))

        return exceptions if exceptions else None

    def _get_max_input_list_length(self) -> int:
        """Get the maximum length of all input parameter lists."""
        if not self.workflow_shape:
            return 0

        max_length = 0
        for params in self.workflow_shape.get("input", {}).values():
            for param_name in params:
                param_value = self.get_parameter_value(param_name)
                if isinstance(param_value, list):
                    max_length = max(max_length, len(param_value))
        return max_length

    def _build_workflow_input_by_index(self, index: int) -> dict[str, Any]:
        """Build the input dictionary for the workflow for a specific list index."""
        workflow_input = {}

        if not self.workflow_shape:
            return workflow_input

        # Build input based on the workflow shape for specific index
        for node_name, params in self.workflow_shape.get("input", {}).items():
            workflow_input[node_name] = {}
            for param_name in params:
                param_value = self.get_parameter_value(param_name)
                if param_value is not None:
                    if isinstance(param_value, list):
                        # Use value at index if available, otherwise skip this parameter
                        if index < len(param_value):
                            workflow_input[node_name][param_name] = param_value[index]
                    else:
                        # Fallback for non-list values - use the same value for all indices
                        workflow_input[node_name][param_name] = param_value

        return workflow_input

    def _build_workflow_input(self) -> dict[str, Any]:
        """Build the input dictionary for the workflow based on parameter values (legacy method)."""
        # This method is kept for backward compatibility but should use index 0
        return self._build_workflow_input_by_index(0)

    def _set_workflow_outputs(self, workflow_output: dict[str, Any]) -> None:
        """Set the output parameter values from the workflow execution result (legacy method)."""
        if not workflow_output or not self.workflow_shape:
            return

        # Extract outputs based on the workflow shape
        for params in self.workflow_shape.get("output", {}).values():
            for param_name in params:
                for node_output in workflow_output.values():
                    if param_name in node_output:
                        self.set_parameter_value(param_name, [node_output[param_name]])

    def _aggregate_workflow_outputs(self, workflow_outputs: list[dict[str, Any] | None]) -> None:
        """Aggregate multiple workflow execution results into list parameters."""
        if not workflow_outputs or not self.workflow_shape:
            return

        # Initialize output lists
        output_lists: dict[str, list[Any]] = {}
        # Extract outputs based on the workflow shape
        for params in self.workflow_shape.get("output", {}).values():
            for param_name in params:
                output_lists[param_name] = []

        # Collect all outputs into lists
        for workflow_output in workflow_outputs:
            for params in self.workflow_shape.get("output", {}).values():
                for param_name in params:
                    found_value = False
                    if workflow_output is not None:
                        for node_output in workflow_output.values():
                            if param_name in node_output:
                                output_lists[param_name].append(node_output[param_name])
                                found_value = True
                                break
                    # If no value found, append None to maintain list alignment
                    if not found_value:
                        output_lists[param_name].append(None)

        # Set the aggregated lists as parameter values
        for param_name, values in output_lists.items():
            logger.info("Setting aggregated output for parameter '%s': %s", param_name, values)
            self.set_parameter_value(param_name, values)
            self.parameter_output_values[param_name] = values

    def _execute_workflow_in_subprocess(self, workflow_input: dict[str, Any]) -> dict[str, Any]:
        """Execute workflow in a separate subprocess to avoid disrupting current state."""
        if not self.workflow_file_path:
            msg = "No workflow file specified"
            raise ValueError(msg)

        # Create temporary file for output
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_output:
            temp_output_path = temp_output.name

        # Create execution script that runs in isolated subprocess
        execution_script = f"""
import sys
import json
import importlib.util

# Add current directory to path to find griptape_nodes
sys.path.insert(0, "{Path.cwd()}")
sys.path.insert(0, "{Path.cwd() / "src"}")

output_file = "{temp_output_path}"

try:
    # Import the workflow module dynamically
    spec = importlib.util.spec_from_file_location("workflow_module", "{self.workflow_file_path}")
    if spec is None or spec.loader is None:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({{"success": False, "error": "Could not load workflow module"}}, f)
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "execute_workflow"):
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({{"success": False, "error": "Workflow file does not contain execute_workflow function"}}, f)
        sys.exit(1)

    execute_workflow = module.execute_workflow

    # Parse input from command line argument
    workflow_input = json.loads(sys.argv[1])

    # Execute the workflow
    workflow_output = execute_workflow(workflow_input)

    # Write result to output file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({{"success": True, "output": workflow_output}}, f)

except Exception as e:
    import traceback
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({{"success": False, "error": str(e), "traceback": traceback.format_exc()}}, f)
    sys.exit(1)
"""

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as temp_script:
            temp_script.write(execution_script)
            temp_script_path = temp_script.name

        try:
            # Run execution script in subprocess
            result = subprocess.run(  # noqa: S603
                [sys.executable, temp_script_path, json.dumps(workflow_input)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=Path.cwd(),
                env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
                check=False,
            )

            if result.returncode != 0:
                msg = f"Execution subprocess failed (code {result.returncode}): {result.stderr}"
                raise RuntimeError(msg)

            # Read result from output file
            if not Path(temp_output_path).exists():
                msg = f"Output file not created. STDERR: {result.stderr}"
                raise ValueError(msg)

            with Path(temp_output_path).open(encoding="utf-8") as f:
                output_data = json.load(f)

            if not output_data.get("success"):
                error_msg = output_data.get("error", "Unknown execution error")
                if "traceback" in output_data:
                    error_msg += f"\nTraceback: {output_data['traceback']}"
                raise ValueError(error_msg)

            logger.info(output_data)

            return output_data.get("output", {})

        except subprocess.TimeoutExpired as e:
            msg = "Workflow execution timed out after 5 minutes"
            raise TimeoutError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Failed to parse JSON from output file: {e}"
            raise ValueError(msg) from e
        finally:
            # Clean up temporary files
            Path(temp_script_path).unlink(missing_ok=True)
            Path(temp_output_path).unlink(missing_ok=True)

    def _process(self) -> None:
        if not self.workflow_file_path:
            msg = "No workflow file specified"
            raise ValueError(msg)

        # Get the maximum length of input lists to determine how many parallel executions to run
        max_length = self._get_max_input_list_length()
        if max_length == 0:
            # No list inputs, execute once with empty input
            workflow_input = self._build_workflow_input_by_index(0)
            try:
                workflow_output = self._execute_workflow_in_subprocess(workflow_input)
                if workflow_output:
                    self._set_workflow_outputs(workflow_output)
            except Exception as e:
                logger.error("Error executing workflow: %s", str(e))
                msg = f"Workflow execution failed: {e}"
                raise ValueError(msg) from e
            return

        # Execute workflows in parallel for each list index
        try:
            # Use ThreadPoolExecutor to run workflows in parallel
            with ThreadPoolExecutor(max_workers=min(max_length, 10)) as executor:
                # Submit all workflow executions
                future_to_index = {}
                for i in range(max_length):
                    workflow_input = self._build_workflow_input_by_index(i)
                    future = executor.submit(self._execute_workflow_in_subprocess, workflow_input)
                    future_to_index[future] = i

                # Collect results in order
                results: list[dict[str, Any] | None] = [None] * max_length
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    try:
                        result = future.result()
                        results[index] = result
                    except Exception as e:
                        logger.error("Error executing workflow at index %d: %s", index, str(e))
                        results[index] = {}  # Use empty dict for failed executions

            # Aggregate all outputs into lists - use results directly to maintain order
            self._aggregate_workflow_outputs(results)

        except Exception as e:
            logger.error("Error executing parallel workflows: %s", str(e))
            msg = f"Parallel workflow execution failed: {e}"
            raise ValueError(msg) from e

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()
