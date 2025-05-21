import logging
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from PIL.Image import Image
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

import uuid
from griptape.artifacts import UrlArtifact

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


def upload_and_get_local_file_path(path: Path) -> str:
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    filename = f"{uuid.uuid4()}{path.suffix}"
    url = GriptapeNodes.StaticFilesManager().save_static_file(path.read_bytes(), filename)
    config_manager = GriptapeNodes.ConfigManager()
    static_dir = config_manager.workspace_path / config_manager.merged_config["static_files_directory"]
    return str(static_dir / filename)

class TrainFluxLoraParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-dev",
            ],
        )

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        # resolutio
        self._node.add_parameter(
            Parameter(
                name="resolution",
                input_types=["int"],
                type="int",
                tooltip="resolution",
                default_value=512,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="learning_rate",
                input_types=["float"],
                type="float",
                tooltip="learning_rate",
                default_value=1e-4,
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_train_epochs",
                input_types=["int"],
                type="int",
                tooltip="num_train_epochs",
                default_value=1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="max_train_steps",
                input_types=["int"],
                type="int",
                tooltip="max_train_steps",
                default_value=1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="validation_prompt",
                input_types=["str"],
                type="str",
                tooltip="validation_prompt",
                default_value="a photo of a cat",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

    def add_output_parameters(self) -> None:
        # TODO: Cache the output model -- only train if input parameters change
        self._node.add_parameter(
            Parameter(
                name="lora_path",
                output_type="str",
                tooltip="the trained LoRA model",
                type="str",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()
    
    def get_resolution(self) -> int:
        return int(self._node.get_parameter_value("resolution"))
    
    def get_learning_rate(self) -> float:
        return float(self._node.get_parameter_value("learning_rate"))
    
    def get_num_train_epochs(self) -> int:
        return int(self._node.get_parameter_value("num_train_epochs"))
    
    def get_max_train_steps(self) -> int:
        return int(self._node.get_parameter_value("max_train_steps"))
    
    def get_validation_prompt(self) -> str:
        return str(self._node.get_parameter_value("validation_prompt"))
    
    def publish_lora_output(self, lora_safetensors_path: Path) -> None:
        self._node.parameter_output_values["lora_path"] = upload_and_get_local_file_path(lora_safetensors_path)