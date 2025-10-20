from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsAudioGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MIN_MUSIC_LENGTH_MS = 10000
MAX_MUSIC_LENGTH_MS = 300000
MIN_MUSIC_LENGTH_SEC = 10.0
MAX_MUSIC_LENGTH_SEC = 300.0
MIN_SOUND_DURATION_SEC = 0.5
MAX_SOUND_DURATION_SEC = 30.0

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

# Model-specific parameter visibility mapping
MODEL_PARAMETERS = {
    "eleven-music-v1": ["text", "music_duration_seconds", "output_format"],
    "eleven_multilingual_v2": [
        "text",
        "voice_preset",
        "custom_voice_id",
        "language_code",
        "seed",
        "previous_text",
        "next_text",
    ],
    "eleven_v3": ["text", "voice_preset", "custom_voice_id", "language_code", "seed", "previous_text", "next_text"],
    "eleven_text_to_sound_v2": ["text", "loop", "sound_duration_seconds", "prompt_influence"],
}


class ElevenLabsAudioGeneration(SuccessFailureNode):
    """Generate audio using Eleven Labs API via Griptape model proxy.

    Supports three models:
    - Eleven Music v1: Music generation from text prompts
    - Eleven Multilingual v2: Text-to-speech with voice options and character alignment
    - Eleven Text to Sound v2: Text-to-sound effects generation

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated audio as URL artifact
        - alignment (dict): Character alignment data (eleven_multilingual_v2 only)
        - normalized_alignment (dict): Normalized alignment data (eleven_multilingual_v2 only)
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate audio using Eleven Labs API via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/models/")

        # INPUTS / PROPERTIES
        # Model Selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="eleven_v3",
                tooltip="Select the Eleven Labs model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[
                            "eleven-music-v1",
                            "eleven_multilingual_v2",
                            "eleven_v3",
                            "eleven_text_to_sound_v2",
                        ]
                    )
                },
                ui_options={"display_name": "Model"},
            )
        )

        # Common text input parameter used across all models
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="Text input for generation (prompt for music/sounds, or text for speech)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter text prompt or speech text...",
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

        # Voice preset selection
        self.add_parameter(
            Parameter(
                name="voice_preset",
                input_types=["str"],
                type="str",
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
            Parameter(
                name="custom_voice_id",
                input_types=["str"],
                type="str",
                tooltip="Enter a custom Eleven Labs voice ID (must be publicly accessible)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Custom Voice ID",
                    "hide": True,
                    "placeholder_text": "e.g., 21m00Tcm4TlvDq8ikWAM",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="language_code",
                input_types=["str"],
                type="str",
                tooltip="ISO 639-1 language code as a hint for pronunciation (optional, defaults to 'en')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Language Code",
                    "placeholder_text": "e.g., en, es, fr",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                default_value=-1,
                tooltip="Seed for reproducible generation (-1 for random seed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Seed"},
            )
        )

        self.add_parameter(
            Parameter(
                name="previous_text",
                input_types=["str"],
                type="str",
                tooltip="Context for what text comes before the generated speech. Helps maintain continuity between consecutive speech generations.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "display_name": "Previous Text",
                    "placeholder_text": "Optional: provide text that comes before for continuity...",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="next_text",
                input_types=["str"],
                type="str",
                tooltip="Context for what text comes after the generated speech. Helps maintain continuity between consecutive speech generations.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "display_name": "Next Text",
                    "placeholder_text": "Optional: provide text that comes after for continuity...",
                },
            )
        )

        # Parameters for Eleven Text to Sound v2
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

        # Alignment outputs (only populated for eleven_multilingual_v2)
        self.add_parameter(
            Parameter(
                name="alignment",
                output_type="dict",
                type="dict",
                tooltip="Character alignment data with start/end times (eleven_multilingual_v2 only)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="normalized_alignment",
                output_type="dict",
                type="dict",
                tooltip="Normalized character alignment data (eleven_multilingual_v2 only)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        # Create status output parameters for success/failure information
        self._create_status_parameters(
            result_details_tooltip="Details about the audio generation result or any errors encountered",
            result_details_placeholder="Audio generation status will appear here...",
            parameter_group_initially_collapsed=False,
        )

        # Initialize parameter visibility based on default model
        self._initialize_parameter_visibility()

    def _update_parameter_visibility(self, model: str) -> None:
        """Update parameter visibility based on selected model.

        Args:
            model: The selected model name
        """
        # Get all parameter names across all models
        all_parameters = set()
        for params in MODEL_PARAMETERS.values():
            all_parameters.update(params)

        # Get parameters for the selected model
        visible_parameters = set(MODEL_PARAMETERS.get(model, []))

        # Show parameters for this model, hide all others
        for param_name in all_parameters:
            if param_name in visible_parameters:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

        # Special handling for custom_voice_id - only show if voice_preset is "Custom..."
        if "custom_voice_id" in visible_parameters:
            voice_preset = self.get_parameter_value("voice_preset")
            if voice_preset == "Custom...":
                self.show_parameter_by_name("custom_voice_id")
            else:
                self.hide_parameter_by_name("custom_voice_id")

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model") or "eleven_v3"
        self._update_parameter_visibility(default_model)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update parameter visibility based on model and voice preset selection."""
        if parameter.name == "model":
            self._update_parameter_visibility(value)
        elif parameter.name == "voice_preset":
            # Show/hide custom voice ID field based on preset selection
            if value == "Custom...":
                self.show_parameter_by_name("custom_voice_id")
            else:
                self.hide_parameter_by_name("custom_voice_id")

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that required configuration is available before running the node."""
        errors = []

        # Check if API key is available
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

        model = self.get_parameter_value("model") or "eleven_v3"
        params = self._get_parameters(model)
        api_key = self._get_api_key()
        headers = self._build_headers(api_key)

        model_names = {
            "eleven-music-v1": "Eleven Music v1",
            "eleven_multilingual_v2": "Eleven Multilingual v2",
            "eleven_v3": "Eleven v3",
            "eleven_text_to_sound_v2": "Eleven Text to Sound v2",
        }
        self._log(f"Generating audio with {model_names.get(model, model)} via Griptape proxy")

        try:
            response_bytes = await self._submit_request(model, params, headers)
            if response_bytes:
                self._handle_response(response_bytes, model)
                self._set_status_results(was_successful=True, result_details="Audio generated successfully")
            else:
                self._set_safe_defaults()
                self._set_status_results(was_successful=False, result_details="No audio data received from API")
        except Exception as e:
            self._set_safe_defaults()
            # Set the failure status with the error message BEFORE calling _handle_failure_exception
            # This ensures the user sees the error details in the node's status output
            error_message = str(e)
            self._set_status_results(was_successful=False, result_details=error_message)
            # Now handle the exception - this will either log and continue (if failure output is connected)
            # or raise the exception to crash the flow (if no failure handling is set up)
            self._handle_failure_exception(e)

    def _get_parameters(self, model: str) -> dict[str, Any]:
        if model == "eleven-music-v1":
            return self._get_music_parameters()
        if model == "eleven_multilingual_v2":
            return self._get_tts_parameters(model)
        if model == "eleven_v3":
            return self._get_tts_parameters(model)
        if model == "eleven_text_to_sound_v2":
            return self._get_sound_parameters()
        msg = f"Unknown model: {model}"
        raise ValueError(msg)

    def _get_music_parameters(self) -> dict[str, Any]:
        text = self.get_parameter_value("text") or ""
        duration_seconds = self.get_parameter_value("music_duration_seconds")
        output_format = self.get_parameter_value("output_format") or "mp3_44100_128"

        # Convert seconds to milliseconds
        music_length_ms = None
        if duration_seconds is not None:
            music_length_ms = int(duration_seconds * 1000)

        return {
            "prompt": text,
            "music_length_ms": music_length_ms,
            "output_format": output_format,
        }

    def _get_tts_parameters(self, model: str) -> dict[str, Any]:
        text = self.get_parameter_value("text") or ""
        language_code = self.get_parameter_value("language_code")
        seed = self.get_parameter_value("seed")
        previous_text = self.get_parameter_value("previous_text")
        next_text = self.get_parameter_value("next_text")

        # Handle voice ID selection based on preset
        voice_preset = self.get_parameter_value("voice_preset")
        voice_id = None
        if voice_preset == "Custom...":
            # Use custom voice ID entered by user
            voice_id = self.get_parameter_value("custom_voice_id")
        elif voice_preset:
            # Map preset name to actual voice ID
            voice_id = VOICE_PRESET_MAP.get(voice_preset)

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

        return params

    def _get_sound_parameters(self) -> dict[str, Any]:
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

        return params

    def _get_api_key(self) -> str:
        """Get the API key - validation is done in validate_before_node_run()."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
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

    async def _submit_request(self, model: str, params: dict[str, Any], headers: dict[str, str]) -> bytes | None:
        # Map model names to proxy model IDs
        model_id_map = {
            "eleven-music-v1": "eleven-music-1-0",
            "eleven_multilingual_v2": "eleven_multilingual_v2",
            "eleven_v3": "eleven_v3",
            "eleven_text_to_sound_v2": "eleven_text_to_sound_v2",
        }
        model_id = model_id_map.get(model, model)
        url = urljoin(self._proxy_base, model_id)

        self._log(f"Submitting request to Griptape model proxy with model: {model_id}")
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
        """Parse error response and extract meaningful error information for the user.

        Args:
            response_text: The raw response text from the API
            status_code: The HTTP status code

        Returns:
            A user-friendly error message
        """
        try:
            # Try to parse the response as JSON
            error_data = _json.loads(response_text)

            # Check if there's a provider_response field
            if "provider_response" in error_data:
                # The provider_response is a JSON string that needs to be parsed
                provider_response_str = error_data["provider_response"]
                provider_data = _json.loads(provider_response_str)

                # Extract detail.status and detail.message if available
                if "detail" in provider_data:
                    detail = provider_data["detail"]
                    status = detail.get("status", "")
                    message = detail.get("message", "")

                    if status and message:
                        # Format a user-friendly error message
                        return f"{status}: {message}"
                    if message:
                        return f"Error: {message}"

            # Fall back to the error field if provider_response isn't available
            if "error" in error_data:
                return f"Error: {error_data['error']}"

            # If we got here, we have JSON but couldn't extract useful info
            return f"API Error ({status_code}): {response_text[:200]}"

        except (_json.JSONDecodeError, KeyError, TypeError):
            # If parsing fails, return a generic error with the status code
            return f"API Error ({status_code}): Unable to parse error response"

    def _log_request(self, payload: dict[str, Any]) -> None:
        with suppress(Exception):
            sanitized_payload = payload.copy()
            # Truncate any text fields for logging
            for key in ["prompt", "text"]:
                if key in sanitized_payload:
                    text_value = sanitized_payload[key]
                    if isinstance(text_value, str) and len(text_value) > PROMPT_TRUNCATE_LENGTH:
                        sanitized_payload[key] = text_value[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _handle_json_response(self, response_bytes: bytes, model: str) -> None:
        """Handle JSON response format with base64 audio and alignment data.

        This is used for eleven_multilingual_v2 model which returns:
        {
            "audio_base64": "...",
            "alignment": {...},
            "normalized_alignment": {...}
        }
        """
        try:
            # Parse JSON response
            response_data = _json.loads(response_bytes.decode("utf-8"))

            # Extract and decode base64 audio
            audio_base64 = response_data.get("audio_base64")
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                self._save_audio_from_bytes(audio_bytes, model)
            else:
                self._log("No audio_base64 in JSON response")
                self.parameter_output_values["audio_url"] = None

            # Extract alignment data
            alignment = response_data.get("alignment")
            normalized_alignment = response_data.get("normalized_alignment")

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

        except _json.JSONDecodeError as e:
            self._log(f"Failed to parse JSON response: {e}")
            self.parameter_output_values["audio_url"] = None
            self.parameter_output_values["alignment"] = None
            self.parameter_output_values["normalized_alignment"] = None
            raise
        except Exception as e:
            self._log(f"Failed to process JSON response: {e}")
            self.parameter_output_values["audio_url"] = None
            self.parameter_output_values["alignment"] = None
            self.parameter_output_values["normalized_alignment"] = None
            raise

    def _handle_response(self, response_bytes: bytes, model: str) -> None:
        # For eleven_multilingual_v2, we get JSON with base64 audio and alignment data
        if model == "eleven_multilingual_v2":
            self._handle_json_response(response_bytes, model)
        elif response_bytes:
            # For other models, we get raw audio bytes
            self._save_audio_from_bytes(response_bytes, model)
        else:
            self._log("No audio data in response")
            self.parameter_output_values["audio_url"] = None

        # Set generation ID (using timestamp since proxy doesn't provide one)
        self.parameter_output_values["generation_id"] = str(int(time.time()))

    def _save_audio_from_bytes(self, audio_bytes: bytes, model: str) -> None:
        try:
            self._log("Processing audio bytes from proxy response")
            # Determine file extension based on model and output format
            ext = "mp3"  # Default extension
            prefix = "eleven_audio"

            if model == "eleven-music-v1":
                output_format = self.get_parameter_value("output_format") or "mp3_44100_128"
                if output_format.startswith("mp3_"):
                    ext = "mp3"
                elif output_format.startswith(("pcm_", "ulaw_", "alaw_")):
                    ext = "wav"
                elif output_format.startswith("opus_"):
                    ext = "opus"
                prefix = "eleven_music"
            elif model in {"eleven_multilingual_v2", "eleven_v3"}:
                ext = "mp3"  # Output format is mp3_44100_128
                prefix = "eleven_tts"
            elif model == "eleven_text_to_sound_v2":
                ext = "mp3"  # Output format is mp3_44100_128
                prefix = "eleven_sound"

            filename = f"{prefix}_{int(time.time())}.{ext}"

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
        self.parameter_output_values["alignment"] = None
        self.parameter_output_values["normalized_alignment"] = None
