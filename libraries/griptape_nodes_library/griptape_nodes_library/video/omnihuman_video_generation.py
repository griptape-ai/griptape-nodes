from __future__ import annotations

import base64
import contextlib
import io
import json as _json
import logging
import time
from typing import Any, ClassVar

import httpx
from griptape.artifacts import VideoUrlArtifact
from griptape.artifacts.url_artifact import UrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.files.file import File, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import resize_image_for_resolution, shrink_image_to_size

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanVideoGeneration"]

# Maximum image size in bytes (5MB)
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
# Maximum image resolution (4096x4096)
MAX_IMAGE_DIMENSION = 4096


class OmnihumanVideoGeneration(GriptapeProxyNode):
    """Generate video effects from a single image, text prompt, and audio file using OmniHuman 1.5.

    This is Step 3 of the OmniHuman workflow. It generates video matching the input image based
    on the provided audio and optional mask. The generation process is asynchronous and will
    poll for completion.

    Inputs:
        - image_url (str): Source image URL
        - audio_url (str): Audio file URL
        - mask_image_urls (list): Optional mask image URLs from subject detection
        - prompt (str): Text prompt to guide generation
        - seed (int): Random seed for generation (-1 for random)
        - fast_mode (bool): Enable fast mode (sacrifices some effects for speed

    Outputs:
        - generation_id (str): Griptape Cloud generation identifier
        - video_url (VideoUrlArtifact): Generated video URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the video generation result or any errors
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-0",
        "omnihuman-1-5",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate talking head videos using OmniHuman 1.5 via Griptape Cloud"

        # INPUTS
        # add model_id parameter with fixed value
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value="omnihuman-1-5",
                tooltip="Model identifier to use for generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.MODEL_IDS)},
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt to guide generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Text prompt to guide generation",
            )
        )

        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterImage(
                name="image_url",
                default_value="",
                tooltip="Source image URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/image.jpg"},
            ),
            disclaimer_message="The OmniHuman service utilizes this URL to access the image for video generation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        self._public_audio_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterAudio(
                name="audio_url",
                default_value="",
                tooltip="Audio file URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/audio.mp3"},
            ),
        )
        self._public_audio_url_parameter.add_input_parameters()
        self.add_parameter(
            Parameter(
                name="mask_image_urls",
                input_types=["list"],
                type="list",
                output_type="list",
                default_value=[],
                tooltip="Optional mask image URLs from subject detection (will auto-detect if enabled and not provided)",
                ui_options={"placeholder_text": "https://example.com/mask1.png"},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        with ParameterGroup(name="Generation Settings") as video_generation_settings_group:
            # Image size validation
            ParameterBool(
                name="auto_image_resize",
                tooltip=f"If disabled, raises an error when input image exceeds the {MAX_IMAGE_SIZE_BYTES / (1024 * 1024):.0f}MB size limit or {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} resolution limit. If enabled, oversized images are automatically resized to fit within these limits.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=True,
            )

            ParameterBool(
                name="auto_detect_masks",
                tooltip="Automatically detect subject masks if none provided (calls subject detection API)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value=True,
                hide=True,
            )

            ParameterInt(
                name="seed",
                default_value=-1,
                tooltip="Random seed for generation (-1 for random)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )

            ParameterBool(
                name="fast_mode",
                default_value=False,
                tooltip="Enable fast mode (sacrifices some effects for speed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        self.add_node_element(video_generation_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation identifier",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video_url",
                tooltip="Generated video URL artifact",
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

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        # if the model_id parameter is omnihuman-1-0, remove seed, fast_mode, and prompt parameters
        if parameter.name == "model_id" and value == "omnihuman-1-0":
            self.hide_parameter_by_name("seed")
            self.hide_parameter_by_name("fast_mode")
            self.hide_parameter_by_name("prompt")
        elif parameter.name == "model_id":
            self.show_parameter_by_name("seed")
            self.show_parameter_by_name("fast_mode")
            self.show_parameter_by_name("prompt")

    def _log(self, message: str) -> None:
        """Log a message."""
        with contextlib.suppress(Exception):
            logger.info("%s: %s", self.name, message)

    async def aprocess(self) -> None:
        """Process video generation asynchronously."""
        try:
            await self._process_generation()
        finally:
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_audio_url_parameter.delete_uploaded_artifact()

    async def _get_image_for_api(self) -> bytes | None:
        """Get the image bytes to use for the API call, shrinking if needed."""
        # Get the image file contents
        file_contents = await self._get_image_file_contents()
        if file_contents is None:
            return None

        # Check file size
        size_bytes = len(file_contents)
        size_mb = size_bytes / (1024 * 1024)
        max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
        exceeds_size = size_bytes > MAX_IMAGE_SIZE_BYTES

        # Check resolution
        img = Image.open(io.BytesIO(file_contents))
        width, height = img.size
        exceeds_resolution = width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION

        # If neither constraint is exceeded, use original
        if not exceeds_size and not exceeds_resolution:
            return file_contents

        # Check if auto resize is enabled
        auto_image_resize = self.get_parameter_value("auto_image_resize")
        if not auto_image_resize:
            issues = []
            if exceeds_size:
                issues.append(f"size {size_mb:.2f}MB exceeds {max_mb:.0f}MB limit")
            if exceeds_resolution:
                issues.append(f"resolution {width}x{height} exceeds {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} limit")
            msg = f"{self.name} input image: {', '.join(issues)}"
            raise ValueError(msg)

        # Log what needs to be fixed
        if exceeds_size and exceeds_resolution:
            self._log(f"Input image is {size_mb:.2f}MB and {width}x{height}, resizing...")
        elif exceeds_size:
            self._log(f"Input image is {size_mb:.2f}MB, shrinking to under {max_mb:.0f}MB...")
        else:
            self._log(
                f"Input image is {width}x{height}, resizing to under {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}..."
            )

        # Resize for resolution if needed, then shrink for size
        resized_bytes = (
            resize_image_for_resolution(file_contents, MAX_IMAGE_DIMENSION, self.name)
            if exceeds_resolution
            else file_contents
        )
        shrunk_bytes = shrink_image_to_size(resized_bytes, MAX_IMAGE_SIZE_BYTES, self.name)

        if len(shrunk_bytes) >= len(file_contents):
            # Shrinking didn't help
            self._log("Could not shrink image, using original")
            return file_contents

        self._log(f"Resized image to {len(shrunk_bytes) / (1024 * 1024):.2f}MB")
        return shrunk_bytes

    async def _get_image_file_contents(self) -> bytes | None:
        """Get the file contents of the input image."""
        parameter_value = self.get_parameter_value("image_url")

        # Extract a string that File can handle
        if isinstance(parameter_value, UrlArtifact):
            url = parameter_value.value
        elif isinstance(parameter_value, str):
            url = parameter_value
        else:
            # ImageArtifact with .base64 property — wrap as data URI for File
            b64 = getattr(parameter_value, "base64", None)
            if isinstance(b64, str):
                url = f"data:image/png;base64,{b64}"
            else:
                return None

        if not url:
            return None

        try:
            return await File(url).aread_bytes()
        except FileLoadError as e:
            self._log(f"Failed to load image from {url}: {e}")
            return None

    async def _get_parameters(self) -> dict[str, Any]:  # noqa: C901
        """Get and normalize input parameters."""
        image_input = self.get_parameter_value("image_url")
        audio_input = self.get_parameter_value("audio_url")
        mask_image_urls = self.get_parameter_value("mask_image_urls")
        prompt = self.get_parameter_value("prompt")
        seed = self.get_parameter_value("seed")
        fast_mode = self.get_parameter_value("fast_mode")

        model_id = self.get_parameter_value("model_id")

        if not image_input:
            msg = "image_url parameter is required."
            raise ValueError(msg)

        if not audio_input:
            msg = "audio_url parameter is required."
            raise ValueError(msg)

        image_bytes = await self._get_image_for_api()
        if not image_bytes:
            msg = "Failed to read image contents."
            raise ValueError(msg)

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/png;base64,{image_b64}"
        audio_url = await self._prepare_audio_data_url_async(audio_input)
        if not audio_url:
            msg = "Failed to process audio input."
            raise ValueError(msg)

        # Handle artifacts
        if hasattr(mask_image_urls, "value"):
            mask_image_urls = mask_image_urls.value

        # Auto-detect masks if enabled and no mask_image_urls provided
        auto_detect = self.get_parameter_value("auto_detect_masks")
        if auto_detect and (not mask_image_urls or len(mask_image_urls) == 0):
            self._log("No masks provided, running subject detection to generate masks")
            mask_image_urls = await self._auto_detect_masks(image_url)
            if mask_image_urls:
                self._log(f"Auto-detected {len(mask_image_urls)} mask(s)")

        mask_data_urls = []
        if mask_image_urls:
            for mask_url in mask_image_urls:
                data_url = await self._prepare_image_data_url_async(mask_url)
                if data_url:
                    mask_data_urls.append(data_url)

        body = {
            "req_key": self._get_req_key(model_id),
            "image_url": image_url,
            "audio_url": audio_url,
            "mask_url": "; ".join(mask_data_urls) if mask_data_urls else None,
            "prompt": prompt if prompt else None,
            "seed": seed if seed else None,
            "fast_mode": fast_mode if fast_mode else None,
        }
        return {k: v for k, v in body.items() if v is not None}

    async def _auto_detect_masks(self, image_url: str) -> list[str]:
        """Automatically detect masks by calling the subject detection API."""
        headers = {"Authorization": f"Bearer {self._validate_api_key()}", "Content-Type": "application/json"}

        # Build payload for subject detection
        provider_params = {
            "req_key": "realman_avatar_object_detection_cv",
            "image_url": image_url,
        }

        post_url = f"{self._proxy_base}models/omnihuman-1-5-subject-detection"
        self._log("Calling subject detection API for auto-mask generation")

        try:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/3041
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    post_url,
                    json=provider_params,
                    headers=headers,
                    timeout=300.0,
                )

                if response.status_code >= 400:  # noqa: PLR2004
                    error_msg = f"Subject detection failed with status {response.status_code}: {response.text}"
                    self._log(error_msg)
                    return []

                response_json = response.json()
                # Extract mask URLs from response
                resp_data = _json.loads(response_json.get("data", {}).get("resp_data", "{}"))
                mask_urls = resp_data.get("object_detection_result", {}).get("mask", {}).get("url", [])
                return mask_urls if isinstance(mask_urls, list) else []

        except Exception as e:
            self._log(f"Auto-detection failed: {e}")
            return []

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-0":
            return "realman_avatar_picture_omni_cv"
        if model_id == "omnihuman-1-5":
            return "realman_avatar_picture_omni15_cv"
        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)

    def _validate_api_key(self) -> str:
        """Validate that the API key is available."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _get_api_model_id(self) -> str:
        return self.get_parameter_value("model_id") or ""

    async def _build_payload(self) -> dict[str, Any]:
        params = await self._get_parameters()
        return params

    async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
        # Handle binary response if returned
        if "raw_bytes" in result_json:
            await self._handle_video_bytes(result_json["raw_bytes"])
            return

        provider_response = result_json.get("provider_response", result_json)
        if isinstance(provider_response, str):
            try:
                provider_response = _json.loads(provider_response)
            except Exception:
                provider_response = {}

        status = provider_response.get("data", {}).get("status", "").lower()
        if status in {"not_found", "expired"}:
            self.parameter_output_values["video_url"] = None
            error_details = f"Video generation failed.\nStatus: {status}\nFull response: {result_json}"
            self._set_status_results(was_successful=False, result_details=error_details)
            return

        await self._handle_completion(provider_response)

    async def _handle_video_bytes(self, video_bytes: bytes) -> None:
        if not video_bytes:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(was_successful=False, result_details="Received empty video data from API.")
            return

        try:
            video_filename = f"omnihuman_video_{int(time.time())}.mp4"
            saved_url = GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, video_filename)
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=video_filename)
            self._set_status_results(
                was_successful=True,
                result_details=f"Video generation completed successfully. Saved as: {video_filename}",
            )
        except Exception as e:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False, result_details=f"Video generation completed but failed to save: {e}"
            )

    async def _prepare_audio_data_url_async(self, audio_input: Any) -> str | None:
        if not audio_input:
            return None

        audio_url = self._coerce_audio_url_or_data_uri(audio_input)
        if not audio_url:
            return None

        # Already a data URI — return as-is
        if audio_url.startswith("data:audio/"):
            return audio_url

        try:
            return await File(audio_url).aread_data_uri(fallback_mime="audio/mpeg")
        except FileLoadError as e:
            self._log(f"Failed to load audio from {audio_url}: {e}")
            return None

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
            return await File(image_url).aread_data_uri(fallback_mime="image/png")
        except FileLoadError as e:
            self._log(f"Failed to load image from {image_url}: {e}")
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
    def _coerce_audio_url_or_data_uri(val: Any) -> str | None:
        if val is None:
            return None

        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:audio/")) else f"data:audio/mpeg;base64,{v}"

        try:
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:audio/")):
                return v
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:audio/") else f"data:audio/mpeg;base64,{b64}"
        except AttributeError:
            pass

        return None

    async def _handle_completion(self, response_json: dict[str, Any]) -> None:
        """Handle successful completion of video generation."""
        # Extract provider response
        provider_response = response_json.get("provider_response", {})
        if isinstance(provider_response, str):
            try:
                provider_response = _json.loads(provider_response)
            except Exception:
                provider_response = {}

        # Extract video URL from provider response
        video_url = self._extract_video_url(provider_response)

        if not video_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)
        try:
            self._log("Downloading video bytes from provider URL")
            video_filename = await self._save_video_bytes(video_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_filename = None

        self._set_status_results(
            was_successful=True,
            result_details=f"Video generation completed successfully. Video URL: {video_url}"
            + (f", saved as: {video_filename}" if video_filename else ""),
        )

    @staticmethod
    def _extract_video_url(response_json: dict[str, Any]) -> str | None:
        """Extract video URL from API response."""
        # Try direct video_url field
        video_url = _json.loads(response_json.get("data", {}).get("resp_data", "{}")).get("video_url")
        if isinstance(video_url, str) and video_url.startswith("http"):
            return video_url

        return None

    @staticmethod
    async def _save_video_bytes(url: str) -> str | None:
        """Download video bytes from URL and save to static storage."""
        try:
            video_bytes = await File(url).aread_bytes()
            video_filename = f"omnihuman_video_{int(time.time())}.mp4"
            GriptapeNodes.StaticFilesManager().save_static_file(video_bytes, video_filename)
        except Exception:
            return None

        return video_filename

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["video_url"] = None
