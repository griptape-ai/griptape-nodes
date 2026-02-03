from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXImageToVideoGeneration"]

# Model mapping from display names to API model IDs
MODEL_MAPPING = {
    "LTX 2 Pro": "ltx-2-pro",
    "LTX 2 Fast": "ltx-2-fast",
}

# Camera motion options
CAMERA_MOTION_OPTIONS = [
    "static",
    "dolly_in",
    "dolly_out",
    "dolly_left",
    "dolly_right",
    "jib_up",
    "jib_down",
]


class LTXImageToVideoGeneration(GriptapeProxyNode):
    """Generate a video from an image using LTX AI models via Griptape Cloud model proxy.

    Inputs:
        - image (ImageArtifact|ImageUrlArtifact|str): Input image (required, base64 data URI format)
        - prompt (str): Text prompt for video generation (required)
        - model (str): Model to use (LTX 2 Pro or LTX 2 Fast)
        - resolution (str): Video resolution (1920x1080, 2560x1440, or 3840x2160)
        - duration (int): Video length in seconds
        - fps (int): Frames per second (default: 25)
        - camera_motion (str): Camera movement type (default: static)
        - generate_audio (bool): Generate audio with the video (default: true)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    DEFAULT_MAX_ATTEMPTS = 240

    # Model capability definitions
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "ltx-2-fast": {
            "resolutions": {
                "1920x1080": {
                    "fps": {25: [6, 8, 10, 12, 14, 16, 18, 20], 50: [6, 8, 10]},
                },
                "2560x1440": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "3840x2160": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
            }
        },
        "ltx-2-pro": {
            "resolutions": {
                "1920x1080": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "2560x1440": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
                "3840x2160": {
                    "fps": {25: [6, 8, 10], 50: [6, 8, 10]},
                },
            }
        },
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="LTX 2 Fast",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["LTX 2 Pro", "LTX 2 Fast"])},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                },
            )
        )

        self.add_parameter(
            ParameterImage(
                name="image",
                tooltip="Input image for video generation (required). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterString(
                name="resolution",
                default_value="1920x1080",
                tooltip="Video resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["1920x1080", "2560x1440", "3840x2160"])},
            )

            ParameterInt(
                name="duration",
                default_value=6,
                tooltip="Video length in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[6, 8, 10, 12, 14, 16, 18, 20])},
            )

            ParameterInt(
                name="fps",
                default_value=25,
                tooltip="Frames per second",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[25, 50])},
            )

            ParameterString(
                name="camera_motion",
                default_value="static",
                tooltip="Camera movement type",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=CAMERA_MOTION_OPTIONS)},
            )

            ParameterBool(
                name="generate_audio",
                default_value=True,
                tooltip="Generate audio with the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(gen_settings_group)

        # OUTPUTS
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

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        self._update_parameter_visibility_for_model("LTX 2 Fast")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        # Update parameter options when model, resolution, or fps changes
        if parameter.name in ("model", "resolution", "fps"):
            model_name = self.get_parameter_value("model") or "LTX 2 Fast"
            self._update_parameter_visibility_for_model(model_name)

    def _update_parameter_visibility_for_model(self, model_name: str) -> None:
        """Update parameter visibility and options based on selected model."""
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-fast")
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})

        # Get available resolutions
        available_resolutions = list(capabilities.get("resolutions", {}).keys())

        # Update resolution options
        resolution_param = self.get_parameter_by_name("resolution")
        if resolution_param and available_resolutions:
            current_resolution = self.get_parameter_value("resolution")
            if current_resolution not in available_resolutions:
                self.set_parameter_value("resolution", available_resolutions[0])

        # Update duration options dynamically based on model, resolution, and fps
        duration_param = self.get_parameter_by_name("duration")
        if duration_param:
            current_resolution = self.get_parameter_value("resolution") or "1920x1080"
            current_fps = self.get_parameter_value("fps") or 25
            resolution_config = capabilities.get("resolutions", {}).get(current_resolution, {})
            fps_config = resolution_config.get("fps", {})
            available_durations = fps_config.get(current_fps, [6, 8, 10])

            # Remove existing Options trait and add new one with updated choices
            existing_traits = duration_param.find_elements_by_type(Options)
            if existing_traits:
                duration_param.remove_trait(trait_type=existing_traits[0])

            # Add new Options trait with updated choices
            duration_param.add_trait(Options(choices=available_durations))

            # Validate current duration
            current_duration = self.get_parameter_value("duration")
            if current_duration not in available_durations:
                self.set_parameter_value("duration", available_durations[0])

    async def _process_generation(self) -> None:
        self._clear_execution_status()
        logger.info("%s starting video generation", self.name)

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._handle_api_key_validation_error(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        result = await self._submit_and_poll(headers)
        if not result:
            return

        generation_id, status_response = result
        self.parameter_output_values["provider_response"] = status_response

        async with httpx.AsyncClient() as client:
            result_json = await self._fetch_generation_result(generation_id, headers, client)
            if not result_json:
                return

            try:
                await self._parse_result(result_json, generation_id)
            except Exception as e:
                self._handle_result_parsing_error(e)

    async def _get_parameters_async(self) -> dict[str, Any]:
        """Get and process all parameters, including image conversion."""
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "LTX 2 Fast",
            "image_uri": await self._prepare_image_data_url_async(self.get_parameter_value("image")),
            "resolution": self.get_parameter_value("resolution") or "1920x1080",
            "duration": self.get_parameter_value("duration") or 6,
            "fps": self.get_parameter_value("fps") or 25,
            "camera_motion": self.get_parameter_value("camera_motion") or "static",
            "generate_audio": self.get_parameter_value("generate_audio")
            if self.get_parameter_value("generate_audio") is not None
            else True,
        }

    def _get_api_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "LTX 2 Fast"
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-fast")
        return f"{model_id}:image-to-video"

    def _validate_model_params(self, params: dict[str, Any]) -> str | None:
        """Validate that the model-resolution-fps-duration combination is supported."""
        model_display_name = params["model"]
        model_id = MODEL_MAPPING.get(model_display_name, "ltx-2-fast")
        resolution = params["resolution"]
        fps = params["fps"]
        duration = params["duration"]

        capabilities = self.MODEL_CAPABILITIES.get(model_id)
        if not capabilities:
            return f"{self.name}: Unknown model '{model_display_name}'"

        resolution_config = capabilities.get("resolutions", {}).get(resolution)
        if not resolution_config:
            valid_resolutions = list(capabilities.get("resolutions", {}).keys())
            return (
                f"{self.name}: Model {model_display_name} does not support resolution '{resolution}'. "
                f"Valid resolutions: {', '.join(valid_resolutions)}"
            )

        fps_config = resolution_config.get("fps", {})
        supported_durations = fps_config.get(fps)
        if supported_durations is None:
            valid_fps = list(fps_config.keys())
            return (
                f"{self.name}: Model {model_display_name} does not support {fps} FPS at resolution {resolution}. "
                f"Valid FPS values: {', '.join(map(str, valid_fps))}"
            )

        if duration not in supported_durations:
            return (
                f"{self.name}: Model {model_display_name} does not support duration {duration}s "
                f"at resolution {resolution} and {fps} FPS. "
                f"Valid durations: {', '.join(map(str, supported_durations))}"
            )

        return None

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        """Convert image input to a base64 data URL."""
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # If it's already a data URL, return it
        if image_url.startswith("data:image/"):
            return image_url

        # If it's an external URL, download and convert to data URL
        if image_url.startswith(("http://", "https://")):
            return await self._inline_external_url_async(image_url)

        return image_url

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Download external image URL and convert to base64 data URL."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.debug("%s failed to inline image URL: %s", self.name, e)
                return None
            else:
                import base64

                content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("Image URL converted to base64 data URI for proxy")
                return f"data:{content_type};base64,{b64}"

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        """Convert various image input types to a URL or data URI string."""
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except AttributeError:
            pass

        return None

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for LTX API."""
        params = await self._get_parameters_async()

        if not params["image_uri"]:
            raise ValueError(f"{self.name} requires an input image for video generation.")

        if not params["prompt"].strip():
            raise ValueError(f"{self.name} requires a prompt to generate video.")

        validation_error = self._validate_model_params(params)
        if validation_error:
            raise ValueError(validation_error)

        # Map display name to model ID (without modality)
        model_id = MODEL_MAPPING.get(params["model"], "ltx-2-fast")

        payload: dict[str, Any] = {
            "image_uri": params["image_uri"],
            "prompt": params["prompt"].strip(),
            "model": model_id,
            "duration": int(params["duration"]),
            "resolution": params["resolution"],
            "fps": int(params["fps"]),
            "camera_motion": params["camera_motion"],
            "generate_audio": bool(params["generate_audio"]),
        }

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        video_bytes = result_json.get("audio_bytes")
        if not isinstance(video_bytes, (bytes, bytearray)):
            raise RuntimeError(f"{self.name} generation completed but no video data received.")

        await self._handle_completion_async(bytes(video_bytes), generation_id)

    async def _handle_completion_async(self, video_bytes: bytes, generation_id: str) -> None:
        """Handle successful completion by saving the video to static storage.

        Args:
            video_bytes: Raw binary MP4 data received from /result endpoint
            generation_id: Generation ID for filename
        """
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no video data received.",
            )
            return

        try:
            static_files_manager = GriptapeNodes.StaticFilesManager()
            filename = f"ltx_image_to_video_{generation_id}.mp4"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
            logger.info("%s saved video to static storage as %s", self.name, filename)
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        except (OSError, PermissionError) as e:
            logger.error("%s failed to save to static storage: %s", self.name, e)
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"Video generated but failed to save to storage: {e}",
            )

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        status = str(response_json.get("status") or "").lower()
        status_detail = response_json.get("status_detail")
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")

            if details and isinstance(details, str):
                try:
                    details_obj = json.loads(details)
                    if isinstance(details_obj, dict):
                        error_obj = details_obj.get("error")
                        if isinstance(error_obj, dict):
                            clean_message = error_obj.get("message")
                            if clean_message:
                                details = clean_message
                except (ValueError, json.JSONDecodeError):
                    pass

            if error and details:
                message = f"{error}: {details}"
            elif error:
                message = error
            elif details:
                message = details
            else:
                message = f"Generation {status or 'failed'} with no details provided"

            return f"{self.name} generation {status or 'failed'}: {message}"

        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                message = error.get("message") or error.get("type") or str(error)
                return f"{self.name} request failed: {message}"
            if isinstance(error, str):
                return f"{self.name} request failed: {error}"

        return f"{self.name} generation failed.\n\nFull API response:\n{response_json}"

    def _handle_payload_build_error(self, e: Exception) -> None:
        if isinstance(e, ValueError):
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            return

        super()._handle_payload_build_error(e)

    def _handle_api_key_validation_error(self, e: ValueError) -> None:
        self._set_safe_defaults()
        self._set_status_results(was_successful=False, result_details=str(e))
        logger.error("%s API key validation failed: %s", self.name, e)

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
