import logging

import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.depthcrafter_pipeline import (
    DepthCrafterVideoDiffusionPipeline,
)
from diffusers_nodes_library.common.parameters.diffusion.depthcrafter.unet import (
    DiffusersUNetSpatioTemporalConditionModelDepthCrafter,
)
from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class DepthCrafterPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._unet_model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "tencent/DepthCrafter",
            ],
            parameter_name="unet_model",
            list_all_models=list_all_models,
        )
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "stabilityai/stable-video-diffusion-img2vid-xt",
            ],
            parameter_name="model",
            list_all_models=list_all_models,
        )

    def add_input_parameters(self) -> None:
        self._unet_model_repo_parameter.add_input_parameters()
        self._model_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._unet_model_repo_parameter.remove_input_parameters()
        self._model_repo_parameter.remove_input_parameters()

    def get_config_kwargs(self) -> dict:
        return {
            "unet_model": self._node.get_parameter_value("unet_model"),
            "model": self._node.get_parameter_value("model"),
        }

    @property
    def pipeline_class(self) -> type:
        return DepthCrafterVideoDiffusionPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        unet_model_errors = self._unet_model_repo_parameter.validate_before_node_run()
        if unet_model_errors:
            errors.extend(unet_model_errors)

        return errors or None

    def build_pipeline(self) -> DepthCrafterVideoDiffusionPipeline:
        repo_id, revision = self._model_repo_parameter.get_repo_revision()
        unet_repo_id, unet_revision = self._unet_model_repo_parameter.get_repo_revision()

        # Load the custom UNet model with float16
        unet = DiffusersUNetSpatioTemporalConditionModelDepthCrafter.from_pretrained(
            # unet_path,
            pretrained_model_name_or_path=unet_repo_id,
            revision=unet_revision,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
        )

        # Load the pipeline with float16 to match UNet dtype
        pipe = DepthCrafterVideoDiffusionPipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            revision=revision,
            torch_dtype=torch.float16,
            variant="fp16",
            use_local_files_only=True,
            unet=unet,
        )

        return pipe
