from __future__ import annotations

import base64
import json as _json
import logging
from contextlib import suppress
from typing import Any

from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsSoundEffectGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MIN_SOUND_DURATION_SEC = 0.5
MAX_SOUND_DURATION_SEC = 30.0


class ElevenLabsSoundEffectGeneration(GriptapeProxyNode):
    """Generate sound effects from text prompts using Eleven Labs API via Griptape model proxy.

    Uses the Eleven Text to Sound v2 model to create custom sound effects from text descriptions.

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated sound effect audio as URL artifact
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate sound effects from text prompts using Eleven Labs"

        # INPUTS / PROPERTIES
        # Text input
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="Text description of the sound effect to generate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the sound effect you want to generate...",
                    "display_name": "Text",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="loop",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Whether to create a smoothly looping sound",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Loop"},
            )
        )

        self.add_parameter(
            Parameter(
                name="sound_duration_seconds",
                input_types=["float"],
                type="float",
                default_value=6.0,
                tooltip="Duration of the sound in seconds (0.5-30.0s, optional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=MIN_SOUND_DURATION_SEC, max_val=MAX_SOUND_DURATION_SEC)},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_influence",
                input_types=["float"],
                type="float",
                default_value=0.3,
                tooltip="Prompt influence (0.0-1.0). Higher values follow prompt more closely. Defaults to 0.3",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Slider(min_val=0.0, max_val=1.0)},
                ui_options={"display_name": "Prompt Influence"},
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
                tooltip="Generated sound effect audio as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status output parameters for success/failure information
        self._create_status_parameters(
            result_details_tooltip="Details about the sound effect generation result or any errors encountered",
            result_details_placeholder="Sound effect generation status will appear here...",
            parameter_group_initially_collapsed=True,
        )

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return "eleven_text_to_sound_v2"

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Eleven Labs sound effect generation."""
        text = self.get_parameter_value("text") or ""
        loop = self.get_parameter_value("loop")
        duration_seconds = self.get_parameter_value("sound_duration_seconds")
        prompt_influence = self.get_parameter_value("prompt_influence")

        params = {"text": text}

        # Add optional parameters if they have values
        if loop is not None:
            params["loop"] = loop
        if duration_seconds is not None:
            params["duration_seconds"] = duration_seconds
        if prompt_influence is not None:
            params["prompt_influence"] = prompt_influence

        # Log request
        self._log_request(params)

        return params

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = payload.copy()
            for key in ["text"]:
                if key in sanitized_payload:
                    text_value = sanitized_payload[key]
                    if isinstance(text_value, str) and len(text_value) > PROMPT_TRUNCATE_LENGTH:
                        sanitized_payload[key] = text_value[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the Eleven Labs sound effect result and set output parameters."""
        # Check if we received raw audio bytes (in case API returns raw bytes)
        audio_bytes_raw = result_json.get("audio_bytes")
        if audio_bytes_raw:
            audio_bytes = audio_bytes_raw
            self._log("Received raw audio bytes from API")
        else:
            # Fall back to base64-encoded audio (expected for this model)
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

        # Save audio
        try:
            filename = f"eleven_sound_{generation_id}.mp3"
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
        self._set_status_results(was_successful=True, result_details="Sound effect generated successfully")

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from Eleven Labs sound effect failed generation response."""
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
