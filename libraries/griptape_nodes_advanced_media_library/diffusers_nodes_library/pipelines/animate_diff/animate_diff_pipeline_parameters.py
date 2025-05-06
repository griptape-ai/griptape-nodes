import logging
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
import torch  # type: ignore[reportMissingImports]
from pillow_nodes_library.utils import pil_to_image_artifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.artifacts.video_url_artifact import (
    VideoUrlArtifact,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class AnimateDiffPipelineParameters:
    def __init__(self, node: ControlNode):
        self._node = node
        self._motion_adapter_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=["guoyww/animatediff-motion-adapter-v1-5-2"],
            parameter_name="motion_adapter",
        )
        self._model_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=["SG161222/Realistic_Vision_V5.1_noVAE"],
            parameter_name="model",
        )

    def add_input_parameters(self) -> None:
        self._motion_adapter_repo_parameter.add_input_parameters()
        self._model_repo_parameter.add_input_parameters()
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="optional negative_prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=25,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_inference_steps",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="guidance_scale",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=16,
                input_types=["int"],
                type="int",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="num_frames",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="width",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="eta",
                default_value=0.0,
                input_types=["float"],
                type="float",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="eta",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="seed",
                default_value=None,
                input_types=["int", "None"],
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="seed",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",  # Hint for UI
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the extended video segment.",
                ui_options={"placeholder_text": "", "is_full_width": True},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="output_gif",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",  # Hint for UI
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the extended video segment.",
                ui_options={"placeholder_text": "", "is_full_width": True},
            )
        )

    def get_motion_adapter_repo_revision(self) -> tuple[str, str]:
        return self._motion_adapter_repo_parameter.get_repo_revision()

    def get_model_repo_revision(self) -> tuple[str, str]:
        return self._model_repo_parameter.get_repo_revision()

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_pipe_kwargs(self) -> dict:
        prompt = self._node.parameter_values["prompt"]
        negative_prompt = self._node.parameter_values["negative_prompt"]
        width = self._node.get_parameter_value("width")
        if width is not None:
            width = int(width)
        height = self._node.get_parameter_value("height")
        if height is not None:
            height = int(height)
        num_inference_steps = int(self._node.parameter_values["num_inference_steps"])
        guidance_scale = float(self._node.parameter_values["guidance_scale"])
        num_frames = int(self._node.parameter_values["num_frames"])
        eta = float(self._node.parameter_values["eta"])
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)

        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "num_frames": num_frames,
            "eta": eta,
            "generator": generator,
        }

    def publish_output_image_preview_placeholder(self) -> None:
        width = int(self._node.parameter_values["width"])
        height = int(self._node.parameter_values["height"])
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_image", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_video(self, video_mystery_format: Any, fps: int) -> None:
        self.publish_output_video_mp4(video_mystery_format, fps)
        self.publish_output_video_gif(video_mystery_format, fps)

    def publish_output_video_mp4(self, video_mystery_format: Any, fps: int) -> None:
        video_path = Path(diffusers.utils.export_to_video(video_mystery_format, fps=fps))
        video_bytes = video_path.read_bytes()
        video_filename = f"{uuid.uuid4()}{video_path.suffix}"
        video_url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, video_filename)
        video_artifact = VideoUrlArtifact(video_url)

        self._node.set_parameter_value("output_video", video_artifact)
        self._node.parameter_output_values["output_video"] = video_artifact

    def publish_output_video_gif(self, video_mystery_format: Any, fps: int) -> None:
        gif_path = Path(diffusers.utils.export_to_gif(video_mystery_format, fps=fps))
        gif_bytes = gif_path.read_bytes()
        gif_filename = f"{uuid.uuid4()}{gif_path.suffix}"
        gif_url = GriptapeNodes.StaticFilesManager().save_static_file(gif_bytes, gif_filename)
        gif_artifact = VideoUrlArtifact(gif_url)

        self._node.set_parameter_value("output_gif", gif_artifact)
        self._node.parameter_output_values["output_gif"] = gif_artifact
