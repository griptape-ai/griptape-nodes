from __future__ import annotations

import logging
import math
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.base_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.video_utils import get_video_duration

logger = logging.getLogger("griptape_nodes")

__all__ = ["WanAnimateGeneration"]

# Model options
MODEL_OPTIONS = [
    "wan2.2-animate-mix",
    "wan2.2-animate-move",
]

# Mode options
MODE_OPTIONS = [
    "wan-std",
    "wan-pro",
]


class WanAnimateGeneration(GriptapeProxyNode):
    """Generate animated videos from images using WAN Animate models via Griptape model proxy.

    WAN Animate models combine a source image with a reference video to create animations.
    - wan2.2-animate-mix: Combines image with reference video motion
    - wan2.2-animate-move: Animates an image based on reference video motion

    Both models support two service modes:
    - wan-std (standard): Lower cost
    - wan-pro (professional): Higher quality

    Inputs:
        - model (str): WAN Animate model to use (default: "wan2.2-animate-mix")
        - mode (str): Service mode - "wan-std" (standard) or "wan-pro" (professional)
        - image_url (ImageUrlArtifact): Source image to animate (required)
            Format: JPG, JPEG, PNG, BMP, or WEBP
            Dimensions: 200-4096 pixels (width and height), aspect ratio 1:3 to 3:1
            Size: Max 5 MB
            Content: Single person facing camera, complete face, not obstructed
        - video_url (VideoUrlArtifact): Reference video for motion (required)
            Format: MP4, AVI, or MOV
            Duration: 2-30 seconds
            Dimensions: 200-2048 pixels (width and height), aspect ratio 1:3 to 3:1
            Size: Max 200 MB
            Content: Single person facing camera, complete face, not obstructed

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - video (VideoUrlArtifact): Generated video as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate animated videos from images using WAN Animate models via Griptape model proxy"

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value=MODEL_OPTIONS[0],
                tooltip="Select the WAN Animate model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Mode selection
        self.add_parameter(
            Parameter(
                name="mode",
                input_types=["str"],
                type="str",
                default_value=MODE_OPTIONS[0],
                tooltip="Service mode: wan-std or wan-pro",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODE_OPTIONS)},
            )
        )

        # Input image URL using PublicArtifactUrlParameter
        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="image_url",
                input_types=["ImageUrlArtifact"],
                type="ImageUrlArtifact",
                default_value="",
                tooltip="Source image to animate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Image URL"},
            ),
            disclaimer_message="The WAN Animate service utilizes this URL to access the image for animation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # Reference video URL using PublicArtifactUrlParameter
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="video_url",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Reference video for motion transfer",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Video URL"},
            ),
            disclaimer_message="The WAN Animate service utilizes this URL to access the reference video for motion transfer.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Generated video as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        image_url = self.get_parameter_value("image_url")
        if not image_url:
            exceptions.append(ValueError("Image URL must be provided"))
        video_url = self.get_parameter_value("video_url")
        if not video_url:
            exceptions.append(ValueError("Video URL must be provided"))
        return exceptions if exceptions else None

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model") or "wan2.2-animate-mix"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for WAN Animate generation."""
        # Get the original video URL to calculate duration
        video_param = self.get_parameter_value("video_url")
        original_video_url = video_param.value if hasattr(video_param, "value") else str(video_param)

        # Calculate duration from the original video (ceiling to int)
        duration = math.ceil(await get_video_duration(original_video_url))
        logger.debug("Detected video duration: %ss", duration)

        # Build payload matching proxy expected format (input + parameters structure)
        payload = {
            "input": {
                "image_url": self._public_image_url_parameter.get_public_url_for_parameter(),
                "video_url": self._public_video_url_parameter.get_public_url_for_parameter(),
            },
            "parameters": {
                "mode": self.get_parameter_value("mode"),
                "duration": duration,
            },
        }

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse WAN Animate result and save generated video."""
        # Extract video URL from results.video_url
        extracted_url = self._extract_video_url(result_json)
        if not extracted_url:
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        # Download and save the video
        try:
            logger.info("Downloading video from URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            logger.error("Failed to download video: %s", e)
            video_bytes = None

        if video_bytes:
            try:
                filename = f"wan_animate_{generation_id}.mp4"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("Saved video to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                logger.error("Failed to save video: %s", e)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    async def aprocess(self) -> None:
        """Process the animation request with cleanup."""
        try:
            await super().aprocess()
        finally:
            # Cleanup uploaded artifacts
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_video_url_parameter.delete_uploaded_artifact()

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video"] = None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        """Extract video URL from WAN Animate response format (results.video_url)."""
        if not obj:
            return None
        results = obj.get("results")
        if isinstance(results, dict):
            video_url = results.get("video_url")
            if isinstance(video_url, str) and video_url.startswith("http"):
                return video_url
        return None
