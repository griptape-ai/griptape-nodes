import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.utils.torch_utils import get_best_device
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")

GLM_IMAGE_REPO_IDS = [
    "zai-org/GLM-Image",
]


class GlmImagePipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=GLM_IMAGE_REPO_IDS,
            parameter_name="model",
            list_all_models=list_all_models,
        )

    def add_input_parameters(self) -> None:
        self._model_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._model_repo_parameter.remove_input_parameters()

    def get_config_kwargs(self) -> dict:
        return {
            "model": self._node.get_parameter_value("model"),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.GlmImagePipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        if errors:
            return errors
        return None

    def requires_device_map(self) -> bool:
        """GLM-Image requires device_map to properly load vision_language_encoder."""
        return True

    def build_pipeline(self) -> diffusers.GlmImagePipeline:
        base_repo_id, base_revision = self._model_repo_parameter.get_repo_revision()
        device = get_best_device()

        # GLM-Image requires device_map to properly load the vision_language_encoder
        # component. Without it, meta tensors remain which cause errors during i2i.
        # See: https://huggingface.co/docs/diffusers/main/api/pipelines/glm_image
        return diffusers.GlmImagePipeline.from_pretrained(
            pretrained_model_name_or_path=base_repo_id,
            revision=base_revision,
            torch_dtype=torch.bfloat16,
            device_map=device.type,
            local_files_only=True,
        )
