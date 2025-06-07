import logging
from typing import Any

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
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Generated 3D mesh data",
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = []

        huggingface_errors = self._huggingface_repo_parameter.validate_before_node_run()
        if huggingface_errors:
            errors.extend(huggingface_errors)

        # Validate input image
        input_image = self._node.get_parameter_value("input_image")
        if input_image is None:
            errors.append(ValueError("Input image is required"))

        return errors if errors else None

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        self._seed_parameter.after_value_set(parameter, value, modified_parameters_set)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str | None]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self._node.get_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self._node.get_parameter_value("prompt"),
            "num_inference_steps": self._node.get_parameter_value("num_inference_steps"),
            "guidance_scale": self._node.get_parameter_value("guidance_scale"),
            "frame_size": self._node.get_parameter_value("frame_size"),
            "generator": self._seed_parameter.get_generator(),
        }
        return kwargs

    def publish_output_mesh_preview_placeholder(self) -> None:
        placeholder_mesh = "# Placeholder mesh data"
        self._node.publish_update_to_parameter("mesh", placeholder_mesh)

    def publish_output_mesh(self, output: Any) -> None:
        if hasattr(output, "images") and output.images:
            mesh_data = str(output.images[0])
        else:
            mesh_data = str(output)
        self._node.parameter_output_values["mesh"] = mesh_data
