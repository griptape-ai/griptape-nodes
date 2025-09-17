import logging
from typing import Any

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class FluxModelParameters:
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
        self._node.add_parameter(
            Parameter(
                name="text_encoder",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder",
                default_value="openai/clip-vit-large-patch14",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="text_encoder_2",
                input_types=["str"],
                type="str",
                allowed_modes=set(),
                tooltip="text_encoder_2",
                default_value="google/t5-v1_1-xxl",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()
        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        return

    def preprocess(self) -> None:
        return

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()
