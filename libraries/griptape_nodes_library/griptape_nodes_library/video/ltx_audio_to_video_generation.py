from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import os
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.ffmpeg_utils import get_ffmpeg_path

logger = logging.getLogger("griptape_nodes")

__all__ = ["LTXAudioToVideoGeneration"]

# Constants
HTTP_CLIENT_ERROR_STATUS = 400
MODEL_MAPPING = {
    "LTX 2 Pro": "ltx-2-pro",
}


class LTXAudioToVideoGeneration(SuccessFailureNode):
    """Generate a video from audio using LTX AI models via Griptape Cloud model proxy.

    Inputs:
        - audio (AudioArtifact|AudioUrlArtifact|str): Input audio (required, base64 data URI format)
        - prompt (str): Text prompt for video generation (required)
        - image (ImageArtifact|ImageUrlArtifact|str): Input image (optional, base64 data URI format)
        - resolution (str): Video resolution (1920x1080)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

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
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()
        logger.info("%s starting video generation", self.name)

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            logger.error("%s API key validation failed: %s", self.name, e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Get parameters and validate
        params = await self._get_parameters_async()
        logger.debug(
            "%s parameters: model=%s, prompt_length=%d, resolution=%s",
            self.name,
            params["model"],
            len(params["prompt"]),
            params["resolution"],
        )

        # Validate audio is provided
        if not params["audio_uri"]:
            self._set_safe_defaults()
            error_msg = f"{self.name} requires an input audio for video generation."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: no audio provided", self.name)
            return

        # Validate prompt is provided
        if not params["prompt"].strip():
            self._set_safe_defaults()
            error_msg = f"{self.name} requires a prompt to generate video."
            self._set_status_results(was_successful=False, result_details=error_msg)
            logger.error("%s validation failed: empty prompt", self.name)
            return

        # Build payload
        payload = self._build_payload(params)

        # Submit request
        try:
            generation_id = await self._submit_request_async(params["model"], payload, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result_async(generation_id, headers)

    async def _get_parameters_async(self) -> dict[str, Any]:
        """Get and process all parameters, including audio and image conversion."""
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "model": self.get_parameter_value("model") or "LTX 2 Pro",
            "audio_uri": await self._prepare_audio_data_url_async(self.get_parameter_value("audio")),
            "image_uri": await self._prepare_image_data_url_async(self.get_parameter_value("image")),
            "resolution": self.get_parameter_value("resolution") or "1920x1080",
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

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

    async def _submit_request_async(self, model_name: str, payload: dict[str, Any], headers: dict[str, str]) -> str:
        model_id = MODEL_MAPPING.get(model_name, "ltx-2-pro")
        model_id_with_modality = f"{model_id}:audio-to-video"
        post_url = urljoin(self._proxy_base, f"models/{model_id_with_modality}")

        logger.info("Submitting request to proxy model=%s", model_id_with_modality)
        self._log_request(post_url, headers, payload)

        async with httpx.AsyncClient() as client:
            try:
                post_resp = await client.post(post_url, json=payload, headers=headers, timeout=60)
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                self._set_safe_defaults()
                msg = f"{self.name} failed to submit request: {e}"
                raise RuntimeError(msg) from e

            if post_resp.status_code >= HTTP_CLIENT_ERROR_STATUS:
                self._set_safe_defaults()
                logger.error(
                    "Proxy POST error status=%d headers=%s body=%s",
                    post_resp.status_code,
                    dict(post_resp.headers),
                    post_resp.text,
                )
                try:
                    error_json = post_resp.json()
                    error_details = self._extract_error_from_initial_response(error_json)
                    msg = f"{self.name} request failed: {error_details}"
                except (ValueError, _json.JSONDecodeError):
                    msg = f"{self.name} request failed: HTTP {post_resp.status_code} - {post_resp.text}"
                raise RuntimeError(msg)

            try:
                post_json = post_resp.json()
            except (ValueError, _json.JSONDecodeError) as e:
                self._set_safe_defaults()
                msg = f"{self.name} received invalid JSON response: {e}"
                raise RuntimeError(msg) from e

            generation_id = str(post_json.get("generation_id") or "")

            if generation_id:
                logger.info("Submitted. generation_id=%s", generation_id)
                self.parameter_output_values["generation_id"] = generation_id
            else:
                logger.error("No generation_id returned from POST response")

            return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the request payload for LTX API."""
        model_id = MODEL_MAPPING.get(params["model"], "ltx-2-pro")
        payload: dict[str, Any] = {
            "audio_uri": params["audio_uri"],
            "prompt": params["prompt"].strip(),
            "model": model_id,
            "resolution": params["resolution"],
        }
        if params["image_uri"]:
            payload["image_uri"] = params["image_uri"]

        return payload

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        # Redact base64 data from logs
        sanitized_payload = {**payload}
        if "image_uri" in sanitized_payload and isinstance(sanitized_payload["image_uri"], str):
            image_uri = sanitized_payload["image_uri"]
            if image_uri.startswith("data:image/"):
                parts = image_uri.split(",", 1)
                header = parts[0] if parts else "data:image/"
                b64_len = len(parts[1]) if len(parts) > 1 else 0
                sanitized_payload["image_uri"] = f"{header},<base64 data length={b64_len}>"
        if "audio_uri" in sanitized_payload and isinstance(sanitized_payload["audio_uri"], str):
            audio_uri = sanitized_payload["audio_uri"]
            if audio_uri.startswith("data:audio/"):
                parts = audio_uri.split(",", 1)
                header = parts[0] if parts else "data:audio/"
                b64_len = len(parts[1]) if len(parts) > 1 else 0
                sanitized_payload["audio_uri"] = f"{header},<base64 data length={b64_len}>"

        with suppress(Exception):
            logger.debug("POST %s\nheaders=%s\nbody=%s", url, dbg_headers, _json.dumps(sanitized_payload, indent=2))

    async def _poll_for_result_async(self, generation_id: str, headers: dict[str, str]) -> None:
        status_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 1200.0

        async with httpx.AsyncClient() as client:
            while True:
                if monotonic() - start_time > timeout_s:
                    self._handle_polling_timeout()
                    return

                try:
                    status_resp = await client.get(status_url, headers=headers, timeout=60)
                    status_resp.raise_for_status()
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    self._handle_polling_error(exc)
                    return

                try:
                    status_json = status_resp.json()
                except (ValueError, _json.JSONDecodeError) as exc:
                    error_msg = f"Invalid JSON response during polling: {exc}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    self._handle_failure_exception(RuntimeError(error_msg))
                    return

                self.parameter_output_values["provider_response"] = status_json

                with suppress(Exception):
                    logger.debug("GET status attempt #%d: %s", attempt + 1, _json.dumps(status_json, indent=2))

                attempt += 1

                # Check status field for generation state
                status = status_json.get("status", "").upper()
                logger.info("%s polling attempt #%d status=%s", self.name, attempt, status)

                # Handle terminal states
                if status == "COMPLETED":
                    await self._fetch_and_handle_result(client, generation_id, headers)
                    return

                if status in ("FAILED", "ERRORED"):
                    self._handle_generation_failure(status_json, status)
                    return

                # Continue polling for in-progress states (QUEUED, RUNNING)
                if status in ("QUEUED", "RUNNING"):
                    await asyncio.sleep(poll_interval_s)
                    continue

                # Unknown status - log and continue polling
                logger.warning("%s unknown status '%s', continuing to poll", self.name, status)
                await asyncio.sleep(poll_interval_s)

    def _handle_polling_timeout(self) -> None:
        self.parameter_output_values["video_url"] = None
        logger.error("%s polling timed out waiting for result", self.name)
        self._set_status_results(
            was_successful=False,
            result_details="Video generation timed out after 1200 seconds waiting for result.",
        )

    def _handle_polling_error(self, exc: Exception) -> None:
        logger.error("%s GET generation status failed: %s", self.name, exc)
        error_msg = f"Failed to poll generation status: {exc}"
        self._set_status_results(was_successful=False, result_details=error_msg)
        self._handle_failure_exception(RuntimeError(error_msg))

    async def _fetch_and_handle_result(
        self, client: httpx.AsyncClient, generation_id: str, headers: dict[str, str]
    ) -> None:
        logger.info("%s generation completed, fetching result", self.name)
        result_url = urljoin(self._proxy_base, f"generations/{generation_id}/result")

        try:
            result_resp = await client.get(result_url, headers=headers, timeout=120)
            result_resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.error("%s failed to fetch result: %s", self.name, exc)
            error_msg = f"Generation completed but failed to fetch result: {exc}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(RuntimeError(error_msg))
            return

        # The /result endpoint returns raw binary MP4 data (application/octet-stream)
        video_bytes = result_resp.content
        logger.info("%s received video data: %d bytes", self.name, len(video_bytes))
        await self._handle_completion_async(video_bytes, generation_id)

    def _handle_generation_failure(self, status_json: dict[str, Any], status: str) -> None:
        # Extract error details from status_detail
        status_detail = status_json.get("status_detail", {})
        if isinstance(status_detail, dict):
            error = status_detail.get("error", "")
            details = status_detail.get("details", "")

            # If details is a JSON string, try to parse it and extract clean error message
            if details and isinstance(details, str):
                try:
                    details_obj = _json.loads(details)
                    if isinstance(details_obj, dict):
                        # Try to extract .error.message from parsed JSON
                        error_obj = details_obj.get("error")
                        if isinstance(error_obj, dict):
                            clean_message = error_obj.get("message")
                            if clean_message:
                                details = clean_message

                except (ValueError, _json.JSONDecodeError):
                    pass

            if error and details:
                message = f"{error}: {details}"
            elif error:
                message = error
            elif details:
                message = details
            else:
                message = f"Generation {status.lower()} with no details provided"
        else:
            message = f"Generation {status.lower()} with no details provided"

        logger.error("%s generation %s: %s", self.name, status.lower(), message)
        self.parameter_output_values["video_url"] = None
        self._set_status_results(
            was_successful=False, result_details=f"{self.name} generation {status.lower()}: {message}"
        )

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

    def _extract_error_from_initial_response(self, response_json: dict[str, Any]) -> str:
        """Extract error details from initial POST response.

        Expected error shape from API:
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Prompt exceeds 5000 characters limit"
            }
        }
        """
        if not response_json:
            return "No error details provided by API."

        # Try to extract .error.message
        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                # Try to get the message field
                message = error.get("message")
                if message:
                    return str(message)

                # If no message but there's a type, include it
                error_type = error.get("type")
                if error_type:
                    return f"API error: {error_type}"

            # If error is just a string
            if isinstance(error, str):
                return error

        # Fallback: return full JSON response
        return f"Request failed: {_json.dumps(response_json)}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None
