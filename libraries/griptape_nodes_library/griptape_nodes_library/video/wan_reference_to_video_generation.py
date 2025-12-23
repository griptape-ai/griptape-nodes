from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["WanReferenceToVideoGeneration"]

# Define constant for prompt truncation length
PROMPT_TRUNCATE_LENGTH = 100

# HTTP status code threshold for error responses
HTTP_ERROR_STATUS = 400

# Model options
MODEL_OPTIONS = [
    "wan2.6-r2v",
]

# Size options organized by resolution tier
SIZE_OPTIONS_720P = [
    "1280*720",  # 16:9
    "720*1280",  # 9:16
    "960*960",  # 1:1
    "1088*832",  # 4:3
    "832*1088",  # 3:4
]

SIZE_OPTIONS_1080P = [
    "1920*1080",  # 16:9
    "1080*1920",  # 9:16
    "1440*1440",  # 1:1
    "1632*1248",  # 4:3
    "1248*1632",  # 3:4
]

ALL_SIZE_OPTIONS = SIZE_OPTIONS_1080P + SIZE_OPTIONS_720P

# Shot type options
SHOT_TYPE_OPTIONS = [
    "single",
    "multi",
]

# Generation status constants
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCELED = "CANCELED"
STATUS_UNKNOWN = "UNKNOWN"


