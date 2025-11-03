import logging

from diffusers_nodes_library.common.parameters.file_path_parameter import FilePathParameter
from diffusers_nodes_library.pipelines.flux.flux_pipeline_parameters import (
    FluxPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.lora.flux_lora_parameters import (  # type: ignore[reportMissingImports]
    FluxLoraParameters,  # type: ignore[reportMissingImports],  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import DeprecationMessage, NodeMessageResult, Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload

logger = logging.getLogger("diffusers_nodes_library")


class FluxLoraFromFile(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.migrate_message = DeprecationMessage(
            value="This node is being deprecated.\nPlease use the LoadLoRA node from the Griptape Advanced Media Library.",
            button_text="Create LoadLoRA Node",
            migrate_function=self._migrate,
        )
        self.add_node_element(self.migrate_message)

        self.flux_params = FluxPipelineParameters(self)
        self.lora_file_path_params = FilePathParameter(
            self, file_types=[".safetensors", ".pt", ".bin", ".json", ".lora"]
        )
        self.lora_weight_and_output_params = FluxLoraParameters(self)
        self.lora_file_path_params.add_input_parameters()
        self.lora_weight_and_output_params.add_input_parameters()
        self.lora_weight_and_output_params.add_output_parameters()
        self.add_parameter(
            Parameter(
                name="trigger_phrase",
                default_value="",
                type="str",
                output_type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="a phrase that must be included in the prompt in order to trigger the lora",
            )
        )

    def _migrate(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult | None:  # noqa: ARG002
        # Create the new node positioned relative to this one
        new_node_name = f"{self.name}_migrated"

        # Create the new node positioned above this one
        new_node_result = cmd.create_node_relative_to(
            reference_node_name=self.name,
            new_node_type="LoadLoRA",
            new_node_name=new_node_name,
            specific_library_name="Griptape Nodes Advanced Media Library",
            offset_side="top_right",
            offset_y=-50,  # Negative offset to go UP from the reference node's top-left corner
            swap=True,
            match_size=True,
        )

        # Extract the node name from the result
        if isinstance(new_node_result, str):
            new_node = new_node_result
        else:
            # If create_node_relative_to failed, new_node_result is the error result
            logger.error("Failed to create node: %s", new_node_result)
            return None

        # Migrate executions
        cmd.migrate_parameter(self.name, new_node, "exec_in", "exec_in")
        cmd.migrate_parameter(self.name, new_node, "exec_out", "exec_out")

        # Migrate file path parameters
        cmd.migrate_parameter(self.name, new_node, "file_path", "file_path")
        cmd.migrate_parameter(self.name, new_node, "use_default_lora_path", "use_default_lora_path")
        cmd.migrate_parameter(self.name, new_node, "default_lora_path", "default_lora_path")

        # Migrate lora weight and output parameters
        cmd.migrate_parameter(self.name, new_node, "weight", "weight")
        cmd.migrate_parameter(self.name, new_node, "loras", "loras")

        # Migrate trigger phrase parameter
        cmd.migrate_parameter(self.name, new_node, "trigger_phrase", "trigger_phrase")

        return None

    def process(self) -> None:
        self.lora_file_path_params.validate_parameter_values()
        lora_path = str(self.lora_file_path_params.get_file_path())
        lora_weight = self.lora_weight_and_output_params.get_weight()
        self.lora_weight_and_output_params.set_output_lora({lora_path: lora_weight})
