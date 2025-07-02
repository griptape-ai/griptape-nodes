import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
import torch  # type: ignore[reportMissingImports]
from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]
from PIL import Image  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import HuggingFaceRepoParameter
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class WanVideoToVideoPipelineParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
                "Wan-AI/Wan2.1-T2V-14B-Diffusers",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

        default_width, default_height = self._get_model_defaults()

        self._node.add_parameter(
            Parameter(
                name="input_video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Input video for video-to-video generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Prompt for video generation",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Negative prompt (optional)",
            )
        )
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
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps (20 is quick, 50+ for quality)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=5.0,
                input_types=["float"],
                type="float",
                tooltip="CFG guidance scale (higher = more prompt adherence)",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="strength",
                default_value=0.8,
                input_types=["float"],
                type="float",
                tooltip="Higher strength leads to more differences between original image and generated video.",
            )
        )
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="Generated video",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        # Validate input video is provided
        input_video = self.get_input_video()
        if input_video is None:
            errors = errors or []
            errors.append(ValueError("Input video is required for video-to-video generation"))

        # Validate dimensions are divisible by 16
        width = self.get_width()
        height = self.get_height()
        if width % 16 != 0:
            errors = errors or []
            errors.append(ValueError(f"Width ({width}) must be divisible by 16"))
        if height % 16 != 0:
            errors = errors or []
            errors.append(ValueError(f"Height ({height}) must be divisible by 16"))

        return errors or None

    def _get_model_defaults(self, repo_id: str | None = None) -> tuple[int, int]:
        """Get default width, height for a specific model or the default model."""
        if repo_id is None:
            available_models = self._huggingface_repo_parameter.fetch_repo_revisions()
            if not available_models:
                return 832, 480  # Default to 832x480 if no models are available
            repo_id = available_models[0][0]

        """Get recommended width, height for a specific model."""
        match repo_id:
            case "Wan-AI/Wan2.1-T2V-1.3B-Diffusers":
                return 832, 480  # 1.3B model - lighter computational requirements
            case "Wan-AI/Wan2.1-T2V-14B-Diffusers":
                return 1280, 720  # 14B model - same resolution but higher quality
            case _:
                msg = f"Unsupported model repo_id: {repo_id}."
                raise ValueError(msg)

    def _update_dimensions_for_model(self, parameter: Parameter, value: Any) -> None:
        """Update width, height when model selection changes."""
        if parameter.name == "model" and isinstance(value, str):
            repo_id, _ = self._huggingface_repo_parameter._key_to_repo_revision(value)
            recommended_width, recommended_height = self._get_model_defaults(repo_id)

            # Update dimensions
            current_width = self._node.get_parameter_value("width")
            current_height = self._node.get_parameter_value("height")

            if current_width != recommended_width:
                self._node.set_parameter_value("width", recommended_width)

            if current_height != recommended_height:
                self._node.set_parameter_value("height", recommended_height)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)
        self._update_dimensions_for_model(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_input_video(self) -> Any:
        return self._node.get_parameter_value("input_video")

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def get_strength(self) -> float:
        return float(self._node.get_parameter_value("strength"))

    def _video_artifact_to_pil_frames(self, video_artifact: VideoUrlArtifact) -> list[Image.Image]:
        """Convert a VideoUrlArtifact to a list of PIL Image frames."""
        if video_artifact is None:
            return []

        # Use diffusers loading utilities to convert video URL to frames
        return diffusers.utils.load_video(video_artifact.value)

    def get_pipe_kwargs(self) -> dict:
        return {
            "video": self._video_artifact_to_pil_frames(self.get_input_video()),
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "width": self.get_width(),
            "height": self.get_height(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "strength": self.get_strength(),
            "generator": self._seed_parameter.get_generator(),
            "output_type": "pil",
        }

    def latents_to_video_mp4(self, pipe: diffusers.WanVideoToVideoPipeline, latents: Any) -> Path:
        """Convert latents to video frames and export as MP4 file."""
        # First convert latents to frames using the VAE
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            # Convert latents to video frames using VAE decode
            latents = latents.to(pipe.vae.dtype)

            # Apply latents normalization as per the WAN pipeline
            latents_mean = (
                torch.tensor(pipe.vae.config.latents_mean)
                .view(1, pipe.vae.config.z_dim, 1, 1, 1)
                .to(latents.device, latents.dtype)
            )
            latents_std = 1.0 / torch.tensor(pipe.vae.config.latents_std).view(1, pipe.vae.config.z_dim, 1, 1, 1).to(
                latents.device, latents.dtype
            )
            latents = latents / latents_std + latents_mean

            # Decode latents to video using VAE
            video = pipe.vae.decode(latents, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="pil")[0]

            # Export frames to video
            diffusers.utils.export_to_video(frames, str(temp_file), fps=16)
        except Exception:
            # Clean up on error
            if temp_file.exists():
                temp_file.unlink()
            raise
        else:
            return temp_file

    def publish_output_video_preview_latents(self, pipe: diffusers.WanVideoToVideoPipeline, latents: Any) -> None:
        """Publish a preview video from latents during generation."""
        preview_video_path = None
        try:
            preview_video_path = self.latents_to_video_mp4(pipe, latents)
            filename = f"preview_{uuid.uuid4()}.mp4"
            url = GriptapeNodes.StaticFilesManager().save_static_file(preview_video_path.read_bytes(), filename)
            self._node.publish_update_to_parameter("output_video", VideoUrlArtifact(url))
        except Exception as e:
            logger.warning("Failed to generate video preview from latents: %s", e)
        finally:
            # Clean up temporary file
            if preview_video_path is not None and preview_video_path.exists():
                preview_video_path.unlink()

    def publish_output_video(self, video_path: Path) -> None:
        filename = f"{uuid.uuid4()}{video_path.suffix}"
        url = GriptapeNodes.StaticFilesManager().save_static_file(video_path.read_bytes(), filename)
        self._node.parameter_output_values["output_video"] = VideoUrlArtifact(url)