class WanReferenceToVideoGeneration(SuccessFailureNode):
    """Generate videos from reference videos using WAN models via Griptape model proxy.

    Creates a new video based on the subject and timbre of reference videos and a prompt.
    Use character1, character2, character3 in the prompt to refer to subjects in
    reference videos 1, 2, 3 respectively.

    Documentation: https://www.alibabacloud.com/help/en/model-studio/reference-to-video-api-reference

    Inputs:
        - model (str): WAN model to use (default: "wan2.6-r2v")
        - prompt (str): Text description using character1/character2/character3 to reference
            subjects in the reference videos (max 1500 characters)
        - negative_prompt (str): Description of content to avoid (max 500 characters)
        - reference_video_1 (VideoUrlArtifact): First reference video (required)
        - reference_video_2 (VideoUrlArtifact): Second reference video (optional)
        - reference_video_3 (VideoUrlArtifact): Third reference video (optional)
            Video requirements: MP4/MOV, 2-30s duration, max 100MB
        - input_audio (AudioUrlArtifact): Input audio file (optional)
            Audio requirements: WAV/MP3, 3-30s duration, max 15MB
            If audio exceeds video duration, it is truncated. If shorter, remaining video is silent.
        - size (str): Output video resolution (default: "1920*1080")
            720p tier: 1280*720, 720*1280, 960*960, 1088*832, 832*1088
            1080p tier: 1920*1080, 1080*1920, 1440*1440, 1632*1248, 1248*1632
        - duration (int): Video duration in seconds (5 or 10, default: 5)
        - shot_type (str): Shot type - "single" or "multi" (default: "single")
        - audio (bool): Auto-generate audio for video (default: True)
        - watermark (bool): Add "AI Generated" watermark (default: False)
        - randomize_seed (bool): If true, randomize the seed on each run
        - seed (int): Random seed for reproducible results (default: 42)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - video (VideoUrlArtifact): Generated video as URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate videos from reference videos using WAN models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Model selection
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value="wan2.6-r2v",
                tooltip="Select the WAN reference-to-video model to use",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_OPTIONS)},
            )
        )

        # Prompt parameter
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text description using character1/character2/character3 to reference subjects (max 1500 characters)",
                multiline=True,
                placeholder_text="character1 is happily watching a movie on the sofa...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )

        # Negative prompt parameter
        self.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Description of content to avoid (max 500 characters)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "low resolution, error, worst quality...",
                    "display_name": "Negative Prompt",
                },
            )
        )

        # Reference video 1 (required) using PublicArtifactUrlParameter
        self._public_video_url_parameter_1 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_1",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="First reference video (required). MP4/MOV, 2-30s, max 100MB. Use 'character1' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 1"},
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_1.add_input_parameters()

        # Reference video 2 (optional) using PublicArtifactUrlParameter - hidden by default
        self._public_video_url_parameter_2 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_2",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Second reference video (optional). MP4/MOV, 2-30s, max 100MB. Use 'character2' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 2"},
                hide=True,
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_2.add_input_parameters()
        # Hide the upload message for video 2 since the parameter is hidden
        self.hide_message_by_name("artifact_url_parameter_message_reference_video_2")

        # Reference video 3 (optional) using PublicArtifactUrlParameter - hidden by default
        self._public_video_url_parameter_3 = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video_3",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Third reference video (optional). MP4/MOV, 2-30s, max 100MB. Use 'character3' in prompt to reference.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Reference Video 3"},
                hide=True,
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the reference video.",
        )
        self._public_video_url_parameter_3.add_input_parameters()
        # Hide the upload message for video 3 since the parameter is hidden
        self.hide_message_by_name("artifact_url_parameter_message_reference_video_3")

        # Size parameter
        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                type="str",
                default_value="1920*1080",
                tooltip="Output video resolution (width*height)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=ALL_SIZE_OPTIONS)},
            )
        )

        # Duration parameter
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=5,
                tooltip="Video duration in seconds (5 or 10)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
        )

        # Audio parameter
        self.add_parameter(
            Parameter(
                name="audio",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Auto-generate audio for video",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Input Audio (optional) using PublicArtifactUrlParameter
        # Hidden by default since audio auto-generation is enabled by default
        self._public_audio_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="input_audio",
                input_types=["AudioUrlArtifact"],
                type="AudioUrlArtifact",
                default_value="",
                tooltip="Input audio file (optional). WAV/MP3, 3-30s, max 15MB. Audio is used to generate video with matching sound.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Audio"},
                hide=self._should_hide_input_audio(),
            ),
            disclaimer_message="The WAN Reference-to-Video service utilizes this URL to access the audio file.",
        )
        self._public_audio_url_parameter.add_input_parameters()
        # Hide the upload message since audio auto-generation is enabled by default
        self.hide_message_by_name("artifact_url_parameter_message_input_audio")

        # Shot type parameter
        self.add_parameter(
            Parameter(
                name="shot_type",
                input_types=["str"],
                type="str",
                default_value="single",
                tooltip="Shot type: 'single' for continuous shot, 'multi' for multiple changing shots",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=SHOT_TYPE_OPTIONS)},
            )
        )

        # Watermark parameter
        self.add_parameter(
            Parameter(
                name="watermark",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Add 'AI Generated' watermark in lower-right corner",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Initialize SeedParameter component
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

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
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from Griptape model proxy",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Generated video as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        reference_video_1 = self.get_parameter_value("reference_video_1")
        if not reference_video_1:
            exceptions.append(ValueError("Reference Video 1 must be provided"))
        prompt = self.get_parameter_value("prompt")
        if not prompt:
            exceptions.append(ValueError("Prompt must be provided"))
        return exceptions if exceptions else None

    def _should_hide_input_audio(self) -> bool:
        """Determine if input_audio should be hidden. Hidden when audio auto-generation is enabled."""
        audio_enabled = self.get_parameter_value("audio")
        return audio_enabled is True

    def _update_input_audio_visibility(self) -> None:
        """Update input_audio parameter visibility based on audio setting."""
        if self._should_hide_input_audio():
            self.hide_parameter_by_name("input_audio")
            self.hide_message_by_name("artifact_url_parameter_message_input_audio")
        else:
            self.show_parameter_by_name("input_audio")
            self.show_message_by_name("artifact_url_parameter_message_input_audio")

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes."""
        super().after_value_set(parameter, value)

        # Update input_audio visibility when audio parameter changes
        if parameter.name == "audio":
            self._update_input_audio_visibility()

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Clear execution status at the start
        self._clear_execution_status()

        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Get parameters
        try:
            params = self._get_parameters()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        model = params["model"]
        logger.info("Generating video from reference with %s", model)

        # Submit request and get generation_id
        try:
            generation_id = await self._submit_request(params, headers)
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
        await self._poll_for_result(generation_id, headers, params["duration"])

        # Cleanup uploaded artifacts
        self._public_video_url_parameter_1.delete_uploaded_artifact()
        self._public_video_url_parameter_2.delete_uploaded_artifact()
        self._public_video_url_parameter_3.delete_uploaded_artifact()
        self._public_audio_url_parameter.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:  # noqa: C901
        model = self.get_parameter_value("model")
        prompt = self.get_parameter_value("prompt")
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        size = self.get_parameter_value("size")
        duration = self.get_parameter_value("duration")
        shot_type = self.get_parameter_value("shot_type")
        audio = self.get_parameter_value("audio")
        watermark = self.get_parameter_value("watermark")

        # Collect reference video URLs using PublicArtifactUrlParameter
        reference_video_urls = []

        # Video 1 is required
        video_url_1 = self._public_video_url_parameter_1.get_public_url_for_parameter()
        if video_url_1:
            reference_video_urls.append(video_url_1)

        # Video 2 is optional - only get public URL if a value is provided
        video_2_value = self.get_parameter_value("reference_video_2")
        if video_2_value:
            video_url_2 = self._public_video_url_parameter_2.get_public_url_for_parameter()
            if video_url_2:
                reference_video_urls.append(video_url_2)

        # Video 3 is optional - only get public URL if a value is provided
        video_3_value = self.get_parameter_value("reference_video_3")
        if video_3_value:
            video_url_3 = self._public_video_url_parameter_3.get_public_url_for_parameter()
            if video_url_3:
                reference_video_urls.append(video_url_3)

        if not reference_video_urls:
            msg = "At least one reference video URL is required"
            raise ValueError(msg)

        # Validate size
        if size not in ALL_SIZE_OPTIONS:
            msg = f"Invalid size {size}. Available sizes: {', '.join(ALL_SIZE_OPTIONS)}"
            raise ValueError(msg)

        # Validate duration
        if duration not in [5, 10]:
            msg = f"Invalid duration {duration}s. Available durations: 5, 10"
            raise ValueError(msg)

        # Validate shot_type
        if shot_type not in SHOT_TYPE_OPTIONS:
            msg = f"Invalid shot_type {shot_type}. Available options: {', '.join(SHOT_TYPE_OPTIONS)}"
            raise ValueError(msg)

        # Get audio URL if provided
        audio_url = None
        input_audio_value = self.get_parameter_value("input_audio")
        if input_audio_value:
            audio_url = self._public_audio_url_parameter.get_public_url_for_parameter()

        return {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "reference_video_urls": reference_video_urls,
            "audio_url": audio_url,
            "size": size,
            "duration": duration,
            "shot_type": shot_type,
            "audio": audio,
            "watermark": watermark,
            "seed": self._seed_parameter.get_seed(),
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        """Submit async generation request and return generation_id."""
        post_url = urljoin(self._proxy_base, f"models/{params['model']}")
        payload = self._build_payload(params)

        logger.debug("Submitting request to proxy model=%s", params["model"])

        async with httpx.AsyncClient() as client:
            post_resp = await client.post(post_url, json=payload, headers=headers, timeout=60)

        if post_resp.status_code >= HTTP_ERROR_STATUS:
            self._set_safe_defaults()
            logger.debug(
                "Proxy POST error status=%s headers=%s body=%s",
                post_resp.status_code,
                dict(post_resp.headers),
                post_resp.text,
            )
            try:
                error_json = post_resp.json()
                error_msg = error_json.get("error", "")
                provider_response = error_json.get("provider_response", "")
                msg_parts = [p for p in [error_msg, provider_response] if p]
                msg = " - ".join(msg_parts) if msg_parts else self._extract_error_details(error_json)
            except Exception:
                msg = f"Proxy POST error: {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        post_json = post_resp.json()
        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response

        if generation_id:
            logger.debug("Submitted. generation_id=%s", generation_id)
        else:
            logger.debug("No generation_id returned from POST response")

        return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        # Build payload matching proxy expected format (nested input/parameters structure)
        payload = {
            "input": {
                "prompt": params["prompt"],
                "reference_video_urls": params["reference_video_urls"],
            },
            "parameters": {
                "size": params["size"],
                "duration": params["duration"],
                "shot_type": params["shot_type"],
                "audio": params["audio"],
                "watermark": params["watermark"],
                "seed": params["seed"],
            },
        }

        # Add negative prompt if provided
        if params["negative_prompt"]:
            payload["input"]["negative_prompt"] = params["negative_prompt"]

        # Add audio_url if provided
        if params.get("audio_url"):
            payload["input"]["audio_url"] = params["audio_url"]

        return payload

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str], video_duration: int) -> None:
        """Poll the generations endpoint until ready."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        pending_start_time = time.monotonic()
        running_start_time = None
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        pending_timeout_s = 30.0
        running_timeout_s = video_duration * 60.0

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    get_resp = await client.get(get_url, headers=headers, timeout=60)
                    get_resp.raise_for_status()
                    last_json = get_resp.json()
                    self.parameter_output_values["provider_response"] = last_json
                except Exception as exc:
                    logger.debug("GET generation failed: %s", exc)
                    error_msg = f"Failed to poll generation status: {exc}"
                    self._set_status_results(was_successful=False, result_details=error_msg)
                    self._handle_failure_exception(RuntimeError(error_msg))
                    return

                attempt += 1
                status = self._extract_status(last_json) or STATUS_UNKNOWN
                logger.info("Last generation response: %s", last_json)
                logger.info("Polling attempt #%s status=%s", attempt, status)

                if status == STATUS_PENDING and time.monotonic() - pending_start_time > pending_timeout_s:
                    self.parameter_output_values["video"] = self._extract_result_video_url(last_json)
                    logger.debug("Polling timed out waiting for generation to start")
                    self._set_status_results(
                        was_successful=False,
                        result_details=f"Video generation timed out after {pending_timeout_s} seconds waiting for generation to start.",
                    )
                    return

                if status == STATUS_RUNNING:
                    if not running_start_time:
                        running_start_time = time.monotonic()
                    if running_start_time and time.monotonic() - running_start_time > running_timeout_s:
                        self.parameter_output_values["video"] = self._extract_result_video_url(last_json)
                        logger.info("Polling timed out waiting for result")
                        self._set_status_results(
                            was_successful=False,
                            result_details=f"Video generation timed out after {int(running_timeout_s)} seconds of processing.",
                        )
                        return

                if status in {STATUS_FAILED, STATUS_CANCELED}:
                    provider_resp = last_json.get("provider_response") if last_json else {}
                    error_code = provider_resp.get("code") if isinstance(provider_resp, dict) else None
                    error_message = provider_resp.get("message") if isinstance(provider_resp, dict) else None
                    log_parts = [p for p in [error_code, error_message] if p]
                    logger.error("Generation failed: %s", " - ".join(log_parts) or status)
                    self.parameter_output_values["video"] = None
                    error_details = self._extract_error_details(last_json)
                    self._set_status_results(was_successful=False, result_details=error_details)
                    return

                if status == STATUS_SUCCEEDED:
                    await self._handle_completion(last_json, generation_id)
                    return

                await asyncio.sleep(poll_interval_s)

    async def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        """Handle successful generation completion."""
        extracted_url = self._extract_result_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        try:
            logger.debug("Downloading video bytes from provider URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            logger.debug("Failed to download video: %s", e)
            video_bytes = None

        if video_bytes:
            try:
                filename = f"wan_r2v_{generation_id}.mp4" if generation_id else f"wan_r2v_{int(time.time())}.mp4"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.debug("Saved video to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                logger.debug("Failed to save to static storage: %s, using provider URL", e)
                self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        if top_level_error:
            return self._format_top_level_error(top_level_error)

        status = self._extract_status(response_json) or STATUS_UNKNOWN
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return json.loads(provider_response)
            except Exception:
                return None
        if isinstance(provider_response, dict):
            return provider_response
        return None

    def _format_provider_error(
        self, parsed_provider_response: dict[str, Any] | None, top_level_error: Any
    ) -> str | None:
        """Format error message from parsed provider response."""
        if not parsed_provider_response:
            return None

        provider_error = parsed_provider_response.get("error")
        if not provider_error:
            return None

        if isinstance(provider_error, dict):
            error_message = provider_error.get("message", "")
            details = f"{error_message}"

            if error_code := provider_error.get("code"):
                details += f"\nError Code: {error_code}"
            if error_type := provider_error.get("type"):
                details += f"\nError Type: {error_type}"
            if top_level_error:
                details = f"{top_level_error}\n\n{details}"
            return details

        error_msg = str(provider_error)
        if top_level_error:
            return f"{top_level_error}\n\nProvider error: {error_msg}"
        return f"Generation failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"Generation failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"Generation failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video"] = None

    @staticmethod
    def _extract_status(response_json: dict[str, Any] | None) -> str | None:
        """Extract task status from response."""
        if not response_json:
            return None
        task_status = response_json.get("task_status")
        if isinstance(task_status, str):
            return task_status
        return None

    @staticmethod
    def _extract_result_video_url(obj: dict[str, Any] | None) -> str | None:
        """Extract video URL from response."""
        if not obj:
            return None
        video_url = obj.get("video_url")
        if isinstance(video_url, str) and video_url.startswith("http"):
            return video_url
        return None

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
