from __future__ import annotations

import json as _json
import logging
from time import time
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_dict import ParameterDict
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.exe_types.param_types.parameter_video import ParameterVideo
from griptape_nodes.retained_mode.events.static_file_events import (
    LoadAndSaveFromLocationRequest,
    LoadAndSaveFromLocationResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedVRVideoUpscale"]


class SeedVRVideoUpscale(GriptapeProxyNode):
    """Upscale a video using the SeedVR model via Griptape Cloud model proxy."""

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    # Base URL is derived from env var and joined with /api/ at runtime

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Seedance through Griptape Cloud model proxy"

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="model_id",
                default_value="seedvr2-upscale-video",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model ID",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "seedvr2-upscale-video",
                        ]
                    )
                },
            )
        )

        # Video URL
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=ParameterVideo(
                name="video_url",
                default_value="",
                tooltip="Video URL",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ),
            disclaimer_message="The SeedVR service utilizes this URL to access the video for upscaling.",
        )
        self._public_video_url_parameter.add_input_parameters()

        with ParameterGroup(name="Generation Settings") as generation_settings_group:
            # Upscale mode selection
            ParameterString(
                name="upscale_mode",
                default_value="factor",
                tooltip="Upscale mode",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["factor", "target"])},
            )

            # Noise scale selection
            ParameterFloat(
                name="noise_scale",
                default_value=0.1,
                tooltip="Noise scale",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"slider": {"min_val": 0.001, "max_val": 1.0}, "step": 0.001},
            )

            # Resolution selection
            ParameterString(
                name="target_resolution",
                default_value="1080p",
                tooltip="Target resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "1080p", "1440p", "2160p"])},
                hide=True,
            )

            # Aspect ratio selection
            ParameterString(
                name="output_format",
                default_value="X264 (.mp4)",
                tooltip="Output format",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["X264 (.mp4)", "VP9 (.webm)", "PRORES4444 (.mov)", "GIF (.gif)"])},
            )

            # Output write mode selection
            ParameterString(
                name="output_write_mode",
                default_value="balanced",
                tooltip="Output write mode",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["balanced", "fast", "small"])},
            )

            # Output quality selection
            ParameterString(
                name="output_quality",
                default_value="high",
                tooltip="Output quality",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["low", "medium", "high", "maximum"])},
            )

            # Upscale factor
            ParameterFloat(
                name="upscale_factor",
                default_value=2.0,
                tooltip="The upscale factor",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"slider": {"min_val": 1.0, "max_val": 10.0}, "step": 0.1},
            )

            # Initialize SeedParameter component
            self._seed_parameter = SeedParameter(self)
            self._seed_parameter.add_input_parameters(inside_param_group=True)

            # Polling timeout (0 = no timeout)
            ParameterInt(
                name="timeout",
                default_value=1000,
                tooltip="Polling timeout in seconds. Set to 0 for no timeout.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                min_val=0,
                max_val=86400,
            )

        self.add_node_element(generation_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            ParameterDict(
                name="provider_response",
                tooltip="Verbatim response from API (final result)",
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
                hide=True,
            )
        )

        self.add_parameter(
            ParameterVideo(
                name="video",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

        # No separate status message panel; we'll stream updates to the 'status' output
        # Always polls with fixed interval/timeout

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        video_url = self.get_parameter_value("video_url")
        if not video_url:
            exceptions.append(ValueError("Video URL must be provided"))
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

    async def _process_generation(self) -> None:
        self.preprocess()
        timeout_s = float(self.get_parameter_value("timeout") or 0)
        if timeout_s > 0:
            poll_interval = self.DEFAULT_POLL_INTERVAL
            self.DEFAULT_MAX_ATTEMPTS = max(1, int((timeout_s + poll_interval - 1) // poll_interval))

        try:
            await super()._process_generation()
        finally:
            self._public_video_url_parameter.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:
        parameters = {
            "model_id": self.get_parameter_value("model_id"),
            "video_input": self.get_parameter_value("video_url"),
            "upscale_mode": self.get_parameter_value("upscale_mode"),
            "noise_scale": self.get_parameter_value("noise_scale"),
            "target_resolution": self.get_parameter_value("target_resolution"),
            "output_format": self.get_parameter_value("output_format"),
            "output_write_mode": self.get_parameter_value("output_write_mode"),
            "output_quality": self.get_parameter_value("output_quality"),
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

    def _get_api_model_id(self) -> str:
        return self.get_parameter_value("model_id") or ""

    async def _build_payload(self) -> dict[str, Any]:
        params = self._get_parameters()

        video_url = self._public_video_url_parameter.get_public_url_for_parameter()
        if not video_url:
            msg = "Video URL must be provided"
            raise ValueError(msg)

        payload: dict[str, Any] = {
            "model_id": params["model_id"],
            "video_url": video_url,
            "upscale_mode": params["upscale_mode"],
            "noise_scale": params["noise_scale"],
            "output_format": params["output_format"],
            "output_write_mode": params["output_write_mode"],
            "output_quality": params["output_quality"],
            "seed": params["seed"],
        }

        if "target_resolution" in params:
            payload["target_resolution"] = params["target_resolution"]
        if "upscale_factor" in params:
            payload["upscale_factor"] = params["upscale_factor"]

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        if "raw_bytes" in result_json:
            await self._handle_video_bytes(result_json["raw_bytes"], generation_id)
            return

        video_url = self._extract_video_url(result_json)
        if video_url:
            await self._handle_completion(result_json, generation_id)
            return

        status = self._extract_status(result_json) or "unknown"
        error_details = self._extract_error_message(result_json)
        self.parameter_output_values["video"] = None
        self._set_status_results(was_successful=False, result_details=error_details or status)

    async def _handle_video_bytes(self, video_bytes: bytes, generation_id: str | None) -> None:
        if not video_bytes:
            self.parameter_output_values["video"] = None
            self._set_status_results(was_successful=False, result_details="Received empty video data from API.")
            return

        try:
            filename = (
                f"seedvr_video_upscale_{generation_id}.mp4"
                if generation_id
                else f"seedvr_video_upscale_{int(time())}.mp4"
            )
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(video_bytes, filename)
            self.parameter_output_values["video"] = VideoUrlArtifact(value=saved_url, name=filename)
            msg = f"Saved video to static storage as {filename}"
            logger.info(msg)
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        except Exception as e:
            msg = f"Failed to save to static storage: {e}"
            logger.info(msg)
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False, result_details=f"Video generation completed but failed to save: {e}"
            )

    async def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self.parameter_output_values["video"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        filename = (
            f"seedvr_video_upscale_{generation_id}.mp4" if generation_id else f"seedvr_video_upscale_{int(time())}.mp4"
        )

        result = await GriptapeNodes.ahandle_request(
            LoadAndSaveFromLocationRequest(
                location=extracted_url,
                filename=filename,
                artifact_type=VideoUrlArtifact,
            )
        )

        if isinstance(result, LoadAndSaveFromLocationResultSuccess):
            self.parameter_output_values["video"] = result.artifact
            msg = f"Saved video to static storage as {filename}"
            logger.info(msg)
            self._set_status_results(
                was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
            )
        else:
            self.parameter_output_values["video"] = VideoUrlArtifact(value=extracted_url)
            logger.info("Failed to download/save video: %s", result.result_details)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_message(self, response_json: dict[str, Any] | None) -> str:
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
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video"] = None

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
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        if "video" in obj:
            video_obj = obj.get("video")
            if isinstance(video_obj, dict):
                url = video_obj.get("url")
                if isinstance(url, str):
                    return url
        return None
