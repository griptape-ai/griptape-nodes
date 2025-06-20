from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterList, Trait
from griptape_nodes.exe_types.node_types import ControlNode
import re
from typing import Any

class CustomDataTrait(Trait):
    def __init__(self, position: int = 0, color: str = "red"):
        super().__init__()
        self.position = position
        self.color = color

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["custom_data"]

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["position"] = self.position
        data["color"] = self.color
        return data

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
                    "placeholder_text": "Enter template here. Fields to be replaced by the parameters are denoted by {field}.",
                    "custom_attribute": "my_value",  # Your custom attribute
                    "another_custom": 123  # You can add multiple custom attributes
                },
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

        # Add dict parameter for boxes
        self.add_parameter(
            Parameter(
                name="box_dict",
                tooltip="Dictionary of box parameters",
                type="dict",
                input_types=["dict"],
                output_type="dict",
                default_value={},
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "collapsible": True,
                    "collapsed": False
                }
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate parameters before the workflow runs"""
        exceptions = []
        box_dict = self.get_parameter_value("box_dict")
        if box_dict is None:
            exceptions.append(ValueError("No parameters provided"))
            return exceptions

        return exceptions if exceptions else None

    def process(self) -> None:
        """Main processing logic for the node"""
        template = self.get_parameter_value("template")
        box_dict = self.get_parameter_value("box_dict")
        if not isinstance(box_dict, dict):
            raise ValueError("Box dictionary not found")
            
        # Get all box parameters and their values
        box_params = []
        for box_name, value in box_dict.items():
            if not isinstance(value, str):
                raise ValueError(f"Box parameter {box_name} must be a string, got {type(value)}")
            # Find the position in the original template
            match = re.search(r'\{box:' + re.escape(box_name) + r'\}', template)
            if match:
                position = match.start()
                box_params.append((position, value))
        
        # Sort by position (descending) so we don't mess up positions when inserting
        box_params.sort(reverse=True)
        
        # Insert values at their positions
        output = template
        for position, value in box_params:
            output = output[:position] + value + output[position:]
        # Remove the {box:name} sequences from the output
        output = re.sub(r'\{box:[^}]+\}', '', output)
        self.parameter_output_values["output"] = output

    def before_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> Any:
        """Called before a parameter value is set on this node.
        
        Args:
            parameter: The parameter that is about to be set
            value: The value that is about to be set
            modified_parameters_set: Set of other parameter names that were modified as a result
            
        Returns:
            The value that should actually be set
        """
        # You can modify the value before it's set
        if parameter.name == "template":
            # React to template changes
            box_matches = re.finditer(r'\{box:([^}]+)\}', value)
            if box_matches:
                # Get the box dict parameter
                box_dict = self.get_parameter_by_name("box_dict")
                if isinstance(box_dict, Parameter):
                    # Create a new dict with box names as keys
                    new_dict = {}
                    for match in box_matches:
                        box_name = match.group(1)  # Get the captured group (text between {box: and })
                        if box_name not in new_dict:
                            new_dict[box_name] = ""
                    # Properly update the parameter value
                    self.set_parameter_value("box_dict", new_dict)
        # Return the value to be set (you can modify it if needed)
        return value