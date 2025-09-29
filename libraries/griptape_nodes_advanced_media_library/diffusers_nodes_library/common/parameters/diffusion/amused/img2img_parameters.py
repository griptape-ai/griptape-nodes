import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.diffusion.pipeline_type_parameters import (
    DiffusionPipelineTypePipelineParameters,
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class AmusedImg2ImgPipelineParameters(DiffusionPipelineTypePipelineParameters):
    def __init__(self, node: BaseNode):
        super().__init__(node)
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "amused/amused-256",
                "amused/amused-512",
            ],
            parameter_name="model",
        )

    def add_input_parameters(self) -> None:
        self._model_repo_parameter.add_input_parameters()

        # Add input_image parameter for img2img
        self._node.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="Input image to transform",
            )
        )

    def remove_input_parameters(self) -> None:
        self._node.remove_parameter_element_by_name("model")
        self._node.remove_parameter_element_by_name("huggingface_repo_parameter_message_model")
        self._node.remove_parameter_element_by_name("input_image")

    def get_config_kwargs(self) -> dict:
        return {
            "model": self._node.get_parameter_value("model"),
        }

    @property
    def pipeline_class(self) -> type:
        return diffusers.AmusedImg2ImgPipeline

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._model_repo_parameter.validate_before_node_run()
        return errors or None

    def build_pipeline(self) -> diffusers.AmusedImg2ImgPipeline:
        repo_id, revision = self._model_repo_parameter.get_repo_revision()
        return diffusers.AmusedImg2ImgPipeline.from_pretrained(
            pretrained_model_name_or_path=repo_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
            local_files_only=True,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Auto-set width and height based on selected model for dimension-dependent parameters
        if parameter.name == "model":
            model = str(value)
            if "256" in model:
                # Set dimensions to 256x256 for 256 models
                if self._node.get_parameter_by_name("width"):
                    self._node.set_parameter_value("width", 256)
                if self._node.get_parameter_by_name("height"):
                    self._node.set_parameter_value("height", 256)
            elif "512" in model:
                # Set dimensions to 512x512 for 512 models
                if self._node.get_parameter_by_name("width"):
                    self._node.set_parameter_value("width", 512)
                if self._node.get_parameter_by_name("height"):
                    self._node.set_parameter_value("height", 512)
