from __future__ import annotations

import contextlib
import json as _json
import logging
import os
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

__all__ = ["OmnihumanSubjectDetection"]


class OmnihumanSubjectDetection(SuccessFailureNode):
    """Detect and locate subjects in an image, returning masks and bounding boxes.

    This is Step 2 of the OmniHuman workflow (optional). It detects subjects in the image
    and provides profile images, mask images, and bounding box coordinates. This step can
    be skipped if there's no need to specify a subject to speak during video generation.

    Inputs:
        - image_url (str): URL of the image to analyze for subject detection

    Outputs:
        - mask_image_urls (list[ImageUrlArtifact]): URLs of the subject mask images
        - contains_subject (bool): Whether the image contains a human subject
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
                default_value=self.MODEL_IDS[0],
                tooltip="Model identifier to use for detection",
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
                tooltip="URL of the image to analyze for subject detection.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "placeholder_text": "https://example.com/image.jpg",
                    "display_name": "Image URL",
                },
            ),
            disclaimer_message="The OmniHuman service utilizes this URL to access the image for subject detection.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="mask_image_urls",
                type="list",
                output_type="list",
                tooltip="List of mask image URLs for detected subjects",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="contains_subject",
                output_type="bool",
                type="bool",
                tooltip="Whether the image contains a human subject",
                allowed_modes={ParameterMode.OUTPUT},
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

        # Submit detection request
        try:
            public_image_url = self._public_image_url_parameter.get_public_url_for_parameter()
            self._submit_detection_request(model_id, public_image_url, api_key)
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

    def _submit_detection_request(self, model_id: str, image_url: str, api_key: str) -> None:
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
                timeout=300,  # 5 minutes
            )

            if response.status_code >= 400:  # noqa: PLR2004
                error_msg = f"Proxy request failed with status {response.status_code}: {response.text}"
                self._log(error_msg)
                raise RuntimeError(error_msg)

            response_json = response.json()
            self._process_response(response_json)

        except requests.RequestException as e:
            error_msg = f"Failed to connect to Griptape Cloud proxy: {e}"
            self._log(error_msg)
            raise RuntimeError(error_msg) from e

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-5-subject-detection":
            return "realman_avatar_object_detection_cv"

        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)

    def _process_response(self, response_json: dict[str, Any]) -> None:
        """Process the API response from Griptape Cloud proxy."""
        # Extract provider response from Griptape Cloud format
        resp_data = _json.loads(response_json.get("data", {}).get("resp_data", {}))

        contains_human = resp_data.get("status") == 1
        mask_urls = resp_data.get("object_detection_result", {}).get("mask", {}).get("url", [])

        self.parameter_output_values["contains_subject"] = contains_human
        self.parameter_output_values["mask_image_urls"] = mask_urls

        result_msg = f"Subject detection completed successfully. response: {resp_data}. "
        self._set_status_results(
            was_successful=True,
            result_details=result_msg,
        )
