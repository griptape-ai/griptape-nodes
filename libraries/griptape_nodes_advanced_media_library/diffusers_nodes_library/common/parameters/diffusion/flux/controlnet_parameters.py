import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
import transformers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class FluxControlNetPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
                "black-forest-labs/FLUX.1-Krea-dev",
            ],
            parameter_name="model",
            list_all_models=list_all_models,
        )

        self._text_encoder_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "openai/clip-vit-large-patch14",
            ],
            parameter_name="text_encoder",
            list_all_models=list_all_models,
        )

        self._text_encoder_2_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/t5-v1_1-xxl",
            ],
            parameter_name="text_encoder_2",
            list_all_models=list_all_models,
        )

        self._controlnet_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "InstantX/FLUX.1-dev-Controlnet-Union",
                "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro",
                "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0",
            ],
            parameter_name="controlnet_model",
            list_all_models=list_all_models,
        )

    def add_input_parameters(self) -> None:
        self._controlnet_repo_parameter.add_input_parameters()
        self._model_repo_parameter.add_input_parameters()
        self._text_encoder_repo_parameter.add_input_parameters()
        self._text_encoder_2_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._controlnet_repo_parameter.remove_input_parameters()
        self._model_repo_parameter.remove_input_parameters()
        self._text_encoder_repo_parameter.remove_input_parameters()
        self._text_encoder_2_repo_parameter.remove_input_parameters()

    def get_config_kwargs(self) -> dict:
        return {
            "controlnet_model": self._node.get_parameter_value("controlnet_model"),
            "model": self._node.get_parameter_value("model"),
            "text_encoder": self._node.get_parameter_value("text_encoder"),
            "text_encoder_2": self._node.get_parameter_value("text_encoder_2"),
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
