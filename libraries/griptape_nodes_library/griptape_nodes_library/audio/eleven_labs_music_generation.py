from __future__ import annotations

import base64
import json as _json
import logging
from contextlib import suppress
from typing import Any

from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsMusicGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MIN_MUSIC_LENGTH_SEC = 10.0
MAX_MUSIC_LENGTH_SEC = 300.0


class ElevenLabsMusicGeneration(GriptapeProxyNode):
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

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate music from text prompts using Eleven Labs"

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
                hide_property=True,
                hide=True,
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
            parameter_group_initially_collapsed=True,
        )

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return "eleven-music-1-0"

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Eleven Labs music generation."""
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

        # Log request
        self._log_request(params)

        return params

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = payload.copy()
            for key in ["prompt"]:
                if key in sanitized_payload:
                    text_value = sanitized_payload[key]
                    if isinstance(text_value, str) and len(text_value) > PROMPT_TRUNCATE_LENGTH:
                        sanitized_payload[key] = text_value[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the Eleven Labs music result and set output parameters."""
        # Check if we received raw audio bytes (v2 API returns raw bytes for music generation)
        audio_bytes_raw = result_json.get("audio_bytes")
        if audio_bytes_raw:
            audio_bytes = audio_bytes_raw
            self._log("Received raw audio bytes from API")
        else:
            # Fall back to base64-encoded audio if that's what we get
            audio_base64 = result_json.get("audio_base64")
            if not audio_base64:
                self._log("No audio data in response")
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="Generation completed but no audio data was found in the response.",
                )
                return

            try:
                audio_bytes = base64.b64decode(audio_base64)
                self._log("Decoded base64 audio")
            except Exception as e:
                self._log(f"Failed to decode base64 audio: {e}")
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Failed to decode audio data: {e}",
                )
                return

        # Save audio with appropriate file extension
        try:
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

            filename = f"eleven_music_{generation_id}.{ext}"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(audio_bytes, filename)
            self.parameter_output_values["audio_url"] = AudioUrlArtifact(value=saved_url, name=filename)
            self._log(f"Saved audio to static storage as {filename}")
        except Exception as e:
            self._log(f"Failed to save audio: {e}")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"Failed to save audio file: {e}",
            )
            return

        # Set success status
        self._set_status_results(was_successful=True, result_details="Music generated successfully")

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from Eleven Labs music generation failed response."""
        # Try top-level details field (ElevenLabs-specific)
        details = response_json.get("details")
        if details:
            return f"{self.name} {details}"

        # Fall back to standard error extraction
        return super()._extract_error_message(response_json)

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["audio_url"] = None
