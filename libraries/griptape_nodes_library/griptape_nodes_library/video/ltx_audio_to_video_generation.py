from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.ffmpeg_utils import get_ffmpeg_path
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXAudioToVideoGeneration"]

MODEL_MAPPING = {
    "LTX 2 Pro": "ltx-2-pro",
}


class LTXAudioToVideoGeneration(GriptapeProxyNode):
    """Generate a video from audio using LTX AI models via Griptape Cloud model proxy.

    Inputs:
        - audio (AudioArtifact|AudioUrlArtifact|str): Input audio (required, base64 data URI format)
        - prompt (str): Text prompt for video generation (required)
        - image (ImageArtifact|ImageUrlArtifact|str): Input image (optional, base64 data URI format)
        - resolution (str): Video resolution (1920x1080)
        - guidance_scale (float): Guidance scale for generation (1-50, optional)

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

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="LTX 2 Pro",
                tooltip="Model to use for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["LTX 2 Pro"])},
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
            Parameter(
                name="audio",
                input_types=["AudioArtifact", "AudioUrlArtifact", "str"],
                type="AudioArtifact",
                tooltip="Input audio for video generation (required). Accepts AudioArtifact, AudioUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Audio"},
            )
        )

        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="Input image for video generation (optional). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Image"},
            )
        )

        self.add_parameter(
            ParameterString(
                name="resolution",
                default_value="1920x1080",
                tooltip="Video resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["1920x1080"])},
            )
        )

        self.add_parameter(
            ParameterFloat(
                name="guidance_scale",
                tooltip="Guidance scale for generation (1-50). Higher values follow the prompt more closely. Leave empty to use the API default.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                min_val=1.0,
                max_val=50.0,
                validate_min_max=True,
                step=0.1,
                ui_options={
                    "placeholder_text": "Optional (e.g., 7.5)",
                },
            )
        )

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
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
                hide=True,
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
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    async def aprocess(self) -> None:
        await super().aprocess()

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
        """Get and process all parameters, including audio and image conversion."""
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "LTX 2 Pro",
            "audio_uri": await self._prepare_audio_data_url_async(self.get_parameter_value("audio")),
            "image_uri": await self._prepare_image_data_url_async(self.get_parameter_value("image")),
            "resolution": self.get_parameter_value("resolution") or "1920x1080",
            "guidance_scale": self.get_parameter_value("guidance_scale"),
        }

    def _get_api_model_id(self) -> str:
        model_name = self.get_parameter_value("model") or "LTX 2 Pro"
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-pro")
        return f"{model_id}:audio-to-video"

    async def _prepare_audio_data_url_async(self, audio_input: Any) -> str | None:
        """Convert audio input to a base64 data URL."""
        if not audio_input:
            return None

        audio_url = self._coerce_audio_url_or_data_uri(audio_input)
        if not audio_url:
            return None

        # If it's already a data URL, normalize the MIME type if needed
        if audio_url.startswith("data:audio/"):
            return self._normalize_audio_data_url(audio_url)

        # If it's an external URL, download and convert to data URL
        if audio_url.startswith(("http://", "https://")):
            downloaded_url = await self._inline_external_url_async(audio_url, "audio/mpeg")
            if downloaded_url:
                return self._normalize_audio_data_url(downloaded_url)
            return None

        return audio_url

    def _normalize_audio_data_url(self, audio_url: str) -> str:
        """Normalize audio data URL to ensure MIME type and codec are supported.

        The LTX API requires audio in specific formats. This method:
        1. Normalizes non-standard MIME types (e.g., audio/x-wav -> audio/wav)
        2. Transcodes audio with unsupported codecs (e.g., pcm_f32le) to MP3

        Supported MIME types: audio/wav, audio/mpeg, audio/mp4, audio/ogg
        Supported codecs: aac, mp3, vorbis, opus, flac

        Args:
            audio_url: Data URL with audio/ prefix

        Returns:
            Normalized data URL with supported MIME type and codec
        """
        # Extract MIME type from data URL (format: data:audio/TYPE;base64,DATA)
        if not audio_url.startswith("data:audio/"):
            return audio_url

        if ";" not in audio_url:
            return audio_url

        parts = audio_url.split(";", 1)
        mime_type = parts[0].replace("data:", "")
        rest = parts[1]

        # Normalize non-standard MIME types
        normalized_mime = self._normalize_audio_mime_type(mime_type)

        if normalized_mime != mime_type:
            logger.info(
                "%s normalized audio MIME type from '%s' to '%s'",
                self.name,
                mime_type,
                normalized_mime,
            )

        # For WAV files, we need to transcode to MP3 because WAV typically contains
        # PCM codec which the API doesn't support. MP3 uses a supported codec.
        if normalized_mime == "audio/wav":
            logger.info(
                "%s transcoding WAV audio to MP3 to ensure codec compatibility",
                self.name,
            )
            try:
                return self._transcode_audio_to_mp3(audio_url)
            except RuntimeError as e:
                logger.warning(
                    "%s failed to transcode audio: %s. Sending as-is and hoping for the best.",
                    self.name,
                    e,
                )
                return f"data:{normalized_mime};{rest}"

        # For other formats, update MIME type if needed
        if normalized_mime != mime_type:
            return f"data:{normalized_mime};{rest}"

        return audio_url

    def _transcode_audio_to_mp3(self, audio_url: str) -> str:
        """Transcode audio data URL to MP3 format using ffmpeg.

        Args:
            audio_url: Data URL with base64-encoded audio data

        Returns:
            Data URL with MP3-encoded audio

        Raises:
            RuntimeError: If transcoding fails
        """
        # Extract base64 data from data URL
        if not audio_url.startswith("data:"):
            error_msg = f"{self.name} invalid data URL format for transcoding"
            raise RuntimeError(error_msg)

        if "base64," not in audio_url:
            error_msg = f"{self.name} data URL must contain base64-encoded data"
            raise RuntimeError(error_msg)

        base64_data = audio_url.split("base64,", 1)[1]

        try:
            audio_bytes = base64.b64decode(base64_data)
        except Exception as e:
            error_msg = f"{self.name} failed to decode base64 audio data: {e}"
            raise RuntimeError(error_msg) from e

        # Create temporary files for input and output
        input_file = None
        output_file = None

        try:
            # Write input audio to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                input_file = Path(f.name)
                f.write(audio_bytes)

            # Create output temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                output_file = Path(f.name)

            # Run ffmpeg to transcode
            try:
                ffmpeg_path = get_ffmpeg_path()
            except RuntimeError as e:
                error_msg = f"{self.name} ffmpeg not available: {e}"
                raise RuntimeError(error_msg) from e

            cmd = [
                ffmpeg_path,
                "-y",  # Overwrite output file
                "-i",
                str(input_file.absolute()),
                "-c:a",
                "libmp3lame",  # Use MP3 codec
                "-b:a",
                "192k",  # Bitrate
                str(output_file.absolute()),
            ]

            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)  # noqa: S603
            if result.returncode != 0:
                error_msg = f"{self.name} ffmpeg transcoding failed: {result.stderr}"
                raise RuntimeError(error_msg)

            # Read transcoded audio
            try:
                with output_file.open("rb") as f:
                    mp3_bytes = f.read()
            except OSError as e:
                error_msg = f"{self.name} failed to read transcoded audio: {e}"
                raise RuntimeError(error_msg) from e

            # Encode to base64 and create data URL
            mp3_base64 = base64.b64encode(mp3_bytes).decode("utf-8")
            return f"data:audio/mpeg;base64,{mp3_base64}"

        finally:
            # Clean up temp files
            if input_file and input_file.exists():
                with suppress(Exception):
                    input_file.unlink()
            if output_file and output_file.exists():
                with suppress(Exception):
                    output_file.unlink()

    @staticmethod
    def _normalize_audio_mime_type(mime_type: str) -> str:
        """Normalize audio MIME type to standard format.

        Args:
            mime_type: Original MIME type

        Returns:
            Normalized MIME type
        """
        # Map of non-standard to standard MIME types
        mime_type_map = {
            "audio/x-wav": "audio/wav",
            "audio/wave": "audio/wav",
            "audio/x-mpeg": "audio/mpeg",
            "audio/mp3": "audio/mpeg",
            "audio/x-mp4": "audio/mp4",
            "audio/m4a": "audio/mp4",
            "audio/x-ogg": "audio/ogg",
            "audio/ogg-vorbis": "audio/ogg",
        }

        return mime_type_map.get(mime_type, mime_type)

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
            return await self._inline_external_url_async(image_url, "image/jpeg")

        return image_url

    async def _inline_external_url_async(self, url: str, default_content_type: str) -> str | None:
        """Download external URL and convert to base64 data URL."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.debug("%s failed to inline URL: %s", self.name, e)
                return None
            else:
                import base64

                content_type = (resp.headers.get("content-type") or default_content_type).split(";")[0]
                if not content_type.startswith(("image/", "audio/")):
                    content_type = default_content_type
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("URL converted to base64 data URI for proxy")
                return f"data:{content_type};base64,{b64}"

    @staticmethod
    def _coerce_audio_url_or_data_uri(val: Any) -> str | None:
        """Convert various audio input types to a URL or data URI string."""
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:audio/")) else f"data:audio/mpeg;base64,{v}"

        # Artifact-like objects
        try:
            # AudioUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:audio/")):
                return v
            # AudioArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:audio/") else f"data:audio/mpeg;base64,{b64}"
        except AttributeError:
            pass

        return None

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

        if not params["audio_uri"]:
            raise ValueError(f"{self.name} requires an input audio for video generation.")

        if not params["prompt"].strip():
            raise ValueError(f"{self.name} requires a prompt to generate video.")

        model_id = MODEL_MAPPING.get(params["model"], "ltx-2-pro")
        payload: dict[str, Any] = {
            "audio_uri": params["audio_uri"],
            "prompt": params["prompt"].strip(),
            "model": model_id,
            "resolution": params["resolution"],
        }
        if params["image_uri"]:
            payload["image_uri"] = params["image_uri"]
        if params["guidance_scale"] is not None:
            payload["guidance_scale"] = params["guidance_scale"]

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
            filename = f"ltx_audio_to_video_{generation_id}.mp4"
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
