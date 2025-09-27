import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.diffusion_pipeline_type_pipeline_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class WanPipelineTypeWanPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
                "Wan-AI/Wan2.1-T2V-14B-Diffusers",
                "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
            ],
            parameter_name="model",
        )

    def add_input_parameters(self) -> None:
        self._model_repo_parameter.add_input_parameters()

        default_width, default_height = self._get_model_defaults()

        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=default_width,
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Video frame width (model-specific)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=default_height,
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Video frame height (model-specific)",
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_model")
        self._node.remove_parameter_element_by_name("width")
        self._node.remove_parameter_element_by_name("height")

    def get_config_kwargs(self) -> dict:
        return {
            "model": self._node.get_parameter_value("model"),
            "width": self.get_width(),
            "height": self.get_height(),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.WanPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []
        model_errors = self._model_repo_parameter.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        # Validate dimensions are divisible by 16
        width = self.get_width()
        height = self.get_height()
        if width % 16 != 0:
            errors.append(ValueError(f"Width ({width}) must be divisible by 16"))
        if height % 16 != 0:
            errors.append(ValueError(f"Height ({height}) must be divisible by 16"))

        return errors or None

    def build_pipeline(self) -> diffusers.WanPipeline:
        repo_id, revision = self._model_repo_parameter.get_repo_revision()
        return diffusers.WanPipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update width and height when model selection changes."""
        if parameter.name == "model" and isinstance(value, str):
            repo_id, _ = self._model_repo_parameter._key_to_repo_revision(value)
            recommended_width, recommended_height = self._get_model_defaults(repo_id)

            # Update dimensions
            current_width = self._node.get_parameter_value("width")
            current_height = self._node.get_parameter_value("height")

            if current_width != recommended_width:
                self._node.set_parameter_value("width", recommended_width)

            if current_height != recommended_height:
                self._node.set_parameter_value("height", recommended_height)

    def _get_model_defaults(self, repo_id: str | None = None) -> tuple[int, int]:
        """Get default width and height for a specific model or the default model."""
        if repo_id is None:
            available_models = self._model_repo_parameter.fetch_repo_revisions()
            if not available_models:
                return 832, 480  # Default to 832x480 if no models are available
            repo_id = available_models[0][0]

        match repo_id:
            case "Wan-AI/Wan2.1-T2V-1.3B-Diffusers":
                return 832, 480  # 1.3B model - lighter computational requirements
            case "Wan-AI/Wan2.1-T2V-14B-Diffusers":
                return 1280, 720  # 14B model - same resolution but higher quality
            case "Wan-AI/Wan2.2-T2V-A14B-Diffusers":
                return 1280, 720  # 14B model - same resolution but higher quality
            case "Wan-AI/Wan2.2-TI2V-5B-Diffusers":
                return 1280, 704  # 5B model - 720p resolution but lighter computational requirements.
            case _:
                msg = f"Unsupported model repo_id: {repo_id}."
                raise ValueError(msg)

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))
