from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterList
from griptape_nodes.exe_types.node_types import ControlNode
import re
class Template(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # 1. Add Parameters
        # Basic input parameter example
        self.add_parameter(
            Parameter(
                name="template",
                type="str",  # Python type
                input_types=["str"],  # Accepted input types
                output_type="str",  # Output type for connections
                tooltip="Copy template here",  # UI tooltip
                default_value="",  # Default value
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},  # How parameter can be used
                ui_options={
                    "multiline": True,  # UI display options
                    "placeholder_text": "Enter template here. Fields to be replaced by the parameters are denoted by {field}."
                }
            )
        )
        self.add_parameter(
            Parameter(
            name="template_parameters",
            input_types=["dict"],
            tooltip="Dict of parameters for template",
            default_value=None,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
         )
    )
                # Output parameter example
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Output from the node",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "multiline": True,  # UI display options
                    "placeholder_text": "Prompt output here..."
                }
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate parameters before the workflow runs"""
        exceptions = []
        param_list = self.get_parameter_value("template_parameters")
        if param_list is None:
            exceptions.append(ValueError("No parameters provided"))
            return exceptions

        return exceptions if exceptions else None

    def process(self) -> None:
        """Main processing logic for the node"""
        # Get template value to validate
        template = self.get_parameter_value("template")
        # Add parameter for each template variable found
        param_dict = self.get_parameter_value("template_parameters")
        output = ""
        # Set output value
        if output == "":
            try:
                output = template.format(**param_dict)
            except Exception as e:
                if isinstance(e, KeyError):
                    output = (f"Although {e} seems to be in the template, it's not found in the parameters you provided.")
                    raise KeyError(output)
                else:
                    output = (f"An error occurred: {e}. \nPlease check your template and parameters.")
                    raise ValueError(output)
        self.parameter_output_values["output"] = output