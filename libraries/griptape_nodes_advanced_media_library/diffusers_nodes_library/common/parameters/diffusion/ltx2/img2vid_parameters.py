import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")

QUANTIZED_LTX_2_I2V_REPO_IDS = ["Lightricks/LTX-2:ltx-2-19b-dev-fp8", "Lightricks/LTX-2:ltx-2-19b-dev-fp4"]

LTX_2_I2V_REPO_IDS = [*QUANTIZED_LTX_2_I2V_REPO_IDS, "Lightricks/LTX-2:ltx-2-19b-dev"]

# TODO: Remove this class once models are downloaded - temporary bypass for testing
SKIP_DOWNLOAD_CHECK = True


class LTX2I2VRepoParameter(HuggingFaceRepoParameter):
    """Temporary subclass that bypasses cache check for testing."""

    def fetch_repo_revisions(self) -> list[tuple[str, str]]:
        if SKIP_DOWNLOAD_CHECK:
            # Return all repo IDs with empty revision for testing
            return [(repo_id, "") for repo_id in self._repo_ids]
        return super().fetch_repo_revisions()


class LTX2ImageToVideoPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = LTX2I2VRepoParameter(
            node,
            repo_ids=LTX_2_I2V_REPO_IDS,
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
        return diffusers.LTXImageToVideoPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.LTXImageToVideoPipeline:
        repo_id, revision = self._model_repo_parameter.get_repo_revision()
        return diffusers.LTXImageToVideoPipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

    def is_prequantized(self) -> bool:
        repo_id, _ = self._model_repo_parameter.get_repo_revision()
        return repo_id in QUANTIZED_LTX_2_I2V_REPO_IDS
