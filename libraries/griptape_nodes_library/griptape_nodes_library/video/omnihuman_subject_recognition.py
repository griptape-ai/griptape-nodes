from __future__ import annotations

import contextlib
import json as _json
import logging
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_image import ParameterImage
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.file.file_loader import FileLoader, FileLoadError
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import extract_image_url

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanSubjectRecognition"]


class OmnihumanSubjectRecognition(GriptapeProxyNode):
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

        # INPUTS
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value=self.MODEL_IDS[0],
                tooltip="Model identifier to use for recognition",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=self.MODEL_IDS)},
            )
        )

        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterImage(
                name="image_url",
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
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation identifier",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterBool(
                name="contains_subject",
                tooltip="Whether the image contains human or human-like subjects",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the subject recognition result or any errors",
            result_details_placeholder="Recognition status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    def _log(self, message: str) -> None:
        """Log a message."""
        with contextlib.suppress(Exception):
            logger.info("%s: %s", self.name, message)

    async def aprocess(self) -> None:
        await self._process_generation()

    async def _process_generation(self) -> None:
        try:
            await super()._process_generation()
        finally:
            self._public_image_url_parameter.delete_uploaded_artifact()

    def _validate_api_key(self) -> str:
        """Validate that the API key is available."""
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _get_api_model_id(self) -> str:
        return self.get_parameter_value("model_id") or ""

    async def _build_payload(self) -> dict[str, Any]:
        model_id = self.get_parameter_value("model_id")
        image_input = self.get_parameter_value("image_url")
        image_value = extract_image_url(image_input)
        if not image_value:
            msg = "Image URL is required"
            raise ValueError(msg)

        image_url = await self._prepare_image_data_url_async(image_value)
        if not image_url:
            msg = "Failed to process input image"
            raise ValueError(msg)

        return {
            "req_key": self._get_req_key(model_id),
            "image_url": image_url,
        }

    async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
        provider_response = result_json.get("provider_response", result_json)
        if isinstance(provider_response, str):
            try:
                provider_response = _json.loads(provider_response)
            except Exception:
                provider_response = {}

        status = provider_response.get("data", {}).get("status", "").lower()

        if status == "done":
            resp_data = _json.loads(provider_response.get("data", {}).get("resp_data", "{}"))
            status_val = resp_data.get("status")
            contains_human = status_val == 1
            self.parameter_output_values["contains_subject"] = contains_human

            result_msg = f"Subject recognition completed successfully. response: {provider_response}. "
            self._set_status_results(
                was_successful=True,
                result_details=result_msg,
            )
            return

        error_details = f"Subject recognition failed.\nStatus: {status}\nFull response: {result_json}"
        self._set_status_results(was_successful=False, result_details=error_details)

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # Already a data URI — return as-is
        if image_url.startswith("data:image/"):
            return image_url

        try:
            return await FileLoader.aload_data_uri(image_url, fallback_mime="image/jpeg")
        except FileLoadError as e:
            logger.debug("%s failed to load image from %s: %s", self.name, image_url, e)
            return None

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        if val is None:
            return None

        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        try:
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except AttributeError:
            pass

        return None

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-5-subject-recognition":
            return "realman_avatar_picture_create_role_omni_cv"

        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["contains_subject"] = False
