from __future__ import annotations

import json as _json
import logging
from typing import Any

import httpx
from griptape.artifacts.image_url_artifact import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedVRImageUpscale"]


class SeedVRImageUpscale(GriptapeProxyNode):
    """Upscale an image using the SeedVR model via Griptape Cloud model proxy."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Upscale images via SeedVR through Griptape Cloud model proxy"

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

    async def aprocess(self) -> None:
        """Process the image upscale request."""
        try:
            await super().aprocess()
        finally:
            # Cleanup uploaded artifact
            self._public_image_url_parameter.delete_uploaded_artifact()

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model_id") or "seedvr2-upscale-image"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for SeedVR upscaling."""
        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        upscale_mode = self.get_parameter_value("upscale_mode")
        parameters = {
            "image_url": self._public_image_url_parameter.get_public_url_for_parameter(),
            "upscale_mode": upscale_mode,
            "noise_scale": self.get_parameter_value("noise_scale"),
            "output_format": self.get_parameter_value("output_format"),
            "seed": self._seed_parameter.get_seed(),
        }

        # Add mode-specific parameters
        if upscale_mode == "factor":
            parameters["upscale_factor"] = self.get_parameter_value("upscale_factor")
        elif upscale_mode == "target":
            parameters["target_resolution"] = self.get_parameter_value("target_resolution")

        return parameters

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse SeedVR result and save upscaled image."""
        # Extract image URL from result
        extracted_url = self._extract_image_url(result_json)
        if not extracted_url:
            self.parameter_output_values["image"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no image URL was found in the response.",
            )
            return

        # Download and save the image
        try:
            logger.info("Downloading image bytes from provider URL")
            image_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            msg = f"Failed to download image: {e}"
            logger.info(msg)
            image_bytes = None

        if image_bytes:
            try:
                output_format = self.get_parameter_value("output_format") or "jpg"
                filename = f"seedvr_image_upscale_{generation_id}.{output_format}"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(image_bytes, filename)
                self.parameter_output_values["image"] = ImageUrlArtifact(value=saved_url, name=filename)
                msg = f"Saved image to static storage as {filename}"
                logger.info(msg)
                self._set_status_results(
                    was_successful=True, result_details=f"Image upscaled successfully and saved as {filename}."
                )
            except Exception as e:
                msg = f"Failed to save to static storage: {e}, using provider URL"
                logger.info(msg)
                self.parameter_output_values["image"] = ImageUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Image upscaled successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["image"] = ImageUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Image upscaled successfully. Using provider URL (could not download image bytes).",
            )

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from failed generation response."""
        # Try to extract from provider response (SeedVR-specific pattern)
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))
        if parsed_provider_response:
            provider_error = parsed_provider_response.get("error")
            if provider_error:
                top_level_error = response_json.get("error")
                provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
                if provider_error_msg:
                    return provider_error_msg

        # Fall back to standard error extraction
        return super()._extract_error_message(response_json)

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

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["image"] = None

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL asynchronously."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
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
