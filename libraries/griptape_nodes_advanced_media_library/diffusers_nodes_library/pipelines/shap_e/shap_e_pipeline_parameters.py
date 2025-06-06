import logging
from typing import Any

import diffusers  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("diffusers_nodes_library")


class ShapEPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "openai/shap-e",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="frame_size",
                default_value=64,
                input_types=["int"],
                type="int",
                tooltip="frame size for rendering",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=15.0,
                input_types=["float"],
                type="float",
                tooltip="guidance_scale",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="mesh",
                type="str",
                allowed_modes=set([ParameterMode.OUTPUT]),
                tooltip="Generated 3D mesh data",
            )
        )

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter("num_inference_steps").value

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter("prompt").value,
            "num_inference_steps": self._node.get_parameter("num_inference_steps").value,
            "guidance_scale": self._node.get_parameter("guidance_scale").value,
            "frame_size": self._node.get_parameter("frame_size").value,
            "generator": self._seed_parameter.get_generator(),
        }
        return kwargs

    def publish_output_mesh_preview_placeholder(self) -> None:
        placeholder_mesh = "# Placeholder mesh data"
        self._node.set_parameter("mesh", placeholder_mesh)

    def publish_output_mesh(self, output) -> None:
        if hasattr(output, "images") and output.images:
            mesh_data = str(output.images[0])
        else:
            mesh_data = str(output)
        self._node.set_parameter("mesh", mesh_data)

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._huggingface_repo_parameter.after_value_set(parameter, value, modified_parameters_set)

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        errors.extend(self._huggingface_repo_parameter.validate_before_node_run())
        return errors

    def preprocess(self) -> None:
        self._huggingface_repo_parameter.preprocess()
        self._seed_parameter.preprocess()