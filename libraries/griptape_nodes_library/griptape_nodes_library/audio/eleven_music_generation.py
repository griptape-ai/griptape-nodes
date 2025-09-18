from __future__ import annotations

import json as _json
import logging
import os
import time
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, DataNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact

logger = logging.getLogger(__name__)

__all__ = ["ElevenMusicGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MAX_PROMPT_LENGTH = 2000
MIN_MUSIC_LENGTH_MS = 10000
MAX_MUSIC_LENGTH_MS = 300000
MIN_MUSIC_LENGTH_SEC = 10.0
MAX_MUSIC_LENGTH_SEC = 300.0


class ElevenMusicGeneration(DataNode):
    """Generate music using Eleven Labs Music Generation API via Griptape model proxy.

    Inputs:
        - prompt (str): Text prompt describing the music to generate (max 2000 characters)
        - duration_seconds (float): Duration of the music in seconds (10.0-300.0s, optional)
        - output_format (str): Audio output format (e.g., mp3_44100_128, pcm_44100)

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated music as URL artifact
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate music using Eleven Labs Music Generation API via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/models/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt describing the music to generate (max 2000 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the music you want to generate...",
                    "display_name": "Prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="duration_seconds",
                input_types=["float"],
                type="float",
                default_value=30.0,
                tooltip="Duration of the music in seconds (10.0-300.0s)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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
                tooltip="Generated music as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that required configuration is available before running the node."""
        errors = []

        # Check if API key is available
        api_key = self.get_config_value(service=self.SERVICE_NAME, value=self.API_KEY_NAME)
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
        params = self._get_parameters()
        api_key = self._get_api_key()
        headers = self._build_headers(api_key)

        self._log("Generating music with Eleven Labs Music Generation via Griptape proxy")

        response_bytes = await self._submit_request(params, headers)
        if response_bytes:
            self._handle_response(response_bytes)
        else:
            self._set_safe_defaults()

    def _get_parameters(self) -> dict[str, Any]:
        prompt = self.get_parameter_value("prompt") or ""
        duration_seconds = self.get_parameter_value("duration_seconds")
        output_format = self.get_parameter_value("output_format") or "mp3_44100_128"

        # Validate prompt length
        if len(prompt) > MAX_PROMPT_LENGTH:
            prompt = prompt[:MAX_PROMPT_LENGTH]
            self._log(f"Prompt truncated to {MAX_PROMPT_LENGTH} characters")

        # Convert seconds to milliseconds and validate
        music_length_ms = None
        if duration_seconds is not None:
            if duration_seconds < MIN_MUSIC_LENGTH_SEC:
                duration_seconds = MIN_MUSIC_LENGTH_SEC
                self._log(f"Duration adjusted to minimum {MIN_MUSIC_LENGTH_SEC}s")
            elif duration_seconds > MAX_MUSIC_LENGTH_SEC:
                duration_seconds = MAX_MUSIC_LENGTH_SEC
                self._log(f"Duration adjusted to maximum {MAX_MUSIC_LENGTH_SEC}s")

            music_length_ms = int(duration_seconds * 1000)

        return {
            "prompt": prompt,
            "music_length_ms": music_length_ms,
            "output_format": output_format,
        }

    def _get_api_key(self) -> str:
        """Get the API key - validation is done in validate_before_node_run()."""
        api_key = self.get_config_value(service=self.SERVICE_NAME, value=self.API_KEY_NAME)
        if not api_key:
            # This should not happen if validate_before_node_run() was called
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
        model_id = "eleven-music-1-0"
        url = urljoin(self._proxy_base, model_id)
        payload = self._build_payload(params)

        self._log(f"Submitting request to Griptape model proxy with model: {model_id}")
        self._log_request(payload)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            msg = f"{self.name} API error: {e.response.status_code}"
            raise RuntimeError(msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        self._log("Request submitted successfully")
        return response.content

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "prompt": params["prompt"],
            "output_format": params["output_format"],
        }

        if params["music_length_ms"] is not None:
            payload["music_length_ms"] = params["music_length_ms"]

        return payload

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = payload.copy()
            prompt = sanitized_payload.get("prompt", "")
            if len(prompt) > PROMPT_TRUNCATE_LENGTH:
                sanitized_payload["prompt"] = prompt[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _handle_response(self, response_bytes: bytes) -> None:
        if response_bytes:
            self._save_audio_from_bytes(response_bytes)
        else:
            self._log("No audio data in response")
            self.parameter_output_values["audio_url"] = None

        # Set generation ID (using timestamp since proxy doesn't provide one)
        self.parameter_output_values["generation_id"] = str(int(time.time()))

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
                ext = "mp3"  # fallback

            filename = f"eleven_music_{int(time.time())}.{ext}"

            from griptape_nodes.retained_mode.retained_mode import GriptapeNodes

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
