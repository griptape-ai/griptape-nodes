import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_variant_parameter import (
    HuggingFaceRepoVariantParameter,
)

logger = logging.getLogger("diffusers_nodes_library")

LTX_2_REPO_ID = "Lightricks/LTX-2"
LTX_2_VARIANTS = ["ltx-2-19b-dev-fp8", "ltx-2-19b-dev-fp4", "ltx-2-19b-dev"]
QUANTIZED_LTX_2_VARIANTS = ["ltx-2-19b-dev-fp8", "ltx-2-19b-dev-fp4"]


class LTX2PipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):  # noqa: ARG002
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoVariantParameter(
            node,
            repo_id=LTX_2_REPO_ID,
            variants=LTX_2_VARIANTS,
            parameter_name="model",
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
        return diffusers.LTX2Pipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.LTX2Pipeline:
        repo_id, variant, revision = self._model_repo_parameter.get_repo_variant_revision()

        return diffusers.LTX2Pipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            transformer_id=variant,
            revision=revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

    def is_prequantized(self) -> bool:
        _, variant, _ = self._model_repo_parameter.get_repo_variant_revision()
        return variant in QUANTIZED_LTX_2_VARIANTS
