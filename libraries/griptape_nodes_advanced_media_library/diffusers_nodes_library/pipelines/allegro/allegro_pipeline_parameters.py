import logging
import uuid
from pathlib import Path
from typing import Any

from griptape.artifacts import ImageUrlArtifact
from griptape_nodes.traits.options import Options
import diffusers  # type: ignore[reportMissingImports]
import PIL.Image
from diffusers_nodes_library.common.utils.ui_option_utils import update_ui_option_hide  # type: ignore[reportMissingImports]
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




class AllegroPipelineParameters:
    image_output_format_choices = ["gif"]
    video_output_format_choices = ["mp4"]
    output_format_choices = [*video_output_format_choices, *image_output_format_choices]
    default_output_format = output_format_choices[0]

    def __init__(self, node: ControlNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(node, ["rhymes-ai/Allegro"])

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()
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
                default_value=100,
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
                default_value=88,
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
        self._node.add_parameter(
            Parameter(
                name="output_format",
                default_value=self.default_output_format,
                input_types=["str"],
                type="str",
                traits={Options(choices=self.output_format_choices)},
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                tooltip="output_format",
            )
        )

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the extended video segment.",
                ui_options={"placeholder_text": "", "hide": True},
            )
        )
        self._node.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="URL of the extended video segment.",
                ui_options={"placeholder_text": "", "hide": True},
            )

        )
        self.set_output_format(self.default_output_format)
        

    def set_output_format(self, output_format: str) -> set[str]:
        is_video_format = output_format in self.video_output_format_choices
        # Notes since this _simple_ boolean logic seems so hard for my brain:
        # 1. Hide output_image if output_format is a video format.
        update_ui_option_hide(self._node, "output_image", hide=is_video_format)
        # 2. Do not hide output_video if output_format is a video format.
        update_ui_option_hide(self._node, "output_video", hide=not is_video_format)
        return {"output_video", "output_image"}

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_height(self) -> int | None:
        height = self._node.get_parameter_value("height")
        if height is not None:
            return int(height)
        return None

    def get_width(self) -> int | None:
        width = self._node.get_parameter_value("width")
        if width is not None:
            return int(width)
        return None

    def get_eta(self) -> float:
        return float(self._node.get_parameter_value("eta"))

    def get_generator(self) -> torch.Generator:
        seed = self._node.get_parameter_value("seed")
        generator = torch.Generator("cpu")
        if seed is not None:
            generator = generator.manual_seed(seed)
        return generator
    
    def get_output_format(self) -> str:
        return self._node.get_parameter_value("output_format")

    def get_pipe_kwargs(self) -> dict:
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "num_frames": self.get_num_frames(),
            "eta": self.get_eta(),
            "generator": self.get_generator(),
        }

    def publish_output_preview_placeholder(self) -> None:
        width = self.get_width() or 512  # Guess a square output if not specified
        height = self.get_height() or 512  # Guess a square output if not specified
        # Immediately set a preview placeholder image to make it react quickly and adjust
        # the size of the image preview on the node.
        preview_placeholder_image = PIL.Image.new("RGB", (width, height), color="black")
        self._node.publish_update_to_parameter("output_video", pil_to_image_artifact(preview_placeholder_image))

    def publish_output_preview(self, pipe: diffusers.AllegroPipeline, latents: Any, fps: int) -> None:
        num_frames = self.get_num_frames() or pipe.transformer.config.sample_frames * pipe.vae_scale_factor_temporal
        width = self.get_width() or pipe.transformer.config.sample_height * pipe.vae_scale_factor_spatial
        height = self.get_height() or pipe.transformer.config.sample_width * pipe.vae_scale_factor_spatial

        latents = latents.to(pipe.vae.dtype)
        video = pipe.decode_latents(latents)
        video = video[:, :, :num_frames, :height, :width]
        video = pipe.video_processor.postprocess_video(video=video, output_type="pil")[0]

        print(type(video))
        print(video)

        match self.get_output_format():
            case "gif":
                image_artifact = self.frames_to_gif_image_url_artifact(video, fps=fps)
                self._node.publish_update_to_parameter("output_image", image_artifact)
            case "mp4":
                video_artifact = self.frames_to_mp4_video_url_artifact(video, fps=fps)
                self._node.publish_update_to_parameter("output_video", video_artifact)
            case _:
                raise ValueError(f"Unsupported output format: {self.get_output_format()}")

    def publish_output_video(self, video: Any, fps: int) -> None:
        match self.get_output_format():
            case "gif":
                image_artifact = self.frames_to_gif_image_url_artifact(video, fps=fps)
                self._node.parameter_output_values["output_image"] = image_artifact
            case "mp4":
                video_artifact = self.frames_to_mp4_video_url_artifact(video, fps=fps)
                self._node.parameter_output_values["output_video"] = video_artifact
            case _:
                raise ValueError(f"Unsupported output format: {self.get_output_format()}")

    def frames_to_gif_image_url_artifact(self, video: Any, fps: int) -> ImageUrlArtifact:
        gif_path = Path(diffusers.utils.export_to_gif(video, fps=fps))
        gif_bytes = gif_path.read_bytes()
        gif_filename = f"{uuid.uuid4()}{gif_path.suffix}"
        gif_url = GriptapeNodes.StaticFilesManager().save_static_file(gif_bytes, gif_filename)
        return ImageUrlArtifact(gif_url)
    
    def frames_to_mp4_video_url_artifact(self, video: Any, fps: int) -> VideoUrlArtifact:
        video_path = Path(diffusers.utils.export_to_video(video, fps=fps))
        video_bytes = video_path.read_bytes()
        video_filename = f"{uuid.uuid4()}{video_path.suffix}"
        video_url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, video_filename)
        return VideoUrlArtifact(video_url)
