from __future__ import annotations

import contextlib
import json as _json
import logging
import os
import time
from time import monotonic, sleep
from typing import Any, ClassVar
from urllib.parse import urljoin

import requests
from griptape.artifacts import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanVideoGeneration"]


class OmnihumanVideoGeneration(SuccessFailureNode):
    """Generate video effects from a single image, text prompt, and audio file using OmniHuman 1.5.

    This is Step 3 of the OmniHuman workflow. It generates video matching the input image based
    on the provided audio and optional mask. The generation process is asynchronous and will
    poll for completion.

    Inputs:
        - image_url (str): Source image URL
        - audio_url (str): Audio file URL
        - mask_image_urls (list): Optional mask image URLs from subject detection
        - prompt (str): Text prompt to guide generation
        - seed (int): Random seed for generation (-1 for random)
        - fast_mode (bool): Enable fast mode (sacrifices some effects for speed

    Outputs:
        - generation_id (str): Griptape Cloud generation identifier
        - video_url (VideoUrlArtifact): Generated video URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the video generation result or any errors
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-0",
        "omnihuman-1-5",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate talking head videos using OmniHuman 1.5 via Griptape Cloud"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS
        # add model_id parameter with fixed value
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="omnihuman-1-5",
                tooltip="Model identifier to use for generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.MODEL_IDS)},
            )
        )

        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="image_url",
                input_types=["ImageUrlArtifact"],
                type="ImageUrlArtifact",
                default_value="",
                tooltip="Source image URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/image.jpg"},
            ),
            disclaimer_message="The OmniHuman service utilizes this URL to access the image for video generation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        self._public_audio_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="audio_url",
                input_types=["AudioUrlArtifact"],
                type="AudioUrlArtifact",
                default_value="",
                tooltip="Audio file URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/audio.mp3"},
            ),
        )
        self._public_audio_url_parameter.add_input_parameters()

        self.add_parameter(
            Parameter(
                name="mask_image_urls",
                input_types=["list"],
                type="list",
                output_type="list",
                default_value=[],
                tooltip="Optional mask image URLs from subject detection",
                ui_options={"placeholder_text": "https://example.com/mask1.png"},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation identifier",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Generated video URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=-1,
                tooltip="Random seed for generation (-1 for random)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "-1 for random"},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="Text prompt to guide generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Text prompt to guide generation"},
            )
        )

        self.add_parameter(
            Parameter(
                name="fast_mode",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="Enable fast mode (sacrifices some effects for speed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        # if the model_id parameter is omnihuman-1-0, remove seed, fast_mode, and prompt parameters
        if parameter.name == "model_id" and value == "omnihuman-1-0":
            self.hide_parameter_by_name("seed")
            self.hide_parameter_by_name("fast_mode")
            self.hide_parameter_by_name("prompt")
        else:
            self.show_parameter_by_name("seed")
            self.show_parameter_by_name("fast_mode")
            self.show_parameter_by_name("prompt")

    def _log(self, message: str) -> None:
        """Log a message."""
        with contextlib.suppress(Exception):
            logger.info("%s: %s", self.name, message)

    def process(self) -> AsyncResult[None]:
        """Process video generation asynchronously."""
        yield lambda: self._process()

    def _process(self) -> None:
        """Internal processing method."""
        # Clear execution status at the start
        self._clear_execution_status()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        try:
            # Get and validate parameters
            params = self._get_parameters()
        except ValueError as e:
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_audio_url_parameter.delete_uploaded_artifact()
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Submit generation request
        try:
            generation_id = self._submit_generation_request(params, api_key)
            if not generation_id:
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from proxy. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        self._poll_for_result(generation_id, api_key)

        # Cleanup
        self._public_image_url_parameter.delete_uploaded_artifact()
        self._public_audio_url_parameter.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:
        """Get and normalize input parameters."""
        image_url = self.get_parameter_value("image_url")
        audio_url = self.get_parameter_value("audio_url")
        mask_image_urls = self.get_parameter_value("mask_image_urls")
        prompt = self.get_parameter_value("prompt")
        seed = self.get_parameter_value("seed")
        fast_mode = self.get_parameter_value("fast_mode")

        model_id = self.get_parameter_value("model_id")

        # image url and audio url are required
        if not image_url:
            msg = "image_url parameter is required."
            raise ValueError(msg)
        image_url = self._public_image_url_parameter.get_public_url_for_parameter()
        if not audio_url:
            msg = "audio_url parameter is required."
            raise ValueError(msg)
        audio_url = self._public_audio_url_parameter.get_public_url_for_parameter()

        # Handle artifacts
        if hasattr(mask_image_urls, "value"):
            mask_image_urls = mask_image_urls.value

        body = {
            "req_key": self._get_req_key(model_id),
            "image_url": str(image_url).strip(),
            "audio_url": str(audio_url).strip(),
            "mask_url": "; ".join([str(url).strip() for url in mask_image_urls]) if mask_image_urls else None,
            "prompt": prompt if prompt else None,
            "seed": seed if seed else None,
            "fast_mode": fast_mode if fast_mode else None,
        }
        # remove None values
        return {k: v for k, v in body.items() if v is not None}

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-0":
            return "realman_avatar_picture_omni_cv"
        if model_id == "omnihuman-1-5":
            return "realman_avatar_picture_omni15_cv"
        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)

    def _validate_api_key(self) -> str:
        """Validate that the API key is available."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_generation_request(self, params: dict[str, Any], api_key: str) -> str:
        """Submit the video generation request via Griptape Cloud proxy."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        model = self.get_parameter_value("model_id")

        post_url = urljoin(self._proxy_base, f"models/{model}")
        self._log("Submitting video generation request via proxy")

        try:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/3041
            response = requests.post(
                post_url,
                json=params,
                headers=headers,
                timeout=60,
            )

            if response.status_code >= 400:  # noqa: PLR2004
                self._set_safe_defaults()
                error_msg = f"Proxy request failed with status {response.status_code}: {response.text}"
                self._log(error_msg)
                raise RuntimeError(error_msg)

            response_json = response.json()
            generation_id = str(response_json.get("generation_id") or "")

            self.parameter_output_values["generation_id"] = generation_id

            if generation_id:
                self._log(f"Submitted. Generation ID: {generation_id}")
            else:
                self._log(f"No generation_id returned from POST response. Response: {response_json}")

            return generation_id  # noqa: TRY300

        except requests.RequestException as e:
            self._set_safe_defaults()
            error_msg = f"Failed to connect to Griptape Cloud proxy: {e}"
            self._log(error_msg)
            raise RuntimeError(error_msg) from e

    def _poll_for_result(self, generation_id: str, api_key: str) -> None:
        """Poll for the generation result via Griptape Cloud proxy."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")

        start_time = monotonic()
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 30 * 60  # 30 minutes

        last_json = None

        while True:
            if monotonic() - start_time > timeout_s:
                self._log("Polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Video generation timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/3041
                response = requests.get(
                    get_url,
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()
                last_json = response.json()

            except Exception as exc:
                self._log(f"Polling request failed: {exc}")
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            attempt += 1

            # Extract provider response
            provider_response = last_json.get("provider_response", {})
            if isinstance(provider_response, str):
                try:
                    provider_response = _json.loads(provider_response)
                except Exception:
                    provider_response = {}

            status = provider_response.get("data", {}).get("status", "").lower()

            self._log(f"Polling attempt #{attempt}, status={status}")

            if status == "done":
                self._handle_completion(last_json, generation_id)
                return

            if status not in ["not_found", "expired"]:
                sleep(poll_interval_s)
                continue

            # Check for completion
            # Any other status code is an error
            self._log(f"Generation failed with status: {status}")
            self.parameter_output_values["video_url"] = None
            error_details = f"Video generation failed.\nStatus: {status}\nFull response: {last_json}"
            self._set_status_results(was_successful=False, result_details=error_details)
            return

    def _handle_completion(self, response_json: dict[str, Any], _generation_id: str) -> None:
        """Handle successful completion of video generation."""
        # Extract provider response
        provider_response = response_json.get("provider_response", {})
        if isinstance(provider_response, str):
            try:
                provider_response = _json.loads(provider_response)
            except Exception:
                provider_response = {}

        # Extract video URL from provider response
        video_url = self._extract_video_url(provider_response)

        if not video_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)
        try:
            self._log("Downloading video bytes from provider URL")
            video_filename = self._save_video_bytes(video_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_filename = None

        self._set_status_results(
            was_successful=True,
            result_details=f"Video generation completed successfully. Video URL: {video_url}"
            + (f", saved as: {video_filename}" if video_filename else ""),
        )

    @staticmethod
    def _extract_video_url(response_json: dict[str, Any]) -> str | None:
        """Extract video URL from API response."""
        if not isinstance(response_json, dict):
            return None

        # Try direct video_url field
        video_url = _json.loads(response_json.get("data", {}).get("resp_data", "{}")).get("video_url")
        if isinstance(video_url, str) and video_url.startswith("http"):
            return video_url

        return None

    @staticmethod
    def _save_video_bytes(url: str) -> str | None:
        """Download video bytes from URL."""
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            video_filename = f"omnihuman_video_{int(time.time())}.mp4"
            GriptapeNodes.StaticFilesManager().save_static_file(response.content, video_filename)
            return video_filename  # noqa: TRY300
        except Exception:
            return None

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["video_url"] = None
