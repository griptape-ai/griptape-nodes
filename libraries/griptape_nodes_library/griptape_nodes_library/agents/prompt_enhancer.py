from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from typing import Any
import os
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent
from griptape_nodes.traits.options import Options

class PromptEnhancer(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        
        # Initialize prompt templates as "" - will be loaded in validate_before_workflow_run
        self.prompt_improver_prompt = ""
        self.basic_prompt = ""

        # Input prompt parameter
        self.add_parameter(
            Parameter(
                name="input_prompt",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="The original prompt to enhance",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter your original prompt here..."
                }
            )
        )

        # Enhancement options
        self.add_parameter(
            Parameter(
                name="enhancement_type",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Type of enhancement or change to apply",
                default_value="Fix clarity",
                allowed_modes={ParameterMode.PROPERTY}
            )
        )

        # Common prompt issues
        self.add_parameter(
            Parameter(
                name="common_issue",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Common issue to address in the prompt",
                default_value="No Common Issues",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Common Issue",
                }
            )
        )
        # Use custom prompt structure toggle
        self.add_parameter(
            Parameter(
                name="use_rdce_prompt_structure",
                type="bool",
                input_types=["bool"],
                output_type="bool",
                tooltip="Enable custom prompt structure enhancement",
                default_value=True,
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Use RDCE Prompt Structure"
                }
            )
        )
        # Include example toggle
        self.add_parameter(
            Parameter(
                name="include_example",
                type="bool",
                input_types=["bool"],
                output_type="bool",
                tooltip="Include an example in the enhanced prompt",
                default_value=True,
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Include Example"
                }
            )
        )

        # Execute enhanced prompt toggle
        self.add_parameter(
            Parameter(
                name="execute_enhanced_prompt",
                type="bool",
                input_types=["bool"],
                output_type="bool",
                tooltip="Execute the enhanced prompt and return the result",
                default_value=False,
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Execute Enhanced Prompt"
                }
            )
        )

        # Output for executed enhanced prompt
        self.add_parameter(
            Parameter(
                name="output_prompt",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Response from GPT-4",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "GPT-4 response will appear here..."
                }
            )
        )
        self.add_parameter(
            Parameter(
                name="executed_output_prompt",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Result of executing the enhanced prompt",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "GPT-4 response will appear here..."
                }
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validate parameters before the workflow runs"""
        exceptions = []
        
        # Load prompt templates
        script_dir = os.path.dirname(os.path.abspath(__file__))

        for template_name in ["prompt_improver_prompt", "basic_prompt"]:
            file_path = os.path.join(script_dir, f"{template_name}.txt")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    setattr(self, template_name, f.read())
            except FileNotFoundError:
                exceptions.append(FileNotFoundError(f"Template file not found: {file_path}"))
            except Exception as e:
                exceptions.append(Exception(f"Error loading {template_name}: {str(e)}"))

        
        # Validate input prompt
        if not self.get_parameter_value("input_prompt") or self.get_parameter_value("input_prompt").strip() == "":
            exceptions.append(ValueError("Input prompt cannot be empty"))
        
        return exceptions if exceptions else None

    def process(self) -> None:
        """Main processing logic for the node"""
        input_prompt = self.get_parameter_value("input_prompt")
        enhancement_type = self.get_parameter_value("enhancement_type")
        common_issue = self.get_parameter_value("common_issue")
        use_rdce_prompt_structure = self.get_parameter_value("use_rdce_prompt_structure")
        include_example = self.get_parameter_value("include_example")
        execute_enhanced_prompt = self.get_parameter_value("execute_enhanced_prompt")
        enhanced_prompt = self._enhance_prompt(input_prompt, enhancement_type, common_issue, use_rdce_prompt_structure, include_example)
        self.set_parameter_value("output_prompt", enhanced_prompt)
        if execute_enhanced_prompt:
            executed_result = self._ask_gpt4_directly(enhanced_prompt)
            self.set_parameter_value("executed_output_prompt", executed_result)
        else:
            self.set_parameter_value("executed_output_prompt", None)

    def _ask_gpt4_directly(self, prompt: str) -> str:
        """Ask GPT-4 directly using the enhanced prompt."""
        try:
            # Get API key and model
            api_key = self.get_config_value("Griptape", "GT_CLOUD_API_KEY")
            model = "gpt-4.1"
            
            # Create prompt driver
            prompt_driver = GriptapeCloudPromptDriver(
                model=model,
                api_key=api_key,
                stream=False  # Set to True for streaming
            )
            
            # Create agent
            agent = Agent(prompt_driver=prompt_driver)
            
            # Send prompt and get response
            result = agent.run(prompt)
            return result.output.value
            
        except Exception as e:
            return f"Error getting GPT-4 response: {str(e)}"

    def _enhance_prompt(self, prompt: str, enhancement_type: str, common_issue: str, use_rdce_prompt_structure: bool, include_example: bool = True) -> str:
        """Enhance the prompt based on the specified type"""
        template = self.prompt_improver_prompt if use_rdce_prompt_structure else self.basic_prompt
        include_example_str = "" if include_example else "not"
        return self._ask_gpt4_directly(template.format(criteria=enhancement_type, prompt=prompt, common_issue=common_issue, include_example=include_example_str))