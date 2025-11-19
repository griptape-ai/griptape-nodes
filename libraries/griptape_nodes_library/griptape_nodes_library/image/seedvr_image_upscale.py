from __future__ import annotations

import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic, sleep, time
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts.image_url_artifact import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedVRImageUpscale"]


class SeedVRImageUpscale(SuccessFailureNode):
    """Upscale an image using the SeedVR model via Griptape Cloud model proxy."""

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    # Base URL is derived from env var and joined with /api/ at runtime

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Upscale images via SeedVR through Griptape Cloud model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"  # Ensure trailing slash
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="seedvr2-upscale-image",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model ID",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "seedvr2-upscale-image",
                        ]
                    )
                },
            )
        )

        # Image URL
        self._public_image_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="image_url",
                input_types=["ImageUrlArtifact"],
                type="ImageUrlArtifact",
                default_value="",
                tooltip="Image URL",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ),
            disclaimer_message="The SeedVR service utilizes this URL to access the image for upscaling.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # Upscale mode selection
        self.add_parameter(
            Parameter(
                name="upscale_mode",
                input_types=["str"],
                type="str",
                default_value="factor",
                tooltip="Upscale mode",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["factor", "target"])},
            )
        )

        # Noise scale selection
        self.add_parameter(
            Parameter(
                name="noise_scale",
                input_types=["float"],
                type="float",
                default_value=0.1,
                tooltip="Noise scale",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.001},
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="target_resolution",
                input_types=["str"],
                type="str",
                default_value="1080p",
                tooltip="Target resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "1080p", "1440p", "2160p"])},
                hide=True,
            )
        )

        # Output format selection
        self.add_parameter(
            Parameter(
                name="output_format",
                input_types=["str"],
                type="str",
                default_value="jpg",
                tooltip="Output format",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["png", "jpg", "webp"])},
            )
        )

        # Upscale factor
        self.add_parameter(
            Parameter(
                name="upscale_factor",
                input_types=["float"],
                type="float",
                default_value=2.0,
                tooltip="The upscale factor",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"slider": {"min_val": 1.0, "max_val": 10.0}, "step": 0.1},
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
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="image",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="Saved image as artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

        # No separate status message panel; we'll stream updates to the 'status' output
        # Always polls with fixed interval/timeout

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        image_url = self.get_parameter_value("image_url")
        if not image_url:
            exceptions.append(ValueError("Image URL must be provided"))
        return exceptions if exceptions else None

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        self._seed_parameter.after_value_set(parameter, value)

        if parameter.name == "upscale_mode":
            upscale_mode = str(value)
            if upscale_mode == "factor":
                self.hide_parameter_by_name("target_resolution")
                self.show_parameter_by_name("upscale_factor")
            if upscale_mode == "target":
                self.show_parameter_by_name("target_resolution")
                self.hide_parameter_by_name("upscale_factor")

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        self.preprocess()
        # Clear execution status at the start
        self._clear_execution_status()

        # Get parameters and validate API key

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        params = self._get_parameters()

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Build and submit request
        try:
            generation_id = self._submit_request(params, headers)
            if not generation_id:
                self.parameter_output_values["result"] = None
                self.parameter_output_values["image"] = None
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            # HTTP error during submission
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        self._poll_for_result(generation_id, headers)

        # Cleanup
        self._public_image_url_parameter.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:
        parameters = {
            "model_id": self.get_parameter_value("model_id"),
            "image_url": self._public_image_url_parameter.get_public_url_for_parameter(),
            "upscale_mode": self.get_parameter_value("upscale_mode"),
            "noise_scale": self.get_parameter_value("noise_scale"),
            "target_resolution": self.get_parameter_value("target_resolution"),
            "output_format": self.get_parameter_value("output_format"),
            "upscale_factor": self.get_parameter_value("upscale_factor"),
            "seed": self._seed_parameter.get_seed(),
        }
        if parameters["upscale_mode"] == "factor":
            parameters.pop("target_resolution", None)
        elif parameters["upscale_mode"] == "target":
            parameters.pop("upscale_factor", None)
        return parameters

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        post_url = urljoin(self._proxy_base, f"models/{params['model_id']}")
        payload = params

        msg = f"Submitting request to proxy model={params['model_id']}"
        logger.info(msg)
        self._log_request(post_url, headers, payload)

        post_resp = requests.post(post_url, json=payload, headers=headers, timeout=60)
        if post_resp.status_code >= 400:  # noqa: PLR2004
            self._set_safe_defaults()
            msg = f"Proxy POST error status={post_resp.status_code} headers={dict(post_resp.headers)} body={post_resp.text}"
            logger.info(msg)
            # Try to parse error response body
            try:
                error_json = post_resp.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"Proxy POST error: {post_resp.status_code} - {post_resp.text}"
            raise RuntimeError(msg)

        post_json = post_resp.json()
        generation_id = str(post_json.get("generation_id") or "")
        provider_response = post_json.get("provider_response")

        self.parameter_output_values["generation_id"] = generation_id
        self.parameter_output_values["provider_response"] = provider_response

        if generation_id:
            msg = f"Submitted. generation_id={generation_id}"
            logger.info(msg)
        else:
            logger.info("No generation_id returned from POST response")

        return generation_id

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            msg = f"POST {url}\nheaders={dbg_headers}\nbody={_json.dumps(payload, indent=2)}"
            logger.info(msg)

    def _poll_for_result(self, generation_id: str, headers: dict[str, str]) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json = None
        attempt = 0
        poll_interval_s = 5.0
        timeout_s = 600.0

        while True:
            if monotonic() - start_time > timeout_s:
                self.parameter_output_values["image_url"] = self._extract_image_url(last_json)
                logger.info("Polling timed out waiting for result")
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Image generation timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()
                last_json = get_resp.json()
                # Update provider_response with latest polling data
                self.parameter_output_values["provider_response"] = last_json
            except Exception as exc:
                msg = f"GET generation failed: {exc}"
                logger.info(msg)
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            with suppress(Exception):
                msg = f"GET payload attempt #{attempt + 1}: {_json.dumps(last_json, indent=2)}"
                logger.info(msg)
                self.append_value_to_parameter("result_details", f"{msg}\n")

            attempt += 1
            status = self._extract_status(last_json) or "IN_PROGRESS"
            msg = f"Polling attempt #{attempt} status={status}"
            logger.info(msg)

            # Check for explicit failure statuses
            if status.lower() in {"failed", "error"}:
                msg = f"Generation failed with status: {status}"
                logger.info(msg)
                self.parameter_output_values["image_url"] = None
                error_details = self._extract_error_details(last_json)
                self._set_status_results(was_successful=False, result_details=error_details)
                return

            # Check if we have the image - if so, we're done
            image_url = self._extract_image_url(last_json)
            if image_url:
                self._handle_completion(last_json, generation_id)
                return

            sleep(poll_interval_s)

    def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        extracted_url = self._extract_image_url(last_json)
        if not extracted_url:
            self.parameter_output_values["image"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no image URL was found in the response.",
            )
            return

        try:
            logger.info("Downloading image bytes from provider URL")
            image_bytes = self._download_bytes_from_url(extracted_url)
        except Exception as e:
            msg = f"Failed to download image: {e}"
            logger.info(msg)
            image_bytes = None

        if image_bytes:
            try:
                filename = (
                    f"seedvr_image_upscale_{generation_id}.{self.get_parameter_value('output_format')}"
                    if generation_id
                    else f"seedvr_image_upscale_{int(time())}.{self.get_parameter_value('output_format')}"
                )
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image"] = ImageUrlArtifact(value=saved_url, name=filename)
                msg = f"Saved image to static storage as {filename}"
                logger.info(msg)
                self._set_status_results(
                    was_successful=True, result_details=f"Image generated successfully and saved as {filename}."
                )
            except Exception as e:
                msg = f"Failed to save to static storage: {e}, using provider URL"
                logger.info(msg)
                self.parameter_output_values["image"] = ImageUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Image generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["image"] = ImageUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Image generated successfully. Using provider URL (could not download image bytes).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response.

        Args:
            response_json: The JSON response from the API that may contain error information

        Returns:
            A formatted error message string
        """
        if not response_json:
            return "Generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        # Try to extract from provider response first (more detailed)
        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        # Fall back to top-level error
        if top_level_error:
            return self._format_top_level_error(top_level_error)

        # Final fallback
        status = self._extract_status(response_json) or "unknown"
        return f"Generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

    def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
        """Parse provider_response if it's a JSON string."""
        if isinstance(provider_response, str):
            try:
                return _json.loads(provider_response)
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
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["result"] = None
        self.parameter_output_values["status"] = "error"
        self.parameter_output_values["image"] = None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            import requests
        except Exception as exc:  # pragma: no cover
            msg = "Missing optional dependency 'requests'. Add it to library dependencies."
            raise ImportError(msg) from exc

        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception:  # pragma: no cover
            return None
        else:
            return resp.content

    @staticmethod
    def _extract_status(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        if "status" in obj:
            status_val = obj.get("status")
            if isinstance(status_val, str):
                return status_val
        return None

    @staticmethod
    def _extract_image_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        if "image" in obj:
            image_obj = obj.get("image")
            if isinstance(image_obj, dict):
                url = image_obj.get("url")
                if isinstance(url, str):
                    return url
        return None
