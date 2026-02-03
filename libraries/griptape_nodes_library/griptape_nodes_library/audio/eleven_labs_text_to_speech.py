from __future__ import annotations

import base64
import json as _json
import logging
from contextlib import suppress
from typing import Any

from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_types.parameter_audio import ParameterAudio
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsTextToSpeechGeneration"]

PROMPT_TRUNCATE_LENGTH = 100

# Voice preset mapping - friendly names to Eleven Labs voice IDs (sorted alphabetically)
VOICE_PRESET_MAP = {  # spellchecker:disable-line
    "Alexandra": "kdmDKE6EkgrWrrykO9Qt",  # spellchecker:disable-line
    "Antoni": "ErXwobaYiN019PkySvjV",  # spellchecker:disable-line
    "Austin": "Bj9UqZbhQsanLzgalpEG",  # spellchecker:disable-line
    "Clyde": "2EiwWnXFnvU5JabPnv8n",  # spellchecker:disable-line
    "Dave": "CYw3kZ02Hs0563khs1Fj",  # spellchecker:disable-line
    "Domi": "AZnzlk1XvdvUeBnXmlld",  # spellchecker:disable-line
    "Drew": "29vD33N1CtxCmqQRPOHJ",  # spellchecker:disable-line
    "Fin": "D38z5RcWu1voky8WS1ja",  # spellchecker:disable-line
    "Hope": "tnSpp4vdxKPjI9w0GnoV",  # spellchecker:disable-line
    "James": "EkK5I93UQWFDigLMpZcX",  # spellchecker:disable-line
    "Jane": "RILOU7YmBhvwJGDGjNmP",  # spellchecker:disable-line
    "Paul": "5Q0t7uMcjvnagumLfvZi",  # spellchecker:disable-line
    "Rachel": "21m00Tcm4TlvDq8ikWAM",  # spellchecker:disable-line
    "Sarah": "EXAVITQu4vr4xnSDxMaL",  # spellchecker:disable-line
    "Thomas": "GBv7mTt0atIp3Br8iCZE",  # spellchecker:disable-line
}


