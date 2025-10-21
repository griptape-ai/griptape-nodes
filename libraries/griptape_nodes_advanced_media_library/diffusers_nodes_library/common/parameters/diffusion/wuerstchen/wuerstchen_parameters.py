import logging

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class WuerstchenPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._prior_model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "warp-ai/wuerstchen-prior",
            ],
            parameter_name="prior_model",
            list_all_models=list_all_models,
        )
        self._decoder_model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "warp-ai/wuerstchen",
            ],
            parameter_name="decoder_model",
            list_all_models=list_all_models,
        )

    def add_input_parameters(self) -> None:
        self._prior_model_repo_parameter.add_input_parameters()
        self._decoder_model_repo_parameter.add_input_parameters()

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("prior_model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_prior_model")
        self._node.remove_parameter_element_by_name("decoder_model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_decoder_model")

    def get_config_kwargs(self) -> dict:
        return {
            "prior_model": self._node.get_parameter_value("prior_model"),
            "decoder_model": self._node.get_parameter_value("decoder_model"),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.WuerstchenCombinedPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        prior_model_errors = self._prior_model_repo_parameter.validate_before_node_run()
        if prior_model_errors:
            errors.extend(prior_model_errors)

        decoder_model_errors = self._decoder_model_repo_parameter.validate_before_node_run()
        if decoder_model_errors:
            errors.extend(decoder_model_errors)

        return errors or None

    def build_pipeline(self) -> diffusers.WuerstchenCombinedPipeline:
        prior_repo_id, prior_revision = self._prior_model_repo_parameter.get_repo_revision()
        decoder_repo_id, decoder_revision = self._decoder_model_repo_parameter.get_repo_revision()

        # Build the WuerstchenCombinedPipeline with both prior and decoder models
        return diffusers.WuerstchenCombinedPipeline.from_pretrained(
            prior_model_name_or_path=prior_repo_id,
            decoder_model_name_or_path=decoder_repo_id,
            prior_revision=prior_revision,
            decoder_revision=decoder_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )
