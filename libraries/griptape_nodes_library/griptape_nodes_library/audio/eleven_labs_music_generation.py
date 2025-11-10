from __future__ import annotations

import json as _json
import logging
import os
import time
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsMusicGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MIN_MUSIC_LENGTH_SEC = 10.0
MAX_MUSIC_LENGTH_SEC = 300.0


class ElevenLabsMusicGeneration(SuccessFailureNode):
    """Generate music from text prompts using Eleven Labs API via Griptape model proxy.

    Uses the Eleven Music v1 model to create custom music from text descriptions.

    Inputs:
        - text (str): Text prompt describing the music to generate
        - music_duration_seconds (float): Duration in seconds (10.0-300.0s)
        - output_format (str): Audio output format (mp3, pcm, opus, etc.)
        - force_instrumental (bool): Ensure output is instrumental without lyrics (default: False)

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated music audio as URL artifact
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate music from text prompts using Eleven Labs"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/models/")

        # INPUTS / PROPERTIES
        # Text input
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the music to generate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the music you want to generate...",
                    "display_name": "Text",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="music_duration_seconds",
                input_types=["float"],
                type="float",
                default_value=30.0,
                tooltip="Duration of the music in seconds (10.0-300.0s)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=MIN_MUSIC_LENGTH_SEC, max_val=MAX_MUSIC_LENGTH_SEC)},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_format",
                input_types=["str"],
                type="str",
                default_value="mp3_44100_128",
                tooltip="Audio output format",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "mp3_22050_32",
                            "mp3_44100_32",
                            "mp3_44100_64",
                            "mp3_44100_96",
                            "mp3_44100_128",
                            "mp3_44100_192",
                            "pcm_8000",
                            "pcm_16000",
                            "pcm_22050",
                            "pcm_24000",
                            "pcm_44100",
                            "pcm_48000",
                            "ulaw_8000",
                            "alaw_8000",
                            "opus_48000_32",
                            "opus_48000_64",
                            "opus_48000_96",
                        ]
                    )
                },
                ui_options={"display_name": "Output Format"},
            )
        )

        self.add_parameter(
            Parameter(
                name="force_instrumental",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Ensure the output music is instrumental without lyrics",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Force Instrumental"},
            )
        )

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
                name="audio_url",
                output_type="AudioUrlArtifact",
                type="AudioUrlArtifact",
                tooltip="Generated music audio as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status output parameters for success/failure information
        self._create_status_parameters(
            result_details_tooltip="Details about the music generation result or any errors encountered",
            result_details_placeholder="Music generation status will appear here...",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that required configuration is available before running the node."""
        errors = []

        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            errors.append(
                ValueError(f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config.")
            )

        return errors or None

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def process(self) -> None:
        pass

    async def aprocess(self) -> None:
        await self._process_async()

    async def _process_async(self) -> None:
        """Async implementation of the processing logic."""
        self._clear_execution_status()

        params = self._get_parameters()
        api_key = self._get_api_key()
        headers = self._build_headers(api_key)

        self._log("Generating music with Eleven Music v1 via Griptape proxy")

        try:
            response_bytes = await self._submit_request(params, headers)
            if response_bytes:
                self._save_audio_from_bytes(response_bytes)
                self.parameter_output_values["generation_id"] = str(int(time.time()))
                self._set_status_results(was_successful=True, result_details="Music generated successfully")
            else:
                self._set_safe_defaults()
                self._set_status_results(was_successful=False, result_details="No audio data received from API")
        except Exception as e:
            self._set_safe_defaults()
            error_message = str(e)
            self._set_status_results(was_successful=False, result_details=error_message)
            self._handle_failure_exception(e)

    def _get_parameters(self) -> dict[str, Any]:
        text = self.get_parameter_value("text") or ""
        duration_seconds = self.get_parameter_value("music_duration_seconds")
        output_format = self.get_parameter_value("output_format") or "mp3_44100_128"
        force_instrumental = self.get_parameter_value("force_instrumental")

        # Convert seconds to milliseconds
        music_length_ms = None
        if duration_seconds is not None:
            music_length_ms = int(duration_seconds * 1000)

        params = {
            "prompt": text,
            "music_length_ms": music_length_ms,
            "output_format": output_format,
        }

        # Add optional force_instrumental parameter if set
        if force_instrumental is not None:
            params["force_instrumental"] = force_instrumental

        return params

    def _get_api_key(self) -> str:
        """Get the API key - validation is done in validate_before_node_run()."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. This should have been caught during validation."
            raise RuntimeError(msg)
        return api_key

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> bytes | None:
        url = urljoin(self._proxy_base, "eleven-music-1-0")

        self._log("Submitting request to Griptape model proxy")
        self._log_request(params)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            error_message = self._parse_error_response(e.response.text, e.response.status_code)
            raise RuntimeError(error_message) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"Request failed: {e}"
            raise RuntimeError(msg) from e

        self._log("Request submitted successfully")
        return response.content

    def _parse_error_response(self, response_text: str, status_code: int) -> str:
        """Parse error response and extract meaningful error information for the user."""
        try:
            error_data = _json.loads(response_text)

            if "provider_response" in error_data:
                provider_response_str = error_data["provider_response"]
                provider_data = _json.loads(provider_response_str)

                if "detail" in provider_data:
                    detail = provider_data["detail"]
                    status = detail.get("status", "")
                    message = detail.get("message", "")

                    if status and message:
                        return f"{status}: {message}"
                    if message:
                        return f"Error: {message}"

            if "error" in error_data:
                return f"Error: {error_data['error']}"

            return f"API Error ({status_code}): {response_text[:200]}"

        except (_json.JSONDecodeError, KeyError, TypeError):
            return f"API Error ({status_code}): Unable to parse error response"

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = payload.copy()
            for key in ["prompt"]:
                if key in sanitized_payload:
                    text_value = sanitized_payload[key]
                    if isinstance(text_value, str) and len(text_value) > PROMPT_TRUNCATE_LENGTH:
                        sanitized_payload[key] = text_value[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _save_audio_from_bytes(self, audio_bytes: bytes) -> None:
        try:
            self._log("Processing audio bytes from proxy response")
            # Determine file extension based on output format
            output_format = self.get_parameter_value("output_format") or "mp3_44100_128"
            if output_format.startswith("mp3_"):
                ext = "mp3"
            elif output_format.startswith(("pcm_", "ulaw_", "alaw_")):
                ext = "wav"
            elif output_format.startswith("opus_"):
                ext = "opus"
            else:
                ext = "mp3"

            filename = f"eleven_music_{int(time.time())}.{ext}"

            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(audio_bytes, filename)
            self.parameter_output_values["audio_url"] = AudioUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved audio to static storage as {filename}")
        except Exception as e:
            self._log(f"Failed to save audio from bytes: {e}")
            self.parameter_output_values["audio_url"] = None

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["audio_url"] = None