class ElevenLabsTextToSpeechGeneration(GriptapeProxyNode):
    """Generate speech from text using Eleven Labs text-to-speech models via Griptape model proxy.

    Supports two models:
    - Eleven Multilingual v2: Text-to-speech with voice options and character alignment
    - Eleven v3: Latest text-to-speech model with voice options and character alignment

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated speech audio as URL artifact
        - alignment (dict): Character alignment data with start/end times
        - normalized_alignment (dict): Normalized character alignment data
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate speech from text using Eleven Labs text-to-speech models"

        # INPUTS / PROPERTIES
        # Model Selection
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="eleven_v3",
                tooltip="Select the Eleven Labs text-to-speech model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["eleven_multilingual_v2", "eleven_v3"])},
                ui_options={"display_name": "Model"},
            )
        )

        # Text input
        self.add_parameter(
            ParameterString(
                name="text",
                tooltip="Text to convert to speech",
                multiline=True,
                placeholder_text="Enter text to convert to speech...",
                allow_output=False,
                ui_options={
                    "display_name": "Text",
                },
            )
        )

        # Voice preset selection
        self.add_parameter(
            ParameterString(
                name="voice_preset",
                default_value="Alexandra",
                tooltip="Select a preset voice or choose 'Custom...' to enter a voice ID",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "Alexandra",
                            "Antoni",
                            "Austin",
                            "Clyde",
                            "Dave",
                            "Domi",
                            "Drew",
                            "Fin",
                            "Hope",
                            "James",
                            "Jane",
                            "Paul",
                            "Rachel",
                            "Sarah",
                            "Thomas",
                            "Custom...",
                        ]
                    )
                },
                ui_options={"display_name": "Voice"},
            )
        )

        # Custom voice ID field (hidden by default)
        self.add_parameter(
            ParameterString(
                name="custom_voice_id",
                tooltip="Enter a custom Eleven Labs voice ID (must be publicly accessible)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                hide=True,
                placeholder_text="e.g., 21m00Tcm4TlvDq8ikWAM",
                ui_options={"display_name": "Custom Voice ID"},
            )
        )

        self.add_parameter(
            ParameterString(
                name="language_code",
                tooltip="ISO 639-1 language code as a hint for pronunciation (optional, defaults to 'en')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                placeholder_text="e.g., en, es, fr",
                ui_options={"display_name": "Language Code"},
            )
        )

        self.add_parameter(
            ParameterInt(
                name="seed",
                default_value=-1,
                tooltip="Seed for reproducible generation (-1 for random seed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])},
                ui_options={"display_name": "Seed"},
            )
        )

        self.add_parameter(
            ParameterString(
                name="previous_text",
                tooltip="Context for what text comes before the generated speech. Helps maintain continuity between consecutive speech generations.",
                multiline=True,
                placeholder_text="Optional: provide text that comes before for continuity...",
                allow_output=False,
                ui_options={
                    "display_name": "Previous Text",
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="next_text",
                tooltip="Context for what text comes after the generated speech. Helps maintain continuity between consecutive speech generations.",
                multiline=True,
                placeholder_text="Optional: provide text that comes after for continuity...",
                allow_output=False,
                ui_options={
                    "display_name": "Next Text",
                },
            )
        )

        # Voice Settings
        with ParameterGroup(name="Voice_Settings", collapsed=True) as voice_settings_group:
            ParameterString(
                name="stability",
                default_value="Natural",
                tooltip="Controls voice consistency. Creative (0.0) = more variable and emotional, Natural (0.5) = balanced, Robust (1.0) = most stable and consistent.",
                allow_input=True,
                allow_property=True,
                allow_output=False,
                traits={Options(choices=["Creative", "Natural", "Robust"])},
            )
            ParameterFloat(
                name="speed",
                default_value=1.0,
                min_val=0.7,
                max_val=1.2,
                slider=True,
                tooltip="Controls speech rate. Default is 1.0 (normal pace). Values below 1.0 slow down speech (minimum 0.7), values above 1.0 speed up speech (maximum 1.2). Extreme values may affect quality.",
                allow_input=True,
                allow_property=True,
                allow_output=False,
            )
        self.add_node_element(voice_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
            )
        )

        self.add_parameter(
            ParameterAudio(
                name="audio_url",
                tooltip="Generated speech audio as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Alignment outputs
        self.add_parameter(
            ParameterDict(
                name="alignment",
                tooltip="Character alignment data with start/end times",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="normalized_alignment",
                tooltip="Normalized character alignment data",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
            )
        )

        # Create status output parameters for success/failure information
        self._create_status_parameters(
            result_details_tooltip="Details about the text-to-speech generation result or any errors encountered",
            result_details_placeholder="Text-to-speech generation status will appear here...",
            parameter_group_initially_collapsed=True,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update parameter visibility based on voice preset selection."""
        if parameter.name == "voice_preset":
            if value == "Custom...":
                self.show_parameter_by_name("custom_voice_id")
            else:
                self.hide_parameter_by_name("custom_voice_id")

        return super().after_value_set(parameter, value)

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model") or "eleven_v3"

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    async def _build_payload(self) -> dict[str, Any]:  # noqa: C901, PLR0912
        """Build the request payload for Eleven Labs TTS generation."""
        text = self.get_parameter_value("text") or ""
        language_code = self.get_parameter_value("language_code")
        seed = self.get_parameter_value("seed")
        previous_text = self.get_parameter_value("previous_text")
        next_text = self.get_parameter_value("next_text")
        stability_str = self.get_parameter_value("stability")
        speed = self.get_parameter_value("speed")

        # Handle voice ID selection based on preset
        voice_preset = self.get_parameter_value("voice_preset")
        voice_id = None
        if voice_preset == "Custom...":
            voice_id = self.get_parameter_value("custom_voice_id")
        elif voice_preset:
            voice_id = VOICE_PRESET_MAP.get(voice_preset)

        model = self.get_parameter_value("model") or "eleven_v3"
        params = {"text": text, "model_id": model}

        # Add optional parameters if they have values
        if voice_id:
            params["voice_id"] = voice_id
        if language_code:
            params["language_code"] = language_code
        if seed is not None and seed != -1:
            params["seed"] = seed
        if previous_text:
            params["previous_text"] = previous_text
        if next_text:
            params["next_text"] = next_text

        # Add voice_settings with stability and speed
        voice_settings = {}

        if stability_str is not None:
            match stability_str:
                case "Creative":
                    voice_settings["stability"] = 0.0
                case "Natural":
                    voice_settings["stability"] = 0.5
                case "Robust":
                    voice_settings["stability"] = 1.0
                case _:
                    msg = f"{self.name} received invalid stability value: {stability_str}. Must be one of: Creative, Natural, or Robust"
                    raise ValueError(msg)

        if speed is not None:
            voice_settings["speed"] = speed

        if voice_settings:
            params["voice_settings"] = voice_settings

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
        """Parse the Eleven Labs TTS result and set output parameters."""
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
            filename = f"eleven_tts_{generation_id}.mp3"
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(audio_bytes, filename, use_direct_save=True)
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

        # Extract alignment data
        alignment = result_json.get("alignment")
        normalized_alignment = result_json.get("normalized_alignment")

        if alignment:
            self.parameter_output_values["alignment"] = alignment
            self._log("Extracted character alignment data")
        else:
            self.parameter_output_values["alignment"] = None

        if normalized_alignment:
            self.parameter_output_values["normalized_alignment"] = normalized_alignment
            self._log("Extracted normalized alignment data")
        else:
            self.parameter_output_values["normalized_alignment"] = None

        # Set success status
        self._set_status_results(was_successful=True, result_details="Speech generated successfully")

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from Eleven Labs TTS failed generation response."""
        # Try top-level details field (ElevenLabs-specific)
        details = response_json.get("details")
        if details:
            return f"{self.name} {details}"

        # Fall back to standard error extraction
        return super()._extract_error_message(response_json)

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["audio_url"] = None
        self.parameter_output_values["alignment"] = None
        self.parameter_output_values["normalized_alignment"] = None
