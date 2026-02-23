from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_components.project_file_parameter import ProjectFileParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError, FileWriteError
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["MinimaxHailuoVideoGeneration"]


class MinimaxHailuoVideoGeneration(GriptapeProxyNode):
    """Generate a video using the MiniMax Hailuo model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Model to use (default: Hailuo 2.3)
        - duration (int): Video duration in seconds (default: 6, options depend on model)
        - resolution (str): Output resolution (options depend on model and duration)
        - prompt_optimizer (bool): Enable prompt optimization (default: False)
        - fast_pretreatment (bool): Reduce optimization time for Hailuo 2.3/02 models (default: False)
        - first_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (data URL)
        - last_frame_image (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for Hailuo 02 model (data URL)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    DEFAULT_MAX_ATTEMPTS = 240

    # Model capability definitions (keyed by provider model IDs)
    MODEL_CAPABILITIES: ClassVar[dict[str, Any]] = {
        "MiniMax-Hailuo-2.3": {
            "durations": [6, 10],
            "resolutions": {"6": ["768p", "1080p"], "10": ["768p"]},
            "default_resolution": {"6": "768p", "10": "768p"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-02": {
            "durations": [6, 10],
            "resolutions": {"6": ["768p", "1080p"], "10": ["768p"]},
            "default_resolution": {"6": "768p", "10": "768p"},
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_fast_pretreatment": True,
        },
        "MiniMax-Hailuo-2.3-Fast": {
            "durations": [6],
            "resolutions": {"6": ["720p", "1080p"]},
            "default_resolution": {"6": "720p"},
            "supports_first_frame": True,
            "supports_last_frame": False,
            "supports_fast_pretreatment": False,
        },
    }

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Hailuo 2.3 (TTV & ITV)": "MiniMax-Hailuo-2.3",
        "Hailuo 02 (TTV & ITV)": "MiniMax-Hailuo-02",
        "Hailuo 2.3 Fast (ITV)": "MiniMax-Hailuo-2.3-Fast",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value="Hailuo 2.3 (TTV & ITV)",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "Hailuo 2.3 (TTV & ITV)",
                            "Hailuo 02 (TTV & ITV)",
                            "Hailuo 2.3 Fast (ITV)",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "prompt",
                },
            )
        )

        # Optional first frame (image) - accepts artifact or data URL string
        self.add_parameter(
            ParameterImage(
                name="first_frame_image",
                default_value=None,
                tooltip=(
                    "Optional first frame image as data URL (data:image/jpeg;base64,...). "
                    "Supported formats: JPG, JPEG, PNG, WebP. Requirements: <20MB, short edge >300px, "
                    "aspect ratio between 2:5 and 5:2."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "First Frame Image"},
            )
        )

        # Optional last frame (image) - only for 02 model
        self.add_parameter(
            ParameterImage(
                name="last_frame_image",
                default_value=None,
                tooltip=(
                    "Optional last frame image for Hailuo 02 model as data URL (data:image/jpeg;base64,...). "
                    "Supported formats: JPG, JPEG, PNG, WebP. Requirements: <20MB, short edge >300px, "
                    "aspect ratio between 2:5 and 5:2."
                ),
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame Image", "hide": True},
            )
        )

        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            # Duration in seconds
            ParameterInt(
                name="duration",
                default_value=6,
                tooltip="Video duration in seconds (options depend on model)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[6, 10])},
            )

            # Resolution selection
            ParameterString(
                name="resolution",
                default_value="768p",
                tooltip="Output resolution (options depend on model and duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "768p", "1080p"])},
            )

            # Prompt optimizer flag
            ParameterBool(
                name="prompt_optimizer",
                default_value=False,
                tooltip="Enable prompt optimization",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            # Fast pretreatment flag (only for 2.3 and 02 models)
            ParameterBool(
                name="fast_pretreatment",
                default_value=False,
                tooltip="Reduce optimization time (only for Hailuo 2.3 and Hailuo 02)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide": False},
            )

        self.add_node_element(gen_settings_group)

        # OUTPUTS
        self._output_file_param = ProjectFileParameter(
            node=self,
            name="output_file",
            situation="save_node_output",
            default_filename="hailuo_video.mp4",
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

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # Set initial parameter visibility based on default model
        default_model = "Hailuo 2.3 (TTV & ITV)"
        default_provider_model_id = self._get_provider_model_id(default_model)
        default_capabilities = self.MODEL_CAPABILITIES.get(default_provider_model_id, {})

        # Show/hide last_frame_image based on default model
        if default_capabilities.get("supports_last_frame", False):
            self.show_parameter_by_name("last_frame_image")
        else:
            self.hide_parameter_by_name("last_frame_image")

        # Show/hide fast_pretreatment based on default model
        if default_capabilities.get("supports_fast_pretreatment", False):
            self.show_parameter_by_name("fast_pretreatment")
        else:
            self.hide_parameter_by_name("fast_pretreatment")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        super().after_value_set(parameter, value)

        if parameter.name == "model_id":
            # Convert friendly name to provider model ID
            provider_model_id = self._get_provider_model_id(value)

            # Show/hide last_frame_image parameter only for 02 model
            capabilities = self.MODEL_CAPABILITIES.get(provider_model_id, {})
            show_last_frame = capabilities.get("supports_last_frame", False)
            if show_last_frame:
                self.show_parameter_by_name("last_frame_image")
            else:
                self.hide_parameter_by_name("last_frame_image")

            # Show/hide fast_pretreatment based on model support
            show_fast_pretreatment = capabilities.get("supports_fast_pretreatment", False)
            if show_fast_pretreatment:
                self.show_parameter_by_name("fast_pretreatment")
            else:
                self.hide_parameter_by_name("fast_pretreatment")

    async def _process_generation(self) -> None:
        await super()._process_generation()

    def _get_parameters(self) -> dict[str, Any]:
        raw_model_id = self.get_parameter_value("model_id") or "Hailuo 2.3 (TTV & ITV)"
        # Convert friendly name to provider model ID
        model_id = self._get_provider_model_id(raw_model_id)

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": model_id,
            "duration": self.get_parameter_value("duration"),
            "resolution": self.get_parameter_value("resolution") or "768p",
            "prompt_optimizer": self.get_parameter_value("prompt_optimizer"),
            "fast_pretreatment": self.get_parameter_value("fast_pretreatment"),
            "first_frame_image": self.get_parameter_value("first_frame_image"),
            "last_frame_image": self.get_parameter_value("last_frame_image"),
        }

    @classmethod
    def _get_provider_model_id(cls, user_facing_name: str) -> str:
        """Convert user-facing model name to provider model ID.

        Falls back to the input value if it's not in the mapping (for backwards compatibility
        with saved flows that may have old model IDs).
        """
        return cls.MODEL_NAME_MAP.get(user_facing_name, user_facing_name)

    def _get_api_model_id(self) -> str:
        raw_model_id = self.get_parameter_value("model_id") or "Hailuo 2.3 (TTV & ITV)"
        return self._get_provider_model_id(raw_model_id)

    async def _build_payload(self) -> dict[str, Any]:  # noqa: C901
        """Build the request payload for MiniMax Hailuo API."""
        params = self._get_parameters()

        if not params["prompt"].strip():
            msg = f"{self.name} requires a prompt to generate video."
            raise ValueError(msg)

        if params["model_id"] == "MiniMax-Hailuo-2.3-Fast" and not params["first_frame_image"]:
            msg = f"{self.name} requires a first frame image for Hailuo 2.3 Fast model (image-to-video only)."
            raise ValueError(msg)

        capabilities = self.MODEL_CAPABILITIES.get(params["model_id"], {})
        valid_resolutions = capabilities.get("resolutions", {}).get(str(params["duration"]), [])
        if valid_resolutions and params["resolution"] not in valid_resolutions:
            msg = (
                f"{self.name}: Model {params['model_id']} does not support the combination of "
                f"duration {params['duration']}s and resolution {params['resolution']}. "
                f"Valid resolutions for {params['duration']}s: {', '.join(valid_resolutions)}"
            )
            raise ValueError(msg)

        model_id = params["model_id"]
        payload: dict[str, Any] = {
            "model": model_id,
            "prompt": params["prompt"].strip(),
        }

        # Add duration
        if params["duration"] is not None:
            payload["duration"] = int(params["duration"])

        # Add resolution (uppercase for API)
        if params["resolution"]:
            payload["resolution"] = params["resolution"].upper()

        # Always send prompt_optimizer (defaults to False)
        payload["prompt_optimizer"] = bool(params["prompt_optimizer"])

        # Add fast_pretreatment only for models that support it
        capabilities = self.MODEL_CAPABILITIES.get(model_id, {})
        if capabilities.get("supports_fast_pretreatment", False):
            payload["fast_pretreatment"] = bool(params["fast_pretreatment"])

        # Add first_frame_image if provided and model supports it
        if capabilities.get("supports_first_frame", False):
            first_frame_data_url = await self._prepare_frame_data_url_async(params["first_frame_image"])
            if first_frame_data_url:
                payload["first_frame_image"] = first_frame_data_url

        # Add last_frame_image if provided and model supports it
        if capabilities.get("supports_last_frame", False):
            last_frame_data_url = await self._prepare_frame_data_url_async(params["last_frame_image"])
            if last_frame_data_url:
                payload["last_frame_image"] = last_frame_data_url

        return payload

    async def _prepare_frame_data_url_async(self, frame_input: Any) -> str | None:
        """Convert frame input to a data URL, handling external URLs by downloading and converting."""
        if not frame_input:
            return None

        frame_url = self._coerce_image_url_or_data_uri(frame_input)
        if not frame_url:
            return None

        # If it's already a data URL, return it
        if frame_url.startswith("data:image/"):
            return frame_url

        try:
            return await File(frame_url).aread_data_uri(fallback_mime="image/jpeg")
        except FileLoadError as e:
            logger.debug("%s failed to load frame from %s: %s", self.name, frame_url, e)
            return None

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def _sanitize_body(b: dict[str, Any]) -> dict[str, Any]:
            try:
                red = deepcopy(b)
                # Redact data URLs in frame images
                for key in ("first_frame_image", "last_frame_image"):
                    if key in red and isinstance(red[key], str) and red[key].startswith("data:image/"):
                        parts = red[key].split(",", 1)
                        header = parts[0] if parts else "data:image/"
                        b64 = parts[1] if len(parts) > 1 else ""
                        red[key] = f"{header},<redacted base64 length={len(b64)}>"
            except (KeyError, TypeError, ValueError):
                return b
            else:
                return red

        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        logger.debug("POST %s\nheaders=%s\nbody=%s", url, dbg_headers, json.dumps(_sanitize_body(payload), indent=2))

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        self.parameter_output_values["provider_response"] = result_json
        await self._handle_completion_async(result_json, generation_id)

    async def _handle_completion_async(self, response_json: dict[str, Any], generation_id: str) -> None:  # noqa: ARG002
        """Handle successful completion by downloading and saving the video."""
        file_obj = response_json.get("file")
        if not isinstance(file_obj, dict):
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no file object found in response.",
            )
            return

        download_url = file_obj.get("download_url")
        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download_url found in response.",
            )
            return

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
                logger.warning("%s failed to write video: %s, using provider URL", self.name, e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save video: {e}).",
                )
            else:
                self.parameter_output_values["video_url"] = VideoUrlArtifact(
                    value=actual_path, name=Path(actual_path).name
                )
                logger.info("%s saved video to %s", self.name, actual_path)
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

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        status = str(response_json.get("status") or "").lower()
        status_detail = response_json.get("status_detail")
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")
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
                message = error.get("message", str(error))
                return f"{self.name} request failed: {message}"
            return f"{self.name} request failed: {error}"

        return f"{self.name} generation failed with no error details in response."

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
