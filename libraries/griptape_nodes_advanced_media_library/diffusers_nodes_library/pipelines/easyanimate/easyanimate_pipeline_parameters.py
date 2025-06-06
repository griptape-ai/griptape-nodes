import functools
from typing import Any

from diffusers_nodes_library.common.parameters.huggingface_model_parameter import HuggingfaceModelParameter  # type: ignore[reportMissingImports]
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import ControlNode


class EasyanimatePipelineParameters:
    def __init__(self, node: ControlNode):
        self.node = node

    def add_input_parameters(self) -> None:
        HuggingfaceModelParameter(self.node).add_input_parameters()
        SeedParameter(self.node).add_input_parameters()

        self.node.add_input_parameter("prompt", default_value="A beautiful sunset over mountains")
        self.node.add_input_parameter("negative_prompt", default_value="")
        self.node.add_input_parameter("num_inference_steps", default_value=20)
        self.node.add_input_parameter("guidance_scale", default_value=7.5)
        self.node.add_input_parameter("num_frames", default_value=16)
        self.node.add_input_parameter("height", default_value=512)
        self.node.add_input_parameter("width", default_value=512)

    def add_output_parameters(self) -> None:
        self.node.add_output_parameter("output_video")

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        pass

    def validate_before_node_run(self) -> list[Exception]:
        errors = []
        return errors

    def preprocess(self) -> None:
        pass

    def get_repo_revision(self) -> tuple[str, str]:
        return HuggingfaceModelParameter(self.node).get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return self.node.get_input_parameter_value("num_inference_steps")

    def get_pipe_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "prompt": self.node.get_input_parameter_value("prompt"),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.node.get_input_parameter_value("guidance_scale"),
            "num_frames": self.node.get_input_parameter_value("num_frames"),
            "height": self.node.get_input_parameter_value("height"),
            "width": self.node.get_input_parameter_value("width"),
            "generator": SeedParameter(self.node).get_generator(),
        }

        negative_prompt = self.node.get_input_parameter_value("negative_prompt")
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        return kwargs

    def publish_output_video_preview_placeholder(self) -> None:
        self.node.set_output_parameter_value("output_video", "Generating video with EasyAnimate...")

    def publish_output_video(self, video_frames) -> None:
        self.node.set_output_parameter_value("output_video", video_frames)