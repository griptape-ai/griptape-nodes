from __future__ import annotations

import contextlib
import json as _json
import logging
import os
from typing import Any, ClassVar
from urllib.parse import urljoin

import requests
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanSubjectDetection"]


class OmnihumanSubjectDetection(SuccessFailureNode):
    """Detect and locate subjects in an image, returning masks and bounding boxes.

    This is Step 2 of the OmniHuman workflow (optional). It detects subjects in the image
    and provides profile images, mask images, and bounding box coordinates. This step can
    be skipped if there's no need to specify a subject to speak during video generation.

    Inputs:
        - image_url (str): URL of the image to analyze for subject detection

    Outputs:
        - profile_image_url (ImageUrlArtifact): URL of the detected subject profile
        - mask_image_url (ImageUrlArtifact): URL of the subject mask image
        - bounding_box (dict): Normalized bounding box coordinates
        - detection_result (dict): Full detection results from the API
        - was_successful (bool): Whether the detection succeeded
        - result_details (str): Details about the detection result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-5-subject-detection",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Detect subjects and generate masks using OmniHuman Subject Detection via Griptape Cloud"

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
                default_value="omnihuman-1-5-subject-detection",
                tooltip="Model identifier to use for detection",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.MODEL_IDS)},
            )
        )

        self.add_parameter(
            Parameter(
                name="image_url",
                input_types=["str", "ImageUrlArtifact"],
                type="str",
                tooltip="URL of the image to analyze for subject detection",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "placeholder_text": "https://example.com/image.jpg",
                    "display_name": "Image URL",
                },
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="profile_image_url",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="URL of the detected subject profile image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="mask_image_url",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="URL of the subject mask image",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="bounding_box",
                output_type="dict",
                type="dict",
                tooltip="Normalized bounding box coordinates of the detected subject",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="detection_result",
                output_type="dict",
                type="dict",
                tooltip="Full detection results from the API",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the subject detection result or any errors",
            result_details_placeholder="Detection status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _log(self, message: str) -> None:
        """Log a message."""
        with contextlib.suppress(Exception):
            logger.info("%s: %s", self.name, message)

    def process(self) -> None:
        """Process the subject detection request."""
        # Clear execution status at the start
        self._clear_execution_status()

        # Get and validate parameters
        model_id = self.get_parameter_value("model_id")
        image_url = self._get_image_url()
        if not image_url:
            self._set_status_results(was_successful=False, result_details="Image URL is required")
            return

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Submit detection request
        try:
            self._submit_detection_request(model_id, image_url, api_key)
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)

    def _get_image_url(self) -> str | None:
        """Get and validate the image URL parameter."""
        image_url = self.get_parameter_value("image_url")

        if not image_url:
            return None

        # Handle ImageUrlArtifact
        if hasattr(image_url, "value"):
            image_url = image_url.value

        image_url_str = str(image_url).strip()
        return image_url_str if image_url_str else None

    def _validate_api_key(self) -> str:
        """Validate that the API key is available."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_detection_request(self, model_id: str, image_url: str, api_key: str) -> None:
        """Submit the subject detection request via Griptape Cloud proxy."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Build payload matching BytePlus API format
        provider_params = {
            "req_key": "realman_avatar_picture_omni15_cv",
            "image_url": image_url,
        }

        post_url = urljoin(self._proxy_base, f"models/{model_id}")
        self._log("Submitting subject detection request via proxy")

        try:
            response = requests.post(
                post_url,
                json=provider_params,
                headers=headers,
                timeout=60,
            )

            if response.status_code >= 400:  # noqa: PLR2004
                self._set_safe_defaults()
                error_msg = f"Proxy request failed with status {response.status_code}: {response.text}"
                self._log(error_msg)
                raise RuntimeError(error_msg)

            response_json = response.json()
            self._process_response(response_json)

        except requests.RequestException as e:
            self._set_safe_defaults()
            error_msg = f"Failed to connect to Griptape Cloud proxy: {e}"
            self._log(error_msg)
            raise RuntimeError(error_msg) from e

    def _process_response(self, response_json: dict[str, Any]) -> None:
        """Process the API response from Griptape Cloud proxy."""
        # Extract provider response from Griptape Cloud format
        provider_response = response_json.get("provider_response", {})
        if isinstance(provider_response, str):
            try:
                provider_response = _json.loads(provider_response)
            except Exception:
                provider_response = {}

        status_code = provider_response.get("status_code")
        status_message = provider_response.get("status_message", "")
        detection_result = provider_response.get("object_detection_result", {})

        self.parameter_output_values["detection_result"] = response_json

        if status_code == 0:
            # Extract detection data
            profile_data = detection_result.get("profile", {}) if isinstance(detection_result, dict) else {}
            mask_data = detection_result.get("mask", {}) if isinstance(detection_result, dict) else {}
            bbox = detection_result.get("normalized_bbox", {}) if isinstance(detection_result, dict) else {}

            # Extract URLs
            profile_url = profile_data.get("image_url", "") if isinstance(profile_data, dict) else ""
            mask_url = mask_data.get("image_url", "") if isinstance(mask_data, dict) else ""

            # Set outputs
            if profile_url:
                self.parameter_output_values["profile_image_url"] = ImageUrlArtifact(value=profile_url)
            else:
                self.parameter_output_values["profile_image_url"] = None

            if mask_url:
                self.parameter_output_values["mask_image_url"] = ImageUrlArtifact(value=mask_url)
            else:
                self.parameter_output_values["mask_image_url"] = None

            self.parameter_output_values["bounding_box"] = bbox

            self._log("Subject detection succeeded")
            result_details = "Subject detection completed successfully."
            if status_message:
                result_details += f"\nMessage: {status_message}"
            if bbox:
                result_details += "\nBounding box coordinates detected"
            self._set_status_results(was_successful=True, result_details=result_details)
        else:
            self._set_safe_defaults()
            self._log(f"Subject detection failed. Status code: {status_code}, Message: {status_message}")
            error_details = f"Subject detection failed.\nStatus code: {status_code}\nMessage: {status_message}"
            self._set_status_results(was_successful=False, result_details=error_details)

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs on error."""
        self.parameter_output_values["profile_image_url"] = None
        self.parameter_output_values["mask_image_url"] = None
        self.parameter_output_values["bounding_box"] = {}
        self.parameter_output_values["detection_result"] = {}
