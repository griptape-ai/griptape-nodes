import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")

QUANTIZED_FLUX_2_REPO_IDS = ["diffusers/FLUX.2-dev-bnb-4bit"]

FLUX_2_REPO_IDS = [*QUANTIZED_FLUX_2_REPO_IDS, "black-forest-labs/FLUX.2-dev"]


class Flux2PipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=FLUX_2_REPO_IDS,
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
        return diffusers.Flux2Pipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.Flux2Pipeline:
        base_repo_id, base_revision = self._model_repo_parameter.get_repo_revision()

        return diffusers.Flux2Pipeline.from_pretrained(
            pretrained_model_name_or_path=base_repo_id,
            revision=base_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

    def is_prequantized(self) -> bool:
        repo_id, _ = self._model_repo_parameter.get_repo_revision()
        return repo_id in QUANTIZED_FLUX_2_REPO_IDS
