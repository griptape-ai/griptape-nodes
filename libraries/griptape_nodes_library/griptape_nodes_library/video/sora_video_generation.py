from __future__ import annotations

import base64
import io
import logging
from contextlib import suppress
from typing import Any

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.base_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact, load_pil_from_url

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

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error

    Note: When a start_frame is provided, the size parameter will automatically update
    to match the image dimensions if they match a supported resolution.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Sora 2 through Griptape Cloud model proxy"

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the video to generate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "Prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
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
            Parameter(
                name="seconds",
                input_types=["int"],
                type="int",
                default_value=4,
                tooltip="Clip duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[4, 6, 8])},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="720x1280",
                tooltip="Output resolution as widthxheight (options vary by model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SIZE_OPTIONS["sora-2"])},
                ui_options={"display_name": "Size"},
            )
        )

        self.add_parameter(
            Parameter(
                name="start_frame",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageUrlArtifact",
                tooltip="Optional: Starting frame image (auto-updates size if dimensions are supported)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Start Frame",
                    "clickable_file_browser": True,
                    "expander": True,
                },
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
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
            # Convert to ImageUrlArtifact if needed
            if isinstance(image_value, dict):
                image_value = dict_to_image_url_artifact(image_value)

            if not hasattr(image_value, "value") or not image_value.value:
                return

            # Load PIL image to get dimensions
            pil_image = load_pil_from_url(image_value.value)
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

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model") or "sora-2"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Sora video generation."""
        seconds_value = self.get_parameter_value("seconds")
        if isinstance(seconds_value, list):
            seconds_value = seconds_value[0] if seconds_value else None

        size = self.get_parameter_value("size") or "720x1280"
        start_frame = self.get_parameter_value("start_frame")

        payload = {
            "prompt": self.get_parameter_value("prompt") or "",
            "size": size,
        }

        if seconds_value:
            payload["seconds"] = str(seconds_value)

        # Process and add start_frame if provided
        if start_frame:
            base64_image = self._process_start_frame(start_frame, size)
            if base64_image:
                payload["input_reference"] = base64_image

        return payload

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

        # Convert to ImageUrlArtifact if needed
        if isinstance(start_frame, dict):
            start_frame = dict_to_image_url_artifact(start_frame)

        if not hasattr(start_frame, "value") or not start_frame.value:
            return None

        # Load PIL image
        pil_image = load_pil_from_url(start_frame.value)

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

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse Sora result and save generated video."""
        # Check if we have video_bytes directly (legacy format)
        video_bytes = result_json.get("video_bytes")
        if video_bytes:
            await self._save_video_from_bytes(video_bytes, generation_id)
            return

        # Otherwise, try to extract video URL from result
        extracted_url = self._extract_video_url(result_json)
        if not extracted_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video data was found in the response.",
            )
            return

        # Download and save the video
        try:
            self._log("Downloading video bytes from provider URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            msg = f"Failed to download video: {e}"
            self._log(msg)
            video_bytes = None

        if video_bytes:
            await self._save_video_from_bytes(video_bytes, generation_id)
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    async def _save_video_from_bytes(self, video_bytes: bytes, generation_id: str) -> None:
        """Save video bytes to static storage."""
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details="Received empty video data from API.")
            return

        try:
            filename = f"sora_video_{generation_id}.mp4"
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

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from failed generation response."""
        # Try to extract from provider response (Sora-specific pattern)

        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))
        if parsed_provider_response:
            provider_error = parsed_provider_response.get("error")
            if provider_error:
                top_level_error = response_json.get("error")
                provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
                if provider_error_msg:
                    return provider_error_msg

        # Fall back to standard error extraction
        return super()._extract_error_message(response_json)

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

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL asynchronously."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        """Extract video URL from result object."""
        if not obj:
            return None
        if "video" in obj:
            video_obj = obj.get("video")
            if isinstance(video_obj, dict):
                url = video_obj.get("url")
                if isinstance(url, str):
                    return url
        return None
