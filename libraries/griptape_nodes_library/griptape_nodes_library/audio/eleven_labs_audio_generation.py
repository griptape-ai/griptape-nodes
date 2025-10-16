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
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.audio.audio_url_artifact import AudioUrlArtifact

logger = logging.getLogger(__name__)

__all__ = ["ElevenLabsAudioGeneration"]

PROMPT_TRUNCATE_LENGTH = 100
MAX_PROMPT_LENGTH = 2000
MIN_MUSIC_LENGTH_MS = 10000
MAX_MUSIC_LENGTH_MS = 300000
MIN_MUSIC_LENGTH_SEC = 10.0
MAX_MUSIC_LENGTH_SEC = 300.0
MIN_SOUND_DURATION_SEC = 0.5
MAX_SOUND_DURATION_SEC = 30.0


class ElevenLabsAudioGeneration(DataNode):
    """Generate audio using Eleven Labs API via Griptape model proxy.

    Supports three models:
    - Eleven Music v1: Music generation from text prompts
    - Eleven Multilingual v2: Text-to-speech with voice options
    - Eleven Text to Sound v2: Text-to-sound effects generation

    Outputs:
        - generation_id (str): Generation ID from the API
        - audio_url (AudioUrlArtifact): Generated audio as URL artifact
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
                default_value="eleven-music-v1",
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

        # Parameters for Eleven Music v1
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
                    "display_name": "Prompt (Music)",
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

        # Parameters for Eleven Multilingual v2 (Text-to-Speech)
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="Text to be converted to speech",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter text to convert to speech...",
                    "display_name": "Text",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="voice_id",
                input_types=["str"],
                type="str",
                tooltip="Voice ID to use for speech generation (optional, null reverts to default)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Voice ID"},
            )
        )

        self.add_parameter(
            Parameter(
                name="language_code",
                input_types=["str"],
                type="str",
                tooltip="ISO 639-1 language code as a hint for pronunciation (optional)",
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
                tooltip="Seed for reproducible generation (optional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Seed"},
            )
        )

        self.add_parameter(
            Parameter(
                name="previous_text",
                input_types=["str"],
                type="str",
                tooltip="Previous text to improve continuity in speech generation (optional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "display_name": "Previous Text",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="next_text",
                input_types=["str"],
                type="str",
                tooltip="Next text to improve continuity in speech generation (optional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "display_name": "Next Text",
                },
            )
        )

        # Parameters for Eleven Text to Sound v2
        self.add_parameter(
            Parameter(
                name="sound_text",
                input_types=["str"],
                type="str",
                tooltip="Text describing the sound effect to generate",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the sound you want to generate...",
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
                default_value=10.0,
                tooltip="Duration of the sound in seconds (0.5-30.0s, optional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Duration (seconds)"},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_influence",
                input_types=["float"],
                type="float",
                tooltip="Prompt influence (0.0-1.0). Higher values follow prompt more closely. Defaults to 0.3",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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

        # Initialize parameter visibility based on default model
        self._initialize_parameter_visibility()

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        default_model = self.get_parameter_value("model") or "eleven-music-v1"
        if default_model == "eleven-music-v1":
            # Show music parameters, hide TTS and sound parameters
            self.show_parameter_by_name("prompt")
            self.show_parameter_by_name("music_duration_seconds")
            self.show_parameter_by_name("output_format")
            self.hide_parameter_by_name("text")
            self.hide_parameter_by_name("voice_id")
            self.hide_parameter_by_name("language_code")
            self.hide_parameter_by_name("seed")
            self.hide_parameter_by_name("previous_text")
            self.hide_parameter_by_name("next_text")
            self.hide_parameter_by_name("sound_text")
            self.hide_parameter_by_name("loop")
            self.hide_parameter_by_name("sound_duration_seconds")
            self.hide_parameter_by_name("prompt_influence")
        elif default_model in {"eleven_multilingual_v2", "eleven_v3"}:
            # Show TTS parameters, hide music and sound parameters
            self.hide_parameter_by_name("prompt")
            self.hide_parameter_by_name("music_duration_seconds")
            self.hide_parameter_by_name("output_format")
            self.show_parameter_by_name("text")
            self.show_parameter_by_name("voice_id")
            self.show_parameter_by_name("language_code")
            self.show_parameter_by_name("seed")
            self.show_parameter_by_name("previous_text")
            self.show_parameter_by_name("next_text")
            self.hide_parameter_by_name("sound_text")
            self.hide_parameter_by_name("loop")
            self.hide_parameter_by_name("sound_duration_seconds")
            self.hide_parameter_by_name("prompt_influence")
        elif default_model == "eleven_text_to_sound_v2":
            # Show sound parameters, hide music and TTS parameters
            self.hide_parameter_by_name("prompt")
            self.hide_parameter_by_name("music_duration_seconds")
            self.hide_parameter_by_name("output_format")
            self.hide_parameter_by_name("text")
            self.hide_parameter_by_name("voice_id")
            self.hide_parameter_by_name("language_code")
            self.hide_parameter_by_name("seed")
            self.hide_parameter_by_name("previous_text")
            self.hide_parameter_by_name("next_text")
            self.show_parameter_by_name("sound_text")
            self.show_parameter_by_name("loop")
            self.show_parameter_by_name("sound_duration_seconds")
            self.show_parameter_by_name("prompt_influence")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update parameter visibility based on model selection."""
        if parameter.name == "model":
            if value == "eleven-music-v1":
                # Show music parameters, hide TTS and sound parameters
                self.show_parameter_by_name("prompt")
                self.show_parameter_by_name("music_duration_seconds")
                self.show_parameter_by_name("output_format")
                self.hide_parameter_by_name("text")
                self.hide_parameter_by_name("voice_id")
                self.hide_parameter_by_name("language_code")
                self.hide_parameter_by_name("seed")
                self.hide_parameter_by_name("previous_text")
                self.hide_parameter_by_name("next_text")
                self.hide_parameter_by_name("sound_text")
                self.hide_parameter_by_name("loop")
                self.hide_parameter_by_name("sound_duration_seconds")
                self.hide_parameter_by_name("prompt_influence")
            elif value in {"eleven_multilingual_v2", "eleven_v3"}:
                # Show TTS parameters, hide music and sound parameters
                self.hide_parameter_by_name("prompt")
                self.hide_parameter_by_name("music_duration_seconds")
                self.hide_parameter_by_name("output_format")
                self.show_parameter_by_name("text")
                self.show_parameter_by_name("voice_id")
                self.show_parameter_by_name("language_code")
                self.show_parameter_by_name("seed")
                self.show_parameter_by_name("previous_text")
                self.show_parameter_by_name("next_text")
                self.hide_parameter_by_name("sound_text")
                self.hide_parameter_by_name("loop")
                self.hide_parameter_by_name("sound_duration_seconds")
                self.hide_parameter_by_name("prompt_influence")
            elif value == "eleven_text_to_sound_v2":
                # Show sound parameters, hide music and TTS parameters
                self.hide_parameter_by_name("prompt")
                self.hide_parameter_by_name("music_duration_seconds")
                self.hide_parameter_by_name("output_format")
                self.hide_parameter_by_name("text")
                self.hide_parameter_by_name("voice_id")
                self.hide_parameter_by_name("language_code")
                self.hide_parameter_by_name("seed")
                self.hide_parameter_by_name("previous_text")
                self.hide_parameter_by_name("next_text")
                self.show_parameter_by_name("sound_text")
                self.show_parameter_by_name("loop")
                self.show_parameter_by_name("sound_duration_seconds")
                self.show_parameter_by_name("prompt_influence")

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
        model = self.get_parameter_value("model") or "eleven-music-v1"
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

        response_bytes = await self._submit_request(model, params, headers)
        if response_bytes:
            self._handle_response(response_bytes, model)
        else:
            self._set_safe_defaults()

    def _get_parameters(self, model: str) -> dict[str, Any]:
        if model == "eleven-music-v1":
            return self._get_music_parameters()
        if model == "eleven_multilingual_v2":
            return self._get_tts_parameters()
        if model == "eleven_v3":
            return self._get_tts_parameters()
        if model == "eleven_text_to_sound_v2":
            return self._get_sound_parameters()
        msg = f"Unknown model: {model}"
        raise ValueError(msg)

    def _get_music_parameters(self) -> dict[str, Any]:
        prompt = self.get_parameter_value("prompt") or ""
        duration_seconds = self.get_parameter_value("music_duration_seconds")
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

    def _get_tts_parameters(self) -> dict[str, Any]:
        text = self.get_parameter_value("text") or ""
        voice_id = self.get_parameter_value("voice_id")
        language_code = self.get_parameter_value("language_code")
        seed = self.get_parameter_value("seed")
        previous_text = self.get_parameter_value("previous_text")
        next_text = self.get_parameter_value("next_text")

        params = {"text": text}

        # Add optional parameters if they have values
        if voice_id:
            params["voice_id"] = voice_id
        if language_code:
            params["language_code"] = language_code
        if seed is not None:
            params["seed"] = seed
        if previous_text:
            params["previous_text"] = previous_text
        if next_text:
            params["next_text"] = next_text

        return params

    def _get_sound_parameters(self) -> dict[str, Any]:
        text = self.get_parameter_value("sound_text") or ""
        loop = self.get_parameter_value("loop")
        duration_seconds = self.get_parameter_value("sound_duration_seconds")
        prompt_influence = self.get_parameter_value("prompt_influence")

        params = {"text": text}

        # Add optional parameters if they have values
        if loop is not None:
            params["loop"] = loop
        if duration_seconds is not None:
            # Validate duration for sound effects
            if duration_seconds < MIN_SOUND_DURATION_SEC:
                duration_seconds = MIN_SOUND_DURATION_SEC
                self._log(f"Duration adjusted to minimum {MIN_SOUND_DURATION_SEC}s")
            elif duration_seconds > MAX_SOUND_DURATION_SEC:
                duration_seconds = MAX_SOUND_DURATION_SEC
                self._log(f"Duration adjusted to maximum {MAX_SOUND_DURATION_SEC}s")
            params["duration_seconds"] = duration_seconds
        if prompt_influence is not None:
            # Validate prompt influence (0.0-1.0)
            if prompt_influence < 0.0:
                prompt_influence = 0.0
                self._log("Prompt influence adjusted to minimum 0.0")
            elif prompt_influence > 1.0:
                prompt_influence = 1.0
                self._log("Prompt influence adjusted to maximum 1.0")
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
            msg = f"{self.name} API error: {e.response.status_code}"
            raise RuntimeError(msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        self._log("Request submitted successfully")
        return response.content

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

    def _handle_response(self, response_bytes: bytes, model: str) -> None:
        if response_bytes:
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
