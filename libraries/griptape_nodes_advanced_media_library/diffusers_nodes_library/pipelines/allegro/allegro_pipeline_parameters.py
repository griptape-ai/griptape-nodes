import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

import diffusers  # type: ignore[reportMissingImports]
from artifact_utils.video_url_artifact import VideoUrlArtifact  # type: ignore[reportMissingImports]

from diffusers_nodes_library.common.parameters.huggingface_repo_parameter import (
    HuggingFaceRepoParameter,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.common.parameters.seed_parameter import SeedParameter  # type: ignore[reportMissingImports]
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore[reportMissingImports]

logger = logging.getLogger("diffusers_nodes_library")


class AllegroPipelineParameters:
    """Handles all Allegro pipeline related parameters for the AllegroPipeline node."""

    def __init__(self, node: BaseNode):
        self._node = node
        # By default we expose the canonical Allegro model on the Hub. Additional fine-tunes can be added later.
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "rhymes-ai/Allegro",
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1482
                # "rhymes-ai/Allegro-T2V-40x360P",
                "rhymes-ai/Allegro-T2V-40x720P",
            ],
        )
        self._seed_parameter = SeedParameter(node)

    # -------------------------------------------------------------------------
    # Parameter registration helpers
    # -------------------------------------------------------------------------

    def add_input_parameters(self) -> None:
        """Register all input parameters on the parent node."""
        self._huggingface_repo_parameter.add_input_parameters()

        default_width, default_height, default_num_frames = self._get_model_defaults()

        self._node.add_parameter(
            Parameter(
                name="prompt",
                default_value="",
                input_types=["str"],
                type="str",
                tooltip="Prompt",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="negative_prompt",
                default_value="nsfw, lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
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
                tooltip="Video frame width",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="height",
                default_value=default_height,
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Video frame height",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_frames",
                default_value=default_num_frames,
                input_types=["int"],
                type="int",
                allowed_modes=set(),
                tooltip="Number of frames to generate",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="num_inference_steps",
                default_value=20,
                input_types=["int"],
                type="int",
                tooltip="Number of denoising steps, 20 is quick, 100 ideal but slow",
            )
        )
        self._node.add_parameter(
            Parameter(
                name="guidance_scale",
                default_value=7.5,
                input_types=["float"],
                type="float",
                tooltip="CFG guidance scale",
            )
        )

        # Seed helpers are standard across pipelines.
        self._seed_parameter.add_input_parameters()

    def add_output_parameters(self) -> None:
        """Register output parameters (currently only the final video URL)."""
        self._node.add_parameter(
            Parameter(
                name="output_video",
                output_type="VideoUrlArtifact",
                tooltip="The generated video clip",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    # -------------------------------------------------------------------------
    # Validation & lifecycle hooks
    # -------------------------------------------------------------------------

    def validate_before_node_run(self) -> list[Exception] | None:
        errors = self._huggingface_repo_parameter.validate_before_node_run()

        # Validate dimensions are divisible by 8
        width = self.get_width()
        height = self.get_height()
        if width % 8 != 0:
            errors = errors or []
            errors.append(ValueError(f"Width ({width}) must be divisible by 8"))
        if height % 8 != 0:
            errors = errors or []
            errors.append(ValueError(f"Height ({height}) must be divisible by 8"))

        return errors or None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._seed_parameter.after_value_set(parameter, value)
        self._update_dimensions_for_model(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    # -------------------------------------------------------------------------
    # Convenience getters
    # -------------------------------------------------------------------------

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def get_prompt(self) -> str:
        return self._node.get_parameter_value("prompt")

    def get_negative_prompt(self) -> str:
        return self._node.get_parameter_value("negative_prompt")

    def get_width(self) -> int:
        return int(self._node.get_parameter_value("width"))

    def get_height(self) -> int:
        return int(self._node.get_parameter_value("height"))

    def get_num_frames(self) -> int:
        return int(self._node.get_parameter_value("num_frames"))

    def get_num_inference_steps(self) -> int:
        return int(self._node.get_parameter_value("num_inference_steps"))

    def get_guidance_scale(self) -> float:
        return float(self._node.get_parameter_value("guidance_scale"))

    def _get_model_defaults(self, repo_id: str | None = None) -> tuple[int, int, int]:
        """Get default width, height, and num_frames for a specific model or the default model."""
        if repo_id is None:
            available_models = self._huggingface_repo_parameter.fetch_repo_revisions()
            if not available_models:
                return 640, 368, 40  # 40x360P variant
            repo_id = available_models[0][0]

        """Get recommended width and height for a specific model."""
        match repo_id:
            case "rhymes-ai/Allegro":
                return 1280, 720, 88  # Default Allegro model
            case "rhymes-ai/Allegro-T2V-40x360P":
                return 640, 368, 40  # 40x360P variant
            case "rhymes-ai/Allegro-T2V-40x720P":
                return 1280, 720, 40  # 40x720P variant
            case _:
                msg = f"Unsupported model: {repo_id}"
                raise ValueError(msg)

    def _update_dimensions_for_model(self, parameter: Parameter, value: Any) -> None:
        """Update width and height when model selection changes."""
        if parameter.name == "model" and isinstance(value, str):
            repo_id, _ = self._huggingface_repo_parameter._key_to_repo_revision(value)
            recommended_width, recommended_height, num_frames = self._get_model_defaults(repo_id)

            # Update dimensions
            current_width = self._node.get_parameter_value("width")
            current_height = self._node.get_parameter_value("height")
            current_num_frames = self._node.get_parameter_value("num_frames")

            if current_width != recommended_width:
                self._node.set_parameter_value("width", recommended_width)

            if current_height != recommended_height:
                self._node.set_parameter_value("height", recommended_height)

            if current_num_frames != num_frames:
                self._node.set_parameter_value("num_frames", num_frames)

    def get_pipe_kwargs(self) -> dict:
        """Return a dictionary of keyword arguments to pass to the Allegro pipeline."""
        return {
            "prompt": self.get_prompt(),
            "negative_prompt": self.get_negative_prompt(),
            "num_frames": self.get_num_frames(),
            "height": self.get_height(),
            "width": self.get_width(),
            "num_inference_steps": self.get_num_inference_steps(),
            "guidance_scale": self.get_guidance_scale(),
            "generator": self._seed_parameter.get_generator(),
            "output_type": "pil",
        }

    def latents_to_video_mp4(self, pipe: diffusers.AllegroPipeline, latents: Any) -> Path:
        """Convert latents to video frames and export as MP4 file."""
        num_frames = self.get_num_frames()
        width = self.get_width()
        height = self.get_height()

        # First convert latents to frames using the VAE
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file_obj:
            temp_file = Path(temp_file_obj.name)

        try:
            latents = latents.to(pipe.vae.dtype)
            frames = pipe.decode_latents(latents)
            frames = frames[:, :, :num_frames, :height, :width]
            frames = pipe.video_processor.postprocess_video(video=frames, output_type="pil")[0]

            # Export frames to video
            diffusers.utils.export_to_video(frames, str(temp_file), fps=15)
        except Exception:
            # Clean up on error
            if temp_file.exists():
                temp_file.unlink()
            raise
        else:
            return temp_file

    def publish_output_video_preview_latents(self, pipe: diffusers.AllegroPipeline, latents: Any) -> None:
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
