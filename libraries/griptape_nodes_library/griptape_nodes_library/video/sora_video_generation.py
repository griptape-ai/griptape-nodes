from __future__ import annotations

import base64
import io
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact, load_pil_from_url

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger("griptape_nodes")

__all__ = ["SoraVideoGeneration"]

# Size options for different models
SIZE_OPTIONS = {
    "sora-2": ["1280x720", "720x1280"],
    "sora-2-pro": ["1280x720", "720x1280", "1024x1792", "1792x1024"],
}


class SoraVideoGeneration(GriptapeProxyNode):
    """Generate a video using Sora 2 models via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (required)
        - model (str): Model to use (default: sora-2, options: sora-2, sora-2-pro)
        - seconds (int): Clip duration in seconds (optional, options: 4, 6, 8)
        - size (str): Output resolution as widthxheight (default: 720x1280)
        - start_frame (ImageUrlArtifact): Optional starting frame image (auto-updates size if supported)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error

    Note: When a start_frame is provided, the size parameter will automatically update
    to match the image dimensions if they match a supported resolution.
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Sora 2 through Griptape Cloud model proxy"

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="sora-2",
                tooltip="Sora model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model",
                },
                traits={Options(choices=["sora-2", "sora-2-pro"])},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt describing the video to generate",
                multiline=True,
                placeholder_text="Describe the video...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )

        self.add_parameter(
            ParameterImage(
                name="start_frame",
                tooltip="Optional: Starting frame image (auto-updates size if dimensions are supported)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                clickable_file_browser=True,
                ui_options={
                    "display_name": "Start Frame",
                    "expander": True,
                },
            )
        )

        with ParameterGroup(name="Generation Settings") as video_generation_settings_group:
            # Duration in seconds
            ParameterInt(
                name="seconds",
                default_value=4,
                tooltip="Clip duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[4, 8, 12])},
                ui_options={"display_name": "Duration (seconds)"},
            )

            ParameterString(
                name="size",
                default_value="720x1280",
                tooltip="Output resolution as widthxheight (options vary by model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SIZE_OPTIONS["sora-2"])},
                ui_options={"display_name": "Size"},
            )

        self.add_node_element(video_generation_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from API (final result)",
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

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update size options based on model selection and auto-update size from start_frame."""
        if parameter.name == "model" and value in SIZE_OPTIONS:
            new_choices = SIZE_OPTIONS[value]
            current_size = self.get_parameter_value("size")

            # If current size is not in new choices, set to default
            if current_size not in new_choices:
                default_size = "720x1280" if "720x1280" in new_choices else new_choices[0]
                self._update_option_choices("size", new_choices, default_size)
            else:
                # Keep current size but update available choices
                self._update_option_choices("size", new_choices, current_size)

        elif parameter.name == "start_frame" and value:
            # Auto-update size parameter to match image dimensions if supported
            self._auto_update_size_from_image(value)

        return super().after_value_set(parameter, value)

    def _auto_update_size_from_image(self, image_value: Any) -> None:
        """Automatically update the size parameter to match the image dimensions if supported."""
        try:
            pil_image = self._load_pil_from_input(image_value)
            if not pil_image:
                return
            image_size = f"{pil_image.width}x{pil_image.height}"

            # Get available size options for current model
            current_model = self.get_parameter_value("model") or "sora-2"
            available_sizes = SIZE_OPTIONS.get(current_model, SIZE_OPTIONS["sora-2"])

            # If image size matches one of the supported sizes, update the size parameter
            if image_size in available_sizes:
                self.set_parameter_value("size", image_size)
                self._log(f"Auto-updated size to {image_size} to match start_frame dimensions")
            else:
                self._log(
                    f"Start frame size {image_size} not in supported sizes {available_sizes} for model {current_model}"
                )
        except Exception as e:
            self._log(f"Could not auto-update size from image: {e}")

    async def aprocess(self) -> None:
        await self._process_generation()

    def _get_parameters(self) -> dict[str, Any]:
        seconds_value = self.get_parameter_value("seconds")
        if isinstance(seconds_value, list):
            seconds_value = seconds_value[0] if seconds_value else None

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "sora-2",
            "seconds": seconds_value,
            "size": self.get_parameter_value("size") or "720x1280",
            "start_frame": self.get_parameter_value("start_frame"),
        }

    def _get_api_model_id(self) -> str:
        return self.get_parameter_value("model") or "sora-2"

    async def _build_payload(self) -> dict[str, Any]:
        params = self._get_parameters()

        # Build JSON payload
        json_data: dict[str, Any] = {
            "prompt": params["prompt"],
            "model": params["model"],
            "size": params["size"],
        }

        if params["seconds"]:
            json_data["seconds"] = str(params["seconds"])

        # Process and add start_frame if provided
        if params["start_frame"]:
            base64_image = self._process_start_frame(params["start_frame"], params["size"])
            if base64_image:
                json_data["input_reference"] = base64_image

        self._log(f"Submitting request to proxy model={params['model']}")
        self._log(f"JSON payload keys: {list(json_data.keys())}")
        if "input_reference" in json_data:
            self._log("Including start_frame as input_reference")

        return json_data

    async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
        # Handle binary response from proxy if returned
        if "raw_bytes" in result_json:
            self._handle_video_completion(result_json["raw_bytes"])
            return

        # Check for video URL in response
        video_url = result_json.get("video_url") or result_json.get("url")
        if isinstance(video_url, str) and video_url:
            await self._handle_video_url_completion(video_url)
            return

        # Check for error status
        status = result_json.get("status")
        if isinstance(status, str) and status.lower() in {"failed", "error"}:
            error_details = self._extract_error_message(result_json)
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details=error_details)
            return

        # Final fallback
        self.parameter_output_values["video_url"] = None
        self._set_status_results(
            was_successful=False,
            result_details="Generation completed but no video data was found in the response.",
        )

    def _process_start_frame(self, start_frame: Any, expected_size: str) -> str | None:
        """Process start_frame image: validate dimensions and encode to base64.

        Args:
            start_frame: Image artifact or None
            expected_size: Expected size as 'widthxheight' (e.g., '720x1280')

        Returns:
            Base64-encoded image string or None if no start_frame provided

        Raises:
            ValueError: If image dimensions don't match expected size
        """
        if not start_frame:
            return None

        pil_image = self._load_pil_from_input(start_frame)
        if not pil_image:
            return None

        # Parse expected dimensions
        expected_width, expected_height = map(int, expected_size.split("x"))

        # Validate dimensions
        if pil_image.width != expected_width or pil_image.height != expected_height:
            msg = (
                f"Start frame dimensions ({pil_image.width}x{pil_image.height}) must match video size ({expected_size})"
            )
            raise ValueError(msg)

        # Convert to base64
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        base64_string = base64.b64encode(image_bytes).decode("utf-8")

        return base64_string

    def _extract_error_message(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response.

        Args:
            response_json: The JSON response from the API that may contain error information

        Returns:
            A formatted error message string
        """
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        # Try to extract from provider response first (more detailed)
        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        # Fall back to top-level error
        if top_level_error:
            return self._format_top_level_error(top_level_error)

        # Final fallback
        status = response_json.get("status", "unknown")
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                import json as _json

                return _json.loads(provider_response)
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

    def _handle_video_completion(self, video_bytes: bytes) -> None:
        """Handle completion when video data is received."""
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details="Received empty video data from API.")
            return

        try:
            filename = f"sora_video_{int(time.time())}.mp4"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved video to static storage as {filename}")
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        except Exception as e:
            self._log(f"Failed to save video: {e}")
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False, result_details=f"Video generation completed but failed to save: {e}"
            )

    async def _handle_video_url_completion(self, video_url: str) -> None:
        """Handle completion when a video URL is received."""
        try:
            video_bytes = await self._download_bytes_from_url(video_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_bytes = None

        if video_bytes:
            self._handle_video_completion(video_bytes)
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _load_pil_from_input(self, image_value: Any) -> Image.Image | None:
        if isinstance(image_value, dict):
            image_value = dict_to_image_url_artifact(image_value)

        # Extract a string URL that load_pil_from_url / File can handle
        if isinstance(image_value, str):
            url = image_value
        elif isinstance(image_value, ImageUrlArtifact):
            url = image_value.value
        elif isinstance(image_value, ImageArtifact):
            url = f"data:image/png;base64,{image_value.base64}"
        else:
            return None

        if not url:
            return None

        try:
            return load_pil_from_url(url)
        except Exception as e:
            self._log(f"Failed to load image: {e}")
            return None

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
