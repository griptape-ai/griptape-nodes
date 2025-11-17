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
from griptape.artifacts.audio_url_artifact import AudioUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

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


class ElevenLabsTextToSpeechGeneration(SuccessFailureNode):
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

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate speech from text using Eleven Labs text-to-speech models"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
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
                tooltip="Select the Eleven Labs text-to-speech model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["eleven_multilingual_v2", "eleven_v3"])},
                ui_options={"display_name": "Model"},
            )
        )

        # Text input
        self.add_parameter(
            Parameter(
                name="text",
                input_types=["str"],
                type="str",
                tooltip="Text to convert to speech",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter text to convert to speech...",
                    "display_name": "Text",
                },
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
                tooltip="Generated speech audio as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Alignment outputs
        self.add_parameter(
            Parameter(
                name="alignment",
                output_type="dict",
                type="dict",
                tooltip="Character alignment data with start/end times",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="normalized_alignment",
                output_type="dict",
                type="dict",
                tooltip="Normalized character alignment data",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        # Create status output parameters for success/failure information
        self._create_status_parameters(
            result_details_tooltip="Details about the text-to-speech generation result or any errors encountered",
            result_details_placeholder="Text-to-speech generation status will appear here...",
            parameter_group_initially_collapsed=False,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update parameter visibility based on voice preset selection."""
        if parameter.name == "voice_preset":
            if value == "Custom...":
                self.show_parameter_by_name("custom_voice_id")
            else:
                self.hide_parameter_by_name("custom_voice_id")

        return super().after_value_set(parameter, value)

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

        model = self.get_parameter_value("model") or "eleven_v3"

        try:
            params = self._get_parameters(model)
        except Exception as e:
            self._set_safe_defaults()
            error_message = str(e)
            self._set_status_results(was_successful=False, result_details=error_message)
            self._handle_failure_exception(e)
            # EARLY OUT OF PROCESS.
            return

        api_key = self._get_api_key()
        headers = self._build_headers(api_key)

        model_names = {
            "eleven_multilingual_v2": "Eleven Multilingual v2",
            "eleven_v3": "Eleven v3",
        }
        self._log(f"Generating speech with {model_names.get(model, model)} via Griptape proxy")

        try:
            response_bytes = await self._submit_request(model, params, headers)
            if response_bytes:
                self._handle_response(response_bytes)
                self._set_status_results(was_successful=True, result_details="Speech generated successfully")
            else:
                self._set_safe_defaults()
                self._set_status_results(was_successful=False, result_details="No audio data received from API")
        except Exception as e:
            self._set_safe_defaults()
            error_message = str(e)
            self._set_status_results(was_successful=False, result_details=error_message)
            self._handle_failure_exception(e)

    def _get_parameters(self, model: str) -> dict[str, Any]:  # noqa: C901, PLR0912
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

    async def _submit_request(self, model: str, params: dict[str, Any], headers: dict[str, str]) -> bytes | None:
        # Map model names to proxy model IDs
        model_id_map = {
            "eleven_multilingual_v2": "eleven_multilingual_v2",
            "eleven_v3": "eleven_v3",
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
            for key in ["text"]:
                if key in sanitized_payload:
                    text_value = sanitized_payload[key]
                    if isinstance(text_value, str) and len(text_value) > PROMPT_TRUNCATE_LENGTH:
                        sanitized_payload[key] = text_value[:PROMPT_TRUNCATE_LENGTH] + "..."

            self._log(f"Request payload: {_json.dumps(sanitized_payload, indent=2)}")

    def _handle_response(self, response_bytes: bytes) -> None:
        """Handle JSON response format with base64 audio and alignment data."""
        try:
            response_data = _json.loads(response_bytes.decode("utf-8"))

            # Extract and decode base64 audio
            audio_base64 = response_data.get("audio_base64")
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                self._save_audio_from_bytes(audio_bytes)
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

        # Set generation ID (using timestamp since proxy doesn't provide one)
        self.parameter_output_values["generation_id"] = str(int(time.time()))

    def _save_audio_from_bytes(self, audio_bytes: bytes) -> None:
        try:
            self._log("Processing audio bytes from proxy response")
            filename = f"eleven_tts_{int(time.time())}.mp3"

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
