import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                # "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
            ],
        )

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="max_epochs",
                input_types=["int"],
                type="int",
                tooltip="max_epochs",
                default_value=4,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="learning_rate",
                input_types=["float"],
                type="float",
                tooltip="learning_rate",
                default_value=5e-4,
            )
        )

    def add_output_parameters(self) -> None:
        # TODO: Cache the output model -- only train if input parameters change
        self._node.add_parameter(
            Parameter(
                name="lora_path",
                output_type="str",
                tooltip="File path to the trained LoRA model",
                type="str",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()
    
    def get_max_epochs(self) -> int:
        return int(self._node.get_parameter_value("max_epochs"))

    def get_learning_rate(self) -> float:
        return float(self._node.get_parameter_value("learning_rate"))
    

