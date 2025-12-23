from __future__ import annotations

import json as _json
import logging
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanSubjectDetection"]


class OmnihumanSubjectDetection(GriptapeProxyNode):
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

    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-5-subject-detection",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Detect subjects and generate masks using OmniHuman Subject Detection via Griptape Cloud"

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

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model_id") or "omnihuman-1-5-subject-detection"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for subject detection."""
        # Get image URL
        image_url = self.get_parameter_value("image_url")
        if not image_url:
            msg = "image_url parameter is required."
            raise ValueError(msg)

        # Get public URL from parameter
        public_image_url = self._public_image_url_parameter.get_public_url_for_parameter()

        # Build payload
        model_id = self._get_api_model_id()
        return {
            "req_key": self._get_req_key(model_id),
            "image_url": public_image_url,
        }

    async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
        """Parse subject detection result."""
        # Parse nested resp_data JSON string
        resp_data_str = result_json.get("data", {}).get("resp_data", "{}")
        if not resp_data_str:
            self.parameter_output_values["contains_subject"] = False
            self.parameter_output_values["mask_image_urls"] = []
            self._set_status_results(
                was_successful=False,
                result_details="No response data found in result.",
            )
            return

        resp_data = _json.loads(resp_data_str)
        contains_human = resp_data.get("status") == 1
        mask_urls = resp_data.get("object_detection_result", {}).get("mask", {}).get("url", [])

        self.parameter_output_values["contains_subject"] = contains_human
        self.parameter_output_values["mask_image_urls"] = mask_urls

        result_msg = (
            f"Subject detection completed successfully. Contains subject: {contains_human}, Masks: {len(mask_urls)}"
        )
        self._set_status_results(
            was_successful=True,
            result_details=result_msg,
        )

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs on error."""
        self.parameter_output_values["mask_image_urls"] = []
        self.parameter_output_values["contains_subject"] = False

    async def aprocess(self) -> None:
        """Process subject detection with cleanup."""
        try:
            await super().aprocess()
        finally:
            # Cleanup uploaded artifacts
            self._public_image_url_parameter.delete_uploaded_artifact()

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-5-subject-detection":
            return "realman_avatar_object_detection_cv"

        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)
