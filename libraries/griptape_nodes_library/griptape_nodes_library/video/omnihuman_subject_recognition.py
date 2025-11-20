from __future__ import annotations

import contextlib
import json as _json
import logging
import os
from time import monotonic, sleep
from typing import Any, ClassVar
from urllib.parse import urljoin

import requests

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.image_utils import extract_image_url

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanSubjectRecognition"]


class OmnihumanSubjectRecognition(SuccessFailureNode):
    """Identify whether an image contains human, human-like, anthropomorphic, or similar subjects.

    This is Step 1 of the OmniHuman workflow. It analyzes an image to determine if it contains
    suitable subjects for video generation. This step can be skipped if you've already confirmed
    the image contains appropriate subjects.

    Inputs:
        - image_url (str): URL of the image to analyze

    Outputs:
        - generation_id (str): Griptape Cloud generation identifier
        - contains_subject (bool): Whether the image contains human or human-like subjects
        - was_successful (bool): Whether the recognition succeeded
        - result_details (str): Details about the subject recognition result or any errors
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-5-subject-recognition",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Identify subjects in images using OmniHuman Subject Recognition via Griptape Cloud"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value=self.MODEL_IDS[0],
                tooltip="Model identifier to use for recognition",
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
                tooltip="URL of the image to analyze for subject recognition.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "placeholder_text": "https://example.com/image.jpg",
                    "display_name": "Image URL",
                },
            ),
            disclaimer_message="The OmniHuman service utilizes this URL to access the image for subject recognition.",
        )
        self._public_image_url_parameter.add_input_parameters()

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
                name="contains_subject",
                output_type="bool",
                type="bool",
                tooltip="Whether the image contains human or human-like subjects",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the subject recognition result or any errors",
            result_details_placeholder="Recognition status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _log(self, message: str) -> None:
        """Log a message."""
        with contextlib.suppress(Exception):
            logger.info("%s: %s", self.name, message)

    def process(self) -> None:
        """Process the subject recognition request."""
        # Clear execution status at the start
        self._clear_execution_status()

        # Get and validate parameters
        model_id = self.get_parameter_value("model_id")
        image_url = extract_image_url(self.get_parameter_value("image_url"))
        if not image_url:
            self._set_status_results(was_successful=False, result_details="Image URL is required")
            return

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Submit recognition request
        try:
            public_image_url = self._public_image_url_parameter.get_public_url_for_parameter()
            generation_id = self._submit_recognition_request(model_id, public_image_url, api_key)
            self.parameter_output_values["generation_id"] = generation_id
            self._poll_for_result(generation_id, api_key)
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
        finally:
            self._public_image_url_parameter.delete_uploaded_artifact()

    def _validate_api_key(self) -> str:
        """Validate that the API key is available."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_recognition_request(self, model_id: str, image_url: str, api_key: str) -> str:
        """Submit the subject detection request via Griptape Cloud proxy."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Build payload matching BytePlus API format
        provider_params = {
            "req_key": self._get_req_key(model_id),
            "image_url": image_url,
        }

        post_url = urljoin(self._proxy_base, f"models/{model_id}")
        self._log("Submitting subject detection request via proxy")

        try:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/3041
            response = requests.post(
                post_url,
                json=provider_params,
                headers=headers,
                timeout=60,
            )

            if response.status_code >= 400:  # noqa: PLR2004
                error_msg = f"Proxy request failed with status {response.status_code}: {response.text}"
                self._log(error_msg)
                raise RuntimeError(error_msg)

            response_json = response.json()
            generation_id = response_json.get("generation_id")
            if not generation_id:
                error_msg = f"No generation_id returned from recognition request. Response: {response_json}"
                self._log(error_msg)
                raise RuntimeError(error_msg)

            return generation_id  # noqa: TRY300

        except requests.RequestException as e:
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
        timeout_s = 600.0

        last_json = None

        while True:
            if monotonic() - start_time > timeout_s:
                self._log("Polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Subject recognition timed out after {timeout_s} seconds waiting for result.",
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

                # Update generation result with latest data
                self.parameter_output_values["result_details"] = last_json

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
                resp_data = _json.loads(provider_response.get("data", {}).get("resp_data", "{}"))
                status = resp_data.get("status")
                contains_human = status == 1
                self.parameter_output_values["contains_subject"] = contains_human

                result_msg = f"Subject recognition completed successfully. response: {provider_response}. "
                self._set_status_results(
                    was_successful=True,
                    result_details=result_msg,
                )
                return

            if status != "done" and status not in ["not_found", "expired"]:
                sleep(poll_interval_s)
                continue

            # Check for completion
            # Any other status code is an error
            self._log(f"Subject recognition failed with status: {status}")
            error_details = f"Subject recognition failed.\nStatus: {status}\nFull response: {last_json}"
            self._set_status_results(was_successful=False, result_details=error_details)
            return

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-5-subject-recognition":
            return "realman_avatar_picture_create_role_omni_cv"

        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)
