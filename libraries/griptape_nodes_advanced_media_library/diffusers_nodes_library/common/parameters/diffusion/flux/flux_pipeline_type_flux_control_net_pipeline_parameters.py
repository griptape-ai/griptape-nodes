import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipelineTypeFluxControlNetPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
                "black-forest-labs/FLUX.1-Krea-dev",
            ],
            parameter_name="model",
        )

        self._text_encoder_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "openai/clip-vit-large-patch14",
            ],
            parameter_name="text_encoder",
        )

        self._text_encoder_2_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/t5-v1_1-xxl",
            ],
            parameter_name="text_encoder_2",
        )

        self._controlnet_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "InstantX/FLUX.1-dev-Controlnet-Union",
                "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro",
                "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0",
            ],
            parameter_name="controlnet_model",
        )

    def add_input_parameters(self) -> None:
        self._model_repo_parameter.add_input_parameters()
        self._text_encoder_repo_parameter.add_input_parameters()
        self._text_encoder_2_repo_parameter.add_input_parameters()
        self._controlnet_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_text_encoder")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_text_encoder_2")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_controlnet_model")
        self._node.remove_parameter_element_by_name("text_encoder")
        self._node.remove_parameter_element_by_name("text_encoder_2")
        self._node.remove_parameter_element_by_name("controlnet_model")

    def get_config_kwargs(self) -> dict:
        return {
            "model": self._node.get_parameter_value("model"),
            "text_encoder": self._node.get_parameter_value("text_encoder"),
            "text_encoder_2": self._node.get_parameter_value("text_encoder_2"),
            "controlnet_model": self._node.get_parameter_value("controlnet_model"),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.FluxControlNetPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        text_encoder_errors = self._text_encoder_repo_parameter.validate_before_node_run()
        if text_encoder_errors:
            errors.extend(text_encoder_errors)

        text_encoder_2_errors = self._text_encoder_2_repo_parameter.validate_before_node_run()
        if text_encoder_2_errors:
            errors.extend(text_encoder_2_errors)

        controlnet_errors = self._controlnet_repo_parameter.validate_before_node_run()
        if controlnet_errors:
            errors.extend(controlnet_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.FluxControlNetPipeline:
        text_encoder_repo_id, text_encoder_revision = self._text_encoder_repo_parameter.get_repo_revision()
        text_encoder_2_repo_id, text_encoder_2_revision = self._text_encoder_2_repo_parameter.get_repo_revision()
        controlnet_repo_id, controlnet_revision = self._controlnet_repo_parameter.get_repo_revision()
        base_repo_id, base_revision = self._model_repo_parameter.get_repo_revision()

        text_encoder = transformers.CLIPTextModel.from_pretrained(
            pretrained_model_name_or_path=text_encoder_repo_id,
            revision=text_encoder_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

        text_encoder_2 = transformers.T5EncoderModel.from_pretrained(
            pretrained_model_name_or_path=text_encoder_2_repo_id,
            revision=text_encoder_2_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

        # Load ControlNet model first
        controlnet = diffusers.FluxControlNetModel.from_pretrained(
            pretrained_model_name_or_path=controlnet_repo_id,
            revision=controlnet_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/2322
        return diffusers.FluxControlNetPipeline.from_pretrained(
            pretrained_model_name_or_path=base_repo_id,
            revision=base_revision,
            text_encoder=text_encoder,
            text_encoder_2=text_encoder_2,
            controlnet=controlnet,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
