import traceback
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class ExecutePython(ControlNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Add input parameters
        self.add_parameter(Parameter(
            name="python_code",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str"],
            type="str",
            default_value="# Enter your Python code here\n# Use 'input_var' to access the input variable\nresult = f'Hello from execute node! Input: {input_var}'",
            tooltip="Python code to execute. Set the 'result' variable to specify the output value. Use 'input_var' to access the input variable.",
            ui_options={
                "multiline": True,
                "placeholder_text": "# Enter your Python code here\n# Use 'input_var' to access the input variable\nresult = f'Hello from execute node! Input: {input_var}'",
                "syntax_highlighting": "python",
            },
        ))

        self.add_parameter(Parameter(
            name="enable_imports",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            type="bool",
            default_value=False,
            tooltip="Allow import statements in the Python code. WARNING: Only enable for trusted code.",
        ))

        self.add_parameter(Parameter(
            name="capture_stdout",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["bool"],
            type="bool",
            default_value=True,
            tooltip="Capture print statements and stdout output.",
        ))

        self.add_parameter(Parameter(
            name="input_variable",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            input_types=["str", "int", "float", "bool", "list", "dict"],
            type="str",
            default_value="",
            tooltip="Optional input variable that will be available as 'input_var' in your Python code.",
        ))

        # Add output parameters
        self.add_parameter(
            Parameter(
                name="result",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="The return value from the executed Python code.",
            )
        )

        self.add_parameter(
            Parameter(
                name="stdout_output",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="Any print statements or stdout output from the code execution.",
            )
        )

        self.add_parameter(
            Parameter(
                name="error_message",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="str",
                default_value="",
                tooltip="Error message if the code execution failed.",
            )
        )

        self.add_parameter(
            Parameter(
                name="execution_success",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="bool",
                default_value=True,
                tooltip="Whether the code executed successfully without errors.",
            )
        )

    def process(self) -> None:
        python_code = self.get_parameter_value("python_code")
        enable_imports = self.get_parameter_value("enable_imports")
        capture_stdout = self.get_parameter_value("capture_stdout")
        input_variable = self.get_parameter_value("input_variable")

        if not python_code.strip():
            self.parameter_output_values["result"] = ""
            self.parameter_output_values["stdout_output"] = ""
            self.parameter_output_values["error_message"] = "No code provided"
            self.parameter_output_values["execution_success"] = False

            self.set_parameter_value("result", "")
            self.set_parameter_value("stdout_output", "")
            self.set_parameter_value("error_message", "No code provided")
            self.set_parameter_value("execution_success", False)
            return

        result = None
        stdout_output = ""
        error_message = ""
        execution_success = True

        try:
            # Capture stdout if requested
            if capture_stdout:
                import io
                from contextlib import redirect_stdout

                stdout_buffer = io.StringIO()

                # Create a local namespace for execution
                local_namespace = {}
                if input_variable:
                    local_namespace["input_var"] = input_variable

                # Execute the code with stdout capture
                with redirect_stdout(stdout_buffer):
                    # Execute as statements
                    exec(python_code, {"__builtins__": __builtins__}, local_namespace)
                    # Get result from the 'result' variable if it exists
                    if "result" in local_namespace:
                        result = local_namespace["result"]

                stdout_output = stdout_buffer.getvalue()
            else:
                # Execute without stdout capture
                local_namespace = {}
                if input_variable:
                    local_namespace["input_var"] = input_variable

                # Execute as statements
                exec(python_code, {"__builtins__": __builtins__}, local_namespace)
                # Get result from the 'result' variable if it exists
                if "result" in local_namespace:
                    result = local_namespace["result"]

        except Exception as e:
            execution_success = False
            error_message = f"{type(e).__name__}: {e!s}\n\nTraceback:\n{traceback.format_exc()}"
            result = None

        # Convert result to string for output
        if result is not None:
            try:
                result_str = str(result)
            except Exception:
                result_str = repr(result)
        else:
            result_str = "No result set"

        # Set output values
        self.parameter_output_values["result"] = result_str
        self.parameter_output_values["stdout_output"] = stdout_output
        self.parameter_output_values["error_message"] = error_message
        self.parameter_output_values["execution_success"] = execution_success

        # Also set in parameter_values for get_value compatibility
        self.set_parameter_value("result", result_str)
        self.set_parameter_value("stdout_output", stdout_output)
        self.set_parameter_value("error_message", error_message)
        self.set_parameter_value("execution_success", execution_success)
