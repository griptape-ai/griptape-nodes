from __future__ import annotations

import json as _json
import logging
from contextlib import suppress
from typing import Any, ClassVar

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.events.static_file_events import (
    DownloadAndSaveRequest,
    DownloadAndSaveResultSuccess,
    LoadAsBase64DataUriRequest,
    LoadAsBase64DataUriResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.utils.artifact_normalization import normalize_artifact_list
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedanceVideoGeneration"]


class SeedanceVideoGeneration(GriptapeProxyNode):
    """Generate a video using the Seedance model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (supports provider flags like --resolution)
        - model_id (str): Provider model id (default: seedance-1-0-pro-250528)
        - resolution (str): Output resolution (default: 720p, options: 480p, 720p, 1080p)
        - ratio (str): Output aspect ratio (default: 16:9, options: auto, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16)
        - duration (int): Video duration in seconds (default: 5, options: 4-12)
        - camerafixed (bool): Camera fixed flag (default: False)
        - audio (bool): Generate audio with video (default: False, only for seedance-1-5-pro-251215)
        - first_frame (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (URL or base64 data URI)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for i2v and 1.5 pro models (URL or base64 data URI)
        (Always polls for result: 5s interval, 10 min timeout)

    Model capabilities:
        - seedance-1-5-pro-251215: 480p/720p, 4-12s duration, first+last frame, audio support
        - seedance-1-0-pro-250528: 480p/720p/1080p, 5s/10s duration, first+last frame
        - seedance-1-0-pro-fast-251015: 480p/720p/1080p, 5s/10s duration, first frame only
        - seedance-1-0-lite-t2v-250428: Text-to-video only (no images)
        - seedance-1-0-lite-i2v-250428: 1-4 reference images OR first+last frame OR first frame only

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    # Map user-facing names to provider model IDs
    MODEL_NAME_MAP: ClassVar[dict[str, str]] = {
        "Seedance 1.5 Pro": "seedance-1-5-pro-251215",
        "Seedance 1.0 Pro": "seedance-1-0-pro-250528",
        "Seedance 1.0 Pro Fast": "seedance-1-0-pro-fast-251015",
        "Seedance 1.0 Lite T2V": "seedance-1-0-lite-t2v-250428",
        "Seedance 1.0 Lite I2V": "seedance-1-0-lite-i2v-250428",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Seedance through Griptape Cloud model proxy"

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value="Seedance 1.5 Pro",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "Seedance 1.5 Pro",
                            "Seedance 1.0 Pro",
                            "Seedance 1.0 Pro Fast",
                            "Seedance 1.0 Lite T2V",
                            "Seedance 1.0 Lite I2V",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video (supports provider flags)",
                multiline=True,
                placeholder_text="Describe the video...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )
        # Optional first frame (image) - accepts artifact or URL/base64 string
        self.add_parameter(
            ParameterImage(
                name="first_frame",
                default_value=None,
                tooltip="Optional first frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "First Frame"},
            )
        )

        # Optional last frame (image) - accepts artifact or URL/base64 string valid only with seedance-1-0-lite-i2v
        self.add_parameter(
            ParameterImage(
                name="last_frame",
                default_value=None,
                tooltip="Optional Last frame image for seedance-1-0-lite-i2v model(URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame"},
            )
        )

        # Optional reference images (list of images) - for seedance-1-0-lite-i2v model (1-4 images)
        self.add_parameter(
            ParameterList(
                name="reference_images",
                input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
                default_value=[],
                tooltip="Optional reference images (1-4 images) for seedance-1-0-lite-i2v model",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Reference Images", "expander": True},
                max_items=4,
            )
        )

        with ParameterGroup(name="Generation Settings") as video_generation_settings_group:
            # Resolution selection
            ParameterString(
                name="resolution",
                default_value="720p",
                tooltip="Output resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["480p", "720p", "1080p"])},
            )

            # Aspect ratio selection
            ParameterString(
                name="ratio",
                default_value="adaptive",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"])},
            )

            # Duration in seconds
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[4, 5, 6, 7, 8, 9, 10, 11, 12])},
            )

            # Camera fixed flag
            ParameterBool(
                name="camerafixed",
                default_value=False,
                tooltip="Camera fixed",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            # Audio generation flag
            ParameterBool(
                name="generate_audio",
                default_value=False,
                tooltip="Generate audio with video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

        self.add_node_element(video_generation_settings_group)

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
                tooltip="Verbatim response from API (initial POST)",
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

        # Set initial parameter visibility based on default model
        default_model = "Seedance 1.5 Pro"
        default_provider_model_id = self._get_provider_model_id(default_model)
        if default_provider_model_id == "seedance-1-0-lite-t2v-250428":
            # T2V only - hide all image inputs
            self.hide_parameter_by_name("first_frame")
            self.hide_parameter_by_name("last_frame")
            self.hide_parameter_by_name("reference_images")
        elif default_provider_model_id == "seedance-1-0-lite-i2v-250428":
            # Lite I2V - show all image inputs (user can choose reference images OR first/last frame)
            self.show_parameter_by_name("first_frame")
            self.show_parameter_by_name("last_frame")
            self.show_parameter_by_name("reference_images")
        else:
            # Other models - show first_frame, conditionally show last_frame, hide reference_images
            self.show_parameter_by_name("first_frame")
            self.hide_parameter_by_name("reference_images")
            supports_last_frame = default_provider_model_id in (
                "seedance-1-5-pro-251215",
                "seedance-1-0-pro-250528",
            )
            if supports_last_frame:
                self.show_parameter_by_name("last_frame")
            else:
                self.hide_parameter_by_name("last_frame")

        # Hide audio parameter by default (only show for 1.5 pro)
        if default_provider_model_id == "seedance-1-5-pro-251215":
            self.show_parameter_by_name("generate_audio")
        else:
            self.hide_parameter_by_name("generate_audio")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters based on model capabilities.

        Model capabilities:
        - seedance-1-5-pro-251215: text-to-video, i2v with first frame, i2v with first+last frame, audio support
        - seedance-1-0-pro-250528: i2v with first+last frame, i2v with first frame, text-to-video
        - seedance-1-0-pro-fast-251015: i2v with first frame only, text-to-video
        - seedance-1-0-lite-t2v-250428: text-to-video only (no images)
        - seedance-1-0-lite-i2v-250428: i2v with reference images, i2v with first+last frame, i2v with first frame
        """
        if parameter.name == "model_id":
            # Convert friendly name to provider model ID
            provider_model_id = self._get_provider_model_id(value)

            if provider_model_id == "seedance-1-0-lite-t2v-250428":
                # T2V only - hide all image inputs
                self.hide_parameter_by_name("first_frame")
                self.hide_parameter_by_name("last_frame")
                self.hide_parameter_by_name("reference_images")
            elif provider_model_id == "seedance-1-0-lite-i2v-250428":
                # Lite I2V - show all image inputs (user can choose reference images OR first/last frame)
                self.show_parameter_by_name("first_frame")
                self.show_parameter_by_name("last_frame")
                self.show_parameter_by_name("reference_images")
            else:
                # Other models - show first_frame, conditionally show last_frame, hide reference_images
                self.show_parameter_by_name("first_frame")
                self.hide_parameter_by_name("reference_images")
                supports_last_frame = provider_model_id in (
                    "seedance-1-5-pro-251215",
                    "seedance-1-0-pro-250528",
                )
                if supports_last_frame:
                    self.show_parameter_by_name("last_frame")
                else:
                    self.hide_parameter_by_name("last_frame")

            # Show audio parameter only for 1.5 pro model
            if provider_model_id == "seedance-1-5-pro-251215":
                self.show_parameter_by_name("generate_audio")
            else:
                self.hide_parameter_by_name("generate_audio")

        # Convert string paths to ImageUrlArtifact by uploading to static storage
        if parameter.name == "reference_images" and isinstance(value, list):
            updated_list = normalize_artifact_list(value, ImageUrlArtifact, accepted_types=(ImageArtifact,))
            if updated_list != value:
                self.set_parameter_value("reference_images", updated_list)

        return super().after_value_set(parameter, value)

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Converts user-facing model name to provider model ID.
        """
        raw_model_id = self.get_parameter_value("model_id") or "Seedance 1.5 Pro"
        return self._get_provider_model_id(raw_model_id)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        params = self._get_parameters()

        # Validate parameter combinations
        try:
            self._validate_parameters(params)
        except ValueError as e:
            exceptions.append(e)

        return exceptions if exceptions else None

    def _get_parameters(self) -> dict[str, Any]:
        raw_model_id = self.get_parameter_value("model_id") or "Seedance 1.5 Pro"
        # Convert friendly name to provider model ID
        model_id = self._get_provider_model_id(raw_model_id)

        # Normalize reference images (handles cases where values come from connections)
        reference_images = self.get_parameter_value("reference_images") or []
        normalized_reference_images = (
            normalize_artifact_list(reference_images, ImageUrlArtifact, accepted_types=(ImageArtifact,))
            if reference_images
            else []
        )

        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": model_id,
            "resolution": self.get_parameter_value("resolution") or "720p",
            "ratio": self.get_parameter_value("ratio") or "adaptive",
            "first_frame": self.get_parameter_value("first_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "reference_images": normalized_reference_images,
            "duration": self.get_parameter_value("duration"),
            "camerafixed": self.get_parameter_value("camerafixed"),
            "generate_audio": self.get_parameter_value("generate_audio"),
        }

    @classmethod
    def _get_provider_model_id(cls, user_facing_name: str) -> str:
        """Convert user-facing model name to provider model ID.

        Falls back to the input value if it's not in the mapping (for backwards compatibility
        with saved flows that may have old model IDs).
        """
        return cls.MODEL_NAME_MAP.get(user_facing_name, user_facing_name)

    def _validate_parameters(self, params: dict[str, Any]) -> None:
        """Validate parameter combinations.

        Raises:
            ValueError: If invalid parameter combinations are detected
        """
        model_id = params["model_id"]

        # For lite-i2v model, check if both reference_images and first/last frames are provided
        if model_id == "seedance-1-0-lite-i2v-250428":
            has_reference_images = (
                params.get("reference_images")
                and isinstance(params.get("reference_images"), list)
                and len(params.get("reference_images", [])) > 0
            )
            has_first_or_last_frame = params.get("first_frame") is not None or params.get("last_frame") is not None

            if has_reference_images and has_first_or_last_frame:
                msg = (
                    f"{self.name}: Cannot use both reference_images and first_frame/last_frame for Seedance 1.0 Lite I2V. "
                    "Please use either reference_images (1-4 images) OR first_frame/last_frame, not both."
                )
                raise ValueError(msg)

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Seedance API (without model field)."""
        # Get parameters
        params = self._get_parameters()

        # Build content array with text prompt
        prompt_text = params["prompt"].strip()

        # Build payload with config params at top level (model is handled separately by base class)
        payload: dict[str, Any] = {"model": params["model_id"]}

        # Add config parameters at top level
        if params["resolution"]:
            payload["resolution"] = params["resolution"]
            prompt_text += f" --resolution {params['resolution']}"
        if params["ratio"]:
            payload["ratio"] = params["ratio"]
            prompt_text += f" --ratio {params['ratio']}"
        if params["duration"] is not None:
            payload["duration"] = int(params["duration"])
            prompt_text += f" --duration {int(params['duration'])}"
        if params["camerafixed"] is not None:
            payload["camerafixed"] = bool(params["camerafixed"])
            prompt_text += f" --camerafixed {str(bool(params['camerafixed'])).lower()}"
        # Only add audio flag for 1.5 pro model
        if params["model_id"] == "seedance-1-5-pro-251215" and params["generate_audio"] is not None:
            payload["generate_audio"] = bool(params["generate_audio"])

        content_list = [{"type": "text", "text": prompt_text}]

        # Add frame images based on model capabilities
        await self._add_frame_images_async(content_list, params)

        payload["content"] = content_list

        return payload

    async def _add_frame_images_async(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frame images to content list based on model capabilities.

        Different models support different image inputs:
        - seedance-1-5-pro: text-to-video, i2v with first frame, i2v with first+last frame
        - seedance-1-0-pro: i2v with first+last frame, i2v with first frame, text-to-video
        - seedance-1-0-lite-t2v: text-to-video only (no images)
        - seedance-1-0-lite-i2v: i2v with 1-4 reference images OR i2v with first+last frame OR i2v with first frame

        Role is always specified in image_url object: "first_frame", "last_frame", or "reference_image"

        For lite-i2v model, if reference_images is provided, use those instead of first/last frames.
        """
        model_id = params["model_id"]

        # seedance-1-0-lite-t2v only supports text-to-video, no images
        if model_id == "seedance-1-0-lite-t2v-250428":
            return

        # For lite-i2v model, check if reference_images is provided (takes priority)
        if model_id == "seedance-1-0-lite-i2v-250428":
            reference_images = params.get("reference_images")
            if reference_images and isinstance(reference_images, list) and len(reference_images) > 0:
                # Add up to 4 reference images
                for _i, ref_image in enumerate(reference_images[:4]):
                    ref_url = await self._prepare_frame_url_async(ref_image)
                    if ref_url:
                        content_list.append(
                            {"type": "image_url", "image_url": {"url": ref_url}, "role": "reference_image"}
                        )
                # If reference images are provided, don't add first/last frames
                return

        # Determine which frames this model supports
        supports_last_frame = model_id in (
            "seedance-1-5-pro-251215",
            "seedance-1-0-pro-250528",
            "seedance-1-0-lite-i2v-250428",
        )

        # Add first_frame if provided
        first_frame_url = await self._prepare_frame_url_async(params["first_frame"])
        if first_frame_url:
            content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})

        # Add last_frame only if model supports it and it's provided
        if supports_last_frame:
            last_frame_url = await self._prepare_frame_url_async(params["last_frame"])
            if last_frame_url:
                content_list.append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})

    async def _prepare_frame_url_async(self, frame_input: Any) -> str | None:
        """Convert frame input to a usable URL, handling inlining of external URLs."""
        if not frame_input:
            return None

        frame_url = self._coerce_image_url_or_data_uri(frame_input)
        if not frame_url:
            return None
        return await self._inline_external_url_async(frame_url)

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Inline external image URL as base64 data URI (async version)."""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return url

        result = await GriptapeNodes.ahandle_request(
            LoadAsBase64DataUriRequest(
                artifact_or_url=url,
                context_name=f"{self.name}.frame_image",
            )
        )

        if isinstance(result, LoadAsBase64DataUriResultSuccess):
            self._log("Frame URL converted to data URI for proxy")
            return result.data_uri

        self._log(f"Warning: failed to inline frame URL: {result.result_details}")
        return url

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the result and set output parameters.

        Args:
            result_json: The JSON response from the /result endpoint
            generation_id: The generation ID for this request
        """
        # Extract video URL from the response
        extracted_url = self._extract_video_url(result_json)
        if not extracted_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no video URL was found in the response.",
            )
            return

        # Download and save video using DownloadAndSaveRequest
        filename = f"seedance_video_{generation_id}.mp4"
        result = await GriptapeNodes.ahandle_request(
            DownloadAndSaveRequest(
                url=extracted_url,
                filename=filename,
                artifact_type=VideoUrlArtifact,
            )
        )

        if isinstance(result, DownloadAndSaveResultSuccess):
            self.parameter_output_values["video_url"] = result.artifact
            self._log(f"Saved video to static storage as {filename}")
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
            self._log(f"Failed to download/save video: {result.result_details}")
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from failed/errored generation response.

        Tries provider-specific error patterns first, then falls back to base implementation.

        Args:
            response_json: The JSON response from the generation status endpoint

        Returns:
            str: A formatted error message to display to the user
        """
        if not response_json:
            return super()._extract_error_message(response_json)

        # Try to extract from provider response (legacy pattern)
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))
        if parsed_provider_response:
            provider_error = parsed_provider_response.get("error")
            if provider_error:
                if isinstance(provider_error, dict):
                    error_message = provider_error.get("message", "")
                    details = f"{self.name} {error_message}"
                    if error_code := provider_error.get("code"):
                        details += f"\nError Code: {error_code}"
                    if error_type := provider_error.get("type"):
                        details += f"\nError Type: {error_type}"
                    return details
                return f"{self.name} Provider error: {provider_error}"

        # Fall back to base implementation
        return super()._extract_error_message(response_json)

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return _json.loads(provider_response)
            except Exception:
                return None
        if isinstance(provider_response, dict):
            return provider_response
        return None

    def _set_safe_defaults(self) -> None:
        """Clear all output parameters on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        # Heuristic search for a URL in common places
        # 1) direct fields
        for key in ("url", "video_url", "output_url"):
            val = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(val, str) and val.startswith("http"):
                return val
        # 2) nested known containers (Seedance returns content.video_url)
        for key in ("result", "data", "output", "outputs", "content", "task_result"):
            nested = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(nested, dict):
                url = SeedanceVideoGeneration._extract_video_url(nested)
                if url:
                    return url
            elif isinstance(nested, list):
                for item in nested:
                    url = SeedanceVideoGeneration._extract_video_url(item if isinstance(item, dict) else None)
                    if url:
                        return url
        return None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
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
        except Exception:  # noqa: S110
            pass

        return None
