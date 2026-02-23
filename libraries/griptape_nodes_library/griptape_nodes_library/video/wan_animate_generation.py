from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError, FileWriteError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
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

# HTTP status code threshold for error responses
HTTP_ERROR_STATUS = 400

# Generation status constants
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCELED = "CANCELED"
STATUS_UNKNOWN = "UNKNOWN"


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

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate animated videos from images using WAN Animate models via Griptape model proxy"

        # Model selection
        self.add_parameter(
            ParameterString(
                name="model",
                default_value=MODEL_OPTIONS[0],
                tooltip="Select the WAN Animate model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )
        # Mode selection
        self.add_parameter(
            ParameterString(
                name="mode",
                default_value=MODE_OPTIONS[0],
                tooltip="Service mode: wan-std or wan-pro",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODE_OPTIONS)},
            )
        )
        # Input image URL using PublicArtifactUrlParameter
        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterImage(
                name="image_url",
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
            artifact_url_parameter=ParameterVideo(
                name="video_url",
                default_value="",
                tooltip="Reference video for motion transfer",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Video URL"},
            ),
            disclaimer_message="The WAN Animate service utilizes this URL to access the reference video for motion transfer.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # OUTPUTS
        self._output_file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="wan_animate.mp4",
        )
        self._output_file_param.add_parameter()

        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video",
                tooltip="Generated video as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
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

    async def aprocess(self) -> None:
        await self._process_generation()

    async def _process_generation(self) -> None:
        try:
            await super()._process_generation()
        finally:
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_video_url_parameter.delete_uploaded_artifact()

    async def _get_parameters(self) -> dict[str, Any]:
        # Get the original video URL before uploading to calculate duration
        video_param = self.get_parameter_value("video_url")
        original_video_url = video_param.value if hasattr(video_param, "value") else str(video_param)

        # Calculate duration from the original video (ceiling to int)
        duration = math.ceil(await get_video_duration(original_video_url))
        logger.debug("Detected video duration: %ss", duration)

        return {
            "model": self.get_parameter_value("model"),
            "mode": self.get_parameter_value("mode"),
            "image_input": self.get_parameter_value("image_url"),
            "video_input": self.get_parameter_value("video_url"),
            "duration": duration,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _get_api_model_id(self) -> str:
        return self.get_parameter_value("model") or ""

    async def _build_payload(self) -> dict[str, Any]:
        params = await self._get_parameters()

        image_url = await self._prepare_image_data_url_async(params["image_input"])
        if not image_url:
            msg = "Failed to process input image"
            raise ValueError(msg)

        video_url = await self._prepare_video_data_url_async(params["video_input"])
        if not video_url:
            msg = "Failed to process input video"
            raise ValueError(msg)

        # Build payload matching proxy expected format
        payload = {
            "input": {
                "image_url": image_url,
                "video_url": video_url,
            },
            "parameters": {
                "mode": params["mode"],
                "duration": params["duration"],
            },
        }

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        status = self._extract_status(result_json) or STATUS_UNKNOWN
        if status in {STATUS_FAILED, STATUS_CANCELED}:
            self.parameter_output_values["video"] = None
            error_details = self._extract_error_message(result_json)
            self._set_status_results(was_successful=False, result_details=error_details)
            return

        await self._handle_completion(result_json, generation_id)

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # Already a data URI — return as-is
        if image_url.startswith("data:image/"):
            return image_url

        try:
            return await File(image_url).aread_data_uri(fallback_mime="image/jpeg")
        except FileLoadError as e:
            logger.debug("%s failed to load image from %s: %s", self.name, image_url, e)
            return None

    async def _prepare_video_data_url_async(self, video_input: Any) -> str | None:
        if not video_input:
            return None

        video_url = self._coerce_video_url_or_data_uri(video_input)
        if not video_url:
            return None

        # Already a data URI — return as-is
        if video_url.startswith("data:video/"):
            return video_url

        try:
            return await File(video_url).aread_data_uri(fallback_mime="video/mp4")
        except FileLoadError as e:
            logger.debug("%s failed to load video from %s: %s", self.name, video_url, e)
            return None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        if val is None:
            return None

        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        try:
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except AttributeError:
            pass

        return None

    @staticmethod
    def _coerce_video_url_or_data_uri(val: Any) -> str | None:
        if val is None:
            return None

        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:video/")) else f"data:video/mp4;base64,{v}"

        try:
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:video/")):
                return v
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:video/") else f"data:video/mp4;base64,{b64}"
        except AttributeError:
            pass

        return None

    async def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:  # noqa: ARG002
        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        try:
            logger.debug("Downloading video bytes from provider URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            logger.debug("Failed to download video: %s", e)
            video_bytes = None

        if video_bytes:
            output_file = self._output_file_param.build_file()
            try:
                actual_path = await output_file.awrite_bytes(video_bytes)
            except FileWriteError as e:
                logger.debug("Failed to write video: %s, using provider URL", e)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not write video: {e}).",
                )
                return
            self.parameter_output_values["video"] = VideoUrlArtifact(value=actual_path, name=Path(actual_path).name)
            logger.debug("Saved video as %s", actual_path)
            self._set_status_results(
                was_successful=True,
                result_details=f"Video generated successfully and saved as {Path(actual_path).name}.",
            )
        else:
            self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_message(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        if top_level_error:
            return self._format_top_level_error(top_level_error)

        status = self._extract_status(response_json) or STATUS_UNKNOWN
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return json.loads(provider_response)
            except Exception:
                return None
        if isinstance(provider_response, dict):
            return provider_response
        return None

    def _format_provider_error(
        self, parsed_provider_response: dict[str, Any] | None, top_level_error: Any
    ) -> str | None:
        """Format error message from parsed provider response."""
        if not parsed_provider_response:
            return None

        provider_error = parsed_provider_response.get("error")
        if not provider_error:
            return None

        if isinstance(provider_error, dict):
            error_message = provider_error.get("message", "")
            details = f"{error_message}"

            if error_code := provider_error.get("code"):
                details += f"\nError Code: {error_code}"
            if error_type := provider_error.get("type"):
                details += f"\nError Type: {error_type}"
            if top_level_error:
                details = f"{top_level_error}\n\n{details}"
            return details

        error_msg = str(provider_error)
        if top_level_error:
            return f"{top_level_error}\n\nProvider error: {error_msg}"
        return f"Generation failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"Generation failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"Generation failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video"] = None

    @staticmethod
    def _extract_status(response_json: dict[str, Any] | None) -> str | None:
        if not response_json:
            return None
        task_status = response_json.get("task_status")
        if isinstance(task_status, str):
            return task_status
        return None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        results = obj.get("results")
        if isinstance(results, dict):
            video_url = results.get("video_url")
            if isinstance(video_url, str) and video_url.startswith("http"):
                return video_url
        return None
