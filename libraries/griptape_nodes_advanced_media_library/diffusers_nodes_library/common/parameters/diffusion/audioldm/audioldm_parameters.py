import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AudioldmPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "cvssp/audioldm-s-full-v2",
                "cvssp/audioldm-s-full",
                "cvssp/audioldm-m-full",
                "cvssp/audioldm-l-full",
            ],
            parameter_name="model",
        )

    def add_input_parameters(self) -> None:
        self._model_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_model")

    def get_config_kwargs(self) -> dict:
        return {
            "model": self._node.get_parameter_value("model"),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.AudioLDMPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._model_repo_parameter.validate_before_node_run()
        return errors or None

    def build_pipeline(self) -> diffusers.AudioLDMPipeline:
        repo_id, revision = self._model_repo_parameter.get_repo_revision()
        return diffusers.AudioLDMPipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
