from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import FileWriteError
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingMotionControl"]

# Constants
MAX_PROMPT_LENGTH = 2500


class KlingMotionControl(GriptapeProxyNode):
    """Generate a video using Kling Motion Control via Griptape Cloud model proxy.

    The Motion Control model transfers character actions from a reference video to a reference image,
    creating a new video where the character in the image performs the actions from the video.

    Inputs:
        - prompt (str): Text prompt for additional guidance (optional, max 2500 chars)
        - reference_image (ImageArtifact|ImageUrlArtifact): Reference image with character (required)
        - reference_video (VideoUrlArtifact): Reference video with actions to transfer (required)
        - keep_original_sound (bool): Keep original video sound (default: True)
        - character_orientation (str): Character orientation - image or video (required)
        - mode (str): Video generation mode - std (Standard) or pro (Professional) (required)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved video URL
        - kling_video_id (str): The video ID from Kling AI
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value="",
                tooltip="Optional text prompt for additional motion guidance (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Optional: Add additional control with a text prompt...",
                    "display_name": "prompt",
                },
            )
        )

        # Image Input Group
        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterImage(
                name="reference_image",
                tooltip="Reference image with character (required). Supports .jpg/.jpeg/.png, max 10MB.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ),
            disclaimer_message="The Kling Motion Control service utilizes this URL to access the image for generation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # Use PublicArtifactUrlParameter for video upload handling
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterVideo(
                name="reference_video",
                tooltip="Reference video with actions to transfer (required). Supports .mp4/.mov, max 100MB.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ),
            disclaimer_message="The Kling Motion Control service utilizes this URL to access the video for generation.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterBool(
                name="keep_original_sound",
                default_value=True,
                tooltip="Keep original video sound",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "keep original sound"},
            )
            ParameterString(
                name="character_orientation",
                default_value="video",
                tooltip="Character orientation: 'image' matches image orientation (max 10s video), 'video' matches video orientation (max 30s video)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["image", "video"])},
                ui_options={"display_name": "character orientation"},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode: 'std' (Standard - cost-effective), 'pro' (Professional - higher quality)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
        self.add_node_element(gen_settings_group)

        # OUTPUTS
        self._output_file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="kling_motion.mp4",
        )
        self._output_file_param.add_parameter()

        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video_url",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The video ID from Kling AI",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The Kling AI video ID",
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    async def aprocess(self) -> None:
        try:
            await super().aprocess()
        finally:
            # Always cleanup uploaded artifacts
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_video_url_parameter.delete_uploaded_artifact()

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Returns the static model ID for Kling Motion Control.
        """
        return "kling:motion-control"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Kling Motion Control API.

        Returns:
            dict: The request payload (model field excluded, handled by base class)
        """
        # Get image parameter - use PublicArtifactUrlParameter to get public URL
        reference_image_param = self.get_parameter_value("reference_image")
        image_url = None
        if reference_image_param:
            image_url = self._public_image_url_parameter.get_public_url_for_parameter()

        # Get video parameter - use PublicArtifactUrlParameter to get public URL
        reference_video_param = self.get_parameter_value("reference_video")
        video_url = None
        if reference_video_param:
            video_url = self._public_video_url_parameter.get_public_url_for_parameter()

        keep_sound = self.get_parameter_value("keep_original_sound")
        if keep_sound is None:
            keep_sound = True

        prompt = (self.get_parameter_value("prompt") or "").strip()
        character_orientation = self.get_parameter_value("character_orientation") or "video"
        mode = self.get_parameter_value("mode") or "pro"
        keep_original_sound = "yes" if keep_sound else "no"

        payload: dict[str, Any] = {
            "image_url": image_url,
            "video_url": video_url,
            "keep_original_sound": keep_original_sound,
            "character_orientation": character_orientation,
            "mode": mode,
        }

        # Add optional prompt if provided
        if prompt:
            payload["prompt"] = prompt

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:  # noqa: ARG002
        """Parse the result and set output parameters.

        Expected structure: {"data": {"task_result": {"videos": [{"url": "...", "id": "..."}]}}}
        """
        data = result_json.get("data", {})
        task_result = data.get("task_result", {})
        videos = task_result.get("videos", [])

        if not videos or not isinstance(videos, list) or len(videos) == 0:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no videos found in response.",
            )
            return

        video_info = videos[0]
        download_url = video_info.get("url")
        video_id = video_info.get("id")

        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download URL found in response.",
            )
            return

        # Set kling_video_id output parameter
        if video_id:
            self.parameter_output_values["kling_video_id"] = video_id
            logger.info("Video ID: %s", video_id)

        # Download and save video
        try:
            logger.info("%s downloading video from provider URL", self.name)
            video_bytes = await self._download_bytes_from_url(download_url)
        except Exception as e:
            logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            output_file = self._output_file_param.build_file()
            try:
                actual_path = await output_file.awrite_bytes(video_bytes)
            except FileWriteError as e:
                self._log(f"Failed to write video: {e}")
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save video: {e}).",
                )
                return
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=actual_path, name=Path(actual_path).name)
            logger.info("%s saved video as %s", self.name, actual_path)
            self._set_status_results(
                was_successful=True,
                result_details=f"Video generated successfully and saved as {Path(actual_path).name}.",
            )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _set_safe_defaults(self) -> None:
        """Clear output parameters on error."""
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["kling_video_id"] = ""

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        # Get parameter values
        prompt = self.get_parameter_value("prompt") or ""
        reference_image_param = self.get_parameter_value("reference_image")
        reference_video_param = self.get_parameter_value("reference_video")

        # Validate prompt length
        if prompt and len(prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(prompt)} characters)."
                )
            )

        # Validate required image
        if not reference_image_param:
            exceptions.append(ValueError(f"{self.name} requires a reference image."))

        # Validate required video
        if not reference_video_param:
            exceptions.append(ValueError(f"{self.name} requires a reference video."))

        return exceptions if exceptions else None
