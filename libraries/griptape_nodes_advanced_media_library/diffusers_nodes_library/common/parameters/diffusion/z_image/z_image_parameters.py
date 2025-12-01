import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


Z_IMAGE_REPO_IDS = ["Tongyi-MAI/Z-Image-Turbo"]


class ZImagePipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=Z_IMAGE_REPO_IDS,
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
        return diffusers.ZImagePipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.ZImagePipeline:
        base_repo_id, base_revision = self._model_repo_parameter.get_repo_revision()

        return diffusers.ZImagePipeline.from_pretrained(
            pretrained_model_name_or_path=base_repo_id,
            revision=base_revision,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=False,
            local_files_only=True,
        )

    def supports_layerwise_casting(self) -> bool:
        """ZImage's TimestepEmbedder checks weight dtype before calling the module.

        This is incompatible with layerwise casting hooks that cast weights during
        the forward pass.
        """
        return False
