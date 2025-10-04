from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResultFailure,
    RunArbitraryPythonStringResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class ExecutePython(SuccessFailureNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameters
        self.add_parameter(
            Parameter(
                name="python_code",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                type="str",
                default_value="# Enter your Python code here. Assign the output to the variable 'result', and access input variables by passing a dict of their names and values'",
                tooltip="Python code to execute. Set the 'result' variable to specify the output value.",
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter your Python code here",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="input_variables",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                type="dict",
                default_value="",
                tooltip="Optional input variables that will be available as local variables in the executed code. Pass as a dictionary of names and values.",
            )
        )

        # Add output parameters
        self.add_parameter(
            Parameter(
                name="result",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="The printed value from the executed Python code.",
            )
        )
        self._create_status_parameters(
            result_details_tooltip="Details about the execute python result",
            result_details_placeholder="Details on the execution attempt will be presented here.",
        )

    def _assign_vars(self, python_code: str, input_variables: dict[str, Any]) -> str:
        # Prepare the code with input variables
        if input_variables:
            variable_assignments = []
            for var_name, var_value in input_variables.items():
                # Create safe variable assignments
                variable_assignments.append(f"{var_name} = {var_value!r}")

            # Prepend variable assignments to the user's code
            return "\n".join(variable_assignments) + "\n" + python_code
        return python_code

    def process(self) -> None:
        self._clear_execution_status()
        python_code = self.get_parameter_value("python_code")
        input_variables: dict[str, Any] = self.get_parameter_value("input_variables")

        if not python_code.strip():
            self.set_parameter_value("result", "No Python code provided for execution")
            self._set_status_results(
                was_successful=False, result_details="Failure: No Python code provided for execution"
            )
            return

        full_code = self._assign_vars(python_code, input_variables)

        # Create the request
        request = RunArbitraryPythonStringRequest(python_string=full_code)

        response = GriptapeNodes.handle_request(request)

        # Process the response
        if isinstance(response, RunArbitraryPythonStringResultFailure):
            error_output = response.python_output
            self._set_status_results(was_successful=False, result_details=f"Failure: {error_output}")
            self.set_parameter_value("result", "")
        elif not isinstance(
            response, RunArbitraryPythonStringResultSuccess
        ):  # if it's not a success either, it is some response type we don't know
            # Fallback for unexpected response type
            self._set_status_results(
                was_successful=False,
                result_details=f"Failure: Unexpected response type from RunArbitraryPythonStringRequest: {type(response)}",
            )
        elif isinstance(response, RunArbitraryPythonStringResultSuccess):
            output = response.python_output
            self.set_parameter_value("result", output)
            self._set_status_results(
                was_successful=True, result_details="The Python code executed successfully with no exceptions."
            )
