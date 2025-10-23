import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode, *, list_all_models: bool = False):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "rhymes-ai/Allegro",
                "rhymes-ai/Allegro-T2V-40x720P",
            ],
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
        return diffusers.AllegroPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update num_frames when model selection changes."""

    def _get_model_defaults(self, repo_id: str | None = None) -> int:
        """Get default num_frames for a specific model or the default model."""
        if repo_id is None:
            available_models = self._model_repo_parameter.fetch_repo_revisions()
            if not available_models:
                return 40  # 40x360P variant
            repo_id = available_models[0][0]

        """Get recommended num_frames for a specific model."""
        match repo_id:
            case "rhymes-ai/Allegro":
                return 88  # Default Allegro model
            case "rhymes-ai/Allegro-T2V-40x360P":
                return 40  # 40x360P variant
            case "rhymes-ai/Allegro-T2V-40x720P":
                return 40  # 40x720P variant
            case _:
                msg = f"Unsupported model: {repo_id}"
                raise ValueError(msg)

    def build_pipeline(self) -> diffusers.AllegroPipeline:
        base_repo_id, base_revision = self._model_repo_parameter.get_repo_revision()

        # Build the pipeline with proper VAE setup
        pipe = diffusers.AllegroPipeline.from_pretrained(
            pretrained_model_name_or_path=base_repo_id,
            revision=base_revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

        # Enable VAE tiling for memory efficiency
        pipe.vae.enable_tiling()

        # Set VAE to float32 for precision
        pipe.vae = pipe.vae.to(torch.float32)

        return pipe
