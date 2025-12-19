from __future__ import annotations

import json as _json
import logging
import os
from contextlib import suppress
from time import monotonic, sleep, time
from typing import Any
from urllib.parse import urljoin

import requests
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["TopazVideoEnhance"]

# Video enhancement models - organized by capability
UPSCALING_MODELS = [
    "prob-4",   # Professional broadcast quality (recommended)
    "rhea-1",   # Generative AI upscaling (4x)
    "aaa-9",    # High-quality upscaling with detail enhancement
    "ahq-12",   # Archival quality upscaling
    "alq-13",   # Low-quality input optimization
    "amq-13",   # Medium-quality enhancement
]

DENOISING_MODELS = [
    "nyx-3",    # Advanced motion processing (recommended)
    "nxf-1",    # Next-gen frame processing (fast)
    "ddv-3",    # Digital video denoising
    "dtd-4",    # Digital temporal denoising
]

FRAME_INTERPOLATION_MODELS = [
    "apo-8",    # Frame interpolation (up to 8x slowmo, recommended)
    "apf-2",    # Fast frame interpolation
    "chr-2",    # Chronos general framerate conversion
    "chf-3",    # Chronos fast
]

SHARPENING_MODELS = [
    "thd-3",    # Texture and detail enhancement (recommended)
    "thf-4",    # Texture high-fidelity
    "thm-2",    # Themis motion deblur
]

ALL_MODELS = UPSCALING_MODELS + DENOISING_MODELS + FRAME_INTERPOLATION_MODELS + SHARPENING_MODELS

# Operation types
OPERATION_OPTIONS = ["upscale", "denoise", "frame_interpolation", "sharpen"]

# Output format options
OUTPUT_FORMAT_OPTIONS = ["mp4", "mov", "webm"]

# Video codecs
VIDEO_CODECS = ["H264", "H265", "ProRes"]

# Upscale factors
UPSCALE_FACTORS = ["2x", "4x", "Auto"]


class TopazVideoEnhance(SuccessFailureNode):
    """Enhance videos using Topaz Labs models via Griptape model proxy.

    This node provides AI-powered video enhancement including upscaling, denoising,
    frame interpolation, and sharpening.

    Inputs:
        - operation (str): Type of enhancement ("upscale", "denoise", "frame_interpolation", "sharpen")
        - model (str): AI model for video enhancement
        - video_url (VideoUrlArtifact): Input video to process
        - upscale_factor (str): Resolution upscaling factor ("2x", "4x", or "Auto")
        - target_fps (int): Target frame rate for frame interpolation
        - slowmo_factor (int): Slow motion factor (1-8)
        - detail_enhancement (float): Enhance fine details and textures (0.0-1.0)
        - noise_reduction (float): Noise reduction intensity (0.0-1.0)
        - sharpening (float): Edge sharpening intensity (0.0-1.0)
        - compression_recovery (float): Remove compression artifacts (0.0-1.0)
        - output_format (str): Output video format
        - video_encoder (str): Video encoding codec
        - processing_timeout (int): Maximum time to wait for processing (minutes)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - video_output (VideoUrlArtifact): Processed video as URL artifact
        - was_successful (bool): Whether the processing succeeded
        - result_details (str): Details about the processing result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Enhance videos using Topaz Labs models via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Operation selection
        self.add_parameter(
            ParameterString(
                name="operation",
                default_value="upscale",
                tooltip="Type of video enhancement operation",
                allow_output=False,
                traits={Options(choices=OPERATION_OPTIONS)},
            )
        )

        # Model selection - will be dynamically updated based on operation
        self.add_parameter(
            ParameterString(
                name="model",
                default_value="prob-4",
                tooltip="AI model for video enhancement",
                allow_output=False,
                traits={Options(choices=UPSCALING_MODELS)},
            )
        )

        # Video URL input using PublicArtifactUrlParameter
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="video_url",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                default_value="",
                tooltip="Input video URL",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Input Video"},
            ),
            disclaimer_message="The Topaz service utilizes this URL to access the video for enhancement.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # Upscale factor (for upscale operation)
        self.add_parameter(
            ParameterString(
                name="upscale_factor",
                default_value="2x",
                tooltip="Resolution upscaling factor",
                allow_output=False,
                traits={Options(choices=UPSCALE_FACTORS)},
            )
        )

        # Target FPS (for frame interpolation)
        self.add_parameter(
            ParameterInt(
                name="target_fps",
                default_value=60,
                tooltip="Target frame rate for frame interpolation",
                allow_output=False,
                slider=True,
                min_val=24,
                max_val=120,
                hide=True,
            )
        )

        # Slow motion factor (for frame interpolation)
        self.add_parameter(
            ParameterInt(
                name="slowmo_factor",
                default_value=1,
                tooltip="Slow motion factor (1 = normal speed, 2-8 = slower)",
                allow_output=False,
                slider=True,
                min_val=1,
                max_val=8,
                hide=True,
            )
        )

        # Detail enhancement
        self.add_parameter(
            ParameterFloat(
                name="detail_enhancement",
                default_value=0.5,
                tooltip="Enhance fine details and textures (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Noise reduction
        self.add_parameter(
            ParameterFloat(
                name="noise_reduction",
                default_value=0.0,
                tooltip="Noise reduction intensity (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Sharpening
        self.add_parameter(
            ParameterFloat(
                name="sharpening",
                default_value=0.0,
                tooltip="Edge sharpening intensity (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Compression recovery
        self.add_parameter(
            ParameterFloat(
                name="compression_recovery",
                default_value=0.0,
                tooltip="Remove compression artifacts (0.0-1.0)",
                allow_output=False,
                slider=True,
                min_val=0.0,
                max_val=1.0,
            )
        )

        # Output format
        self.add_parameter(
            ParameterString(
                name="output_format",
                default_value="mp4",
                tooltip="Output video format",
                allow_output=False,
                traits={Options(choices=OUTPUT_FORMAT_OPTIONS)},
            )
        )

        # Video encoder
        self.add_parameter(
            ParameterString(
                name="video_encoder",
                default_value="H265",
                tooltip="Video encoding codec",
                allow_output=False,
                traits={Options(choices=VIDEO_CODECS)},
            )
        )

        # Processing timeout
        self.add_parameter(
            ParameterInt(
                name="processing_timeout",
                default_value=60,
                tooltip="Maximum time to wait for processing (minutes)",
                allow_output=False,
                slider=True,
                min_val=5,
                max_val=180,
            )
        )

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Generation ID from the API",
                allow_input=False,
                allow_property=False,
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
                name="video_output",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Processed video as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video processing result or any errors",
            result_details_placeholder="Processing status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)

        if parameter.name == "operation":
            model_param = self.get_parameter_by_name("model")
            if model_param:
                if value == "upscale":
                    model_param.traits = {Options(choices=UPSCALING_MODELS)}
                    self.set_parameter_value("model", "prob-4")
                    # Show upscale params
                    self.show_parameter_by_name("upscale_factor")
                    self.show_parameter_by_name("detail_enhancement")
                    self.show_parameter_by_name("sharpening")
                    self.show_parameter_by_name("compression_recovery")
                    # Hide frame interp params
                    self.hide_parameter_by_name("target_fps")
                    self.hide_parameter_by_name("slowmo_factor")
                elif value == "denoise":
                    model_param.traits = {Options(choices=DENOISING_MODELS)}
                    self.set_parameter_value("model", "nyx-3")
                    # Hide most params for denoise
                    self.hide_parameter_by_name("upscale_factor")
                    self.hide_parameter_by_name("detail_enhancement")
                    self.hide_parameter_by_name("sharpening")
                    self.hide_parameter_by_name("target_fps")
                    self.hide_parameter_by_name("slowmo_factor")
                    # Show noise reduction
                    self.show_parameter_by_name("noise_reduction")
                    self.show_parameter_by_name("compression_recovery")
                elif value == "frame_interpolation":
                    model_param.traits = {Options(choices=FRAME_INTERPOLATION_MODELS)}
                    self.set_parameter_value("model", "apo-8")
                    # Show frame interp params
                    self.show_parameter_by_name("target_fps")
                    self.show_parameter_by_name("slowmo_factor")
                    # Hide other params
                    self.hide_parameter_by_name("upscale_factor")
                    self.hide_parameter_by_name("detail_enhancement")
                    self.hide_parameter_by_name("sharpening")
                    self.hide_parameter_by_name("noise_reduction")
                    self.hide_parameter_by_name("compression_recovery")
                elif value == "sharpen":
                    model_param.traits = {Options(choices=SHARPENING_MODELS)}
                    self.set_parameter_value("model", "thd-3")
                    # Show sharpen params
                    self.show_parameter_by_name("sharpening")
                    self.show_parameter_by_name("detail_enhancement")
                    # Hide other params
                    self.hide_parameter_by_name("upscale_factor")
                    self.hide_parameter_by_name("target_fps")
                    self.hide_parameter_by_name("slowmo_factor")
                    self.hide_parameter_by_name("noise_reduction")
                    self.hide_parameter_by_name("compression_recovery")

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        video_url = self.get_parameter_value("video_url")
        if not video_url:
            exceptions.append(ValueError("Video URL must be provided"))
        return exceptions if exceptions else None

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()

    def _process(self) -> None:
        self._clear_execution_status()

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
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with processing.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        timeout_minutes = params.get("processing_timeout", 60)
        self._poll_for_result(generation_id, headers, timeout_minutes * 60)

        # Cleanup
        self._public_video_url_parameter.delete_uploaded_artifact()

    def _get_parameters(self) -> dict[str, Any]:
        operation = self.get_parameter_value("operation") or "upscale"
        params = {
            "operation": operation,
            "model": self.get_parameter_value("model") or "prob-4",
            "video_url": self._public_video_url_parameter.get_public_url_for_parameter(),
            "output_format": self.get_parameter_value("output_format") or "mp4",
            "video_encoder": self.get_parameter_value("video_encoder") or "H265",
            "processing_timeout": self.get_parameter_value("processing_timeout") or 60,
        }

        if operation == "upscale":
            params.update({
                "upscale_factor": self.get_parameter_value("upscale_factor") or "2x",
                "detail_enhancement": self.get_parameter_value("detail_enhancement") or 0.5,
                "sharpening": self.get_parameter_value("sharpening") or 0.0,
                "compression_recovery": self.get_parameter_value("compression_recovery") or 0.0,
            })
        elif operation == "denoise":
            params.update({
                "noise_reduction": self.get_parameter_value("noise_reduction") or 0.5,
                "compression_recovery": self.get_parameter_value("compression_recovery") or 0.0,
            })
        elif operation == "frame_interpolation":
            params.update({
                "target_fps": self.get_parameter_value("target_fps") or 60,
                "slowmo_factor": self.get_parameter_value("slowmo_factor") or 1,
            })
        elif operation == "sharpen":
            params.update({
                "sharpening": self.get_parameter_value("sharpening") or 0.5,
                "detail_enhancement": self.get_parameter_value("detail_enhancement") or 0.5,
            })

        return params

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str:
        payload = self._build_payload(params)
        operation = params["operation"]
        proxy_url = urljoin(self._proxy_base, f"models/topaz-video-{operation}")

        self._log(f"Submitting request to Griptape model proxy for topaz-video-{operation}")
        self._log_request(proxy_url, headers, payload)

        post_resp = requests.post(proxy_url, json=payload, headers=headers, timeout=60)
        if post_resp.status_code >= 400:
            self._set_safe_defaults()
            self._log(f"Proxy POST error status={post_resp.status_code} body={post_resp.text}")
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
            self._log(f"Submitted. generation_id={generation_id}")
        else:
            self._log("No generation_id returned from POST response")

        return generation_id

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": params["model"],
            "video_url": params["video_url"],
            "output_format": params["output_format"],
            "video_encoder": params["video_encoder"],
        }

        operation = params["operation"]

        if operation == "upscale":
            upscale_factor = params.get("upscale_factor", "2x")
            if upscale_factor == "2x":
                payload["upscale_multiplier"] = 2
            elif upscale_factor == "4x":
                payload["upscale_multiplier"] = 4
            # Auto will let the model decide

            if params.get("detail_enhancement", 0) > 0:
                payload["details"] = params["detail_enhancement"]
            if params.get("sharpening", 0) > 0:
                payload["sharpen"] = params["sharpening"]
            if params.get("compression_recovery", 0) > 0:
                payload["compression"] = params["compression_recovery"]

        elif operation == "denoise":
            if params.get("noise_reduction", 0) > 0:
                payload["noise"] = params["noise_reduction"]
            if params.get("compression_recovery", 0) > 0:
                payload["compression"] = params["compression_recovery"]

        elif operation == "frame_interpolation":
            payload["output_fps"] = params.get("target_fps", 60)
            payload["slowmo"] = params.get("slowmo_factor", 1)

        elif operation == "sharpen":
            if params.get("sharpening", 0) > 0:
                payload["sharpen"] = params["sharpening"]
            if params.get("detail_enhancement", 0) > 0:
                payload["details"] = params["detail_enhancement"]

        return payload

    def _log_request(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        dbg_headers = {**headers, "Authorization": "Bearer ***"}
        with suppress(Exception):
            self._log(f"POST {url}\nheaders={dbg_headers}\nbody={_json.dumps(payload, indent=2)}")

    def _poll_for_result(self, generation_id: str, headers: dict[str, str], timeout_s: float) -> None:
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        start_time = monotonic()
        last_json = None
        attempt = 0
        poll_interval_s = 10.0  # Video processing takes longer

        while True:
            if monotonic() - start_time > timeout_s:
                self._log("Polling timed out waiting for result")
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details=f"Video processing timed out after {timeout_s} seconds waiting for result.",
                )
                return

            try:
                get_resp = requests.get(get_url, headers=headers, timeout=60)
                get_resp.raise_for_status()
                last_json = get_resp.json()
                self.parameter_output_values["provider_response"] = last_json
            except Exception as exc:
                self._log(f"GET generation failed: {exc}")
                error_msg = f"Failed to poll generation status: {exc}"
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(RuntimeError(error_msg))
                return

            attempt += 1
            status = self._extract_status(last_json) or "IN_PROGRESS"
            self._log(f"Polling attempt #{attempt} status={status}")

            # Check for explicit failure statuses
            if status.lower() in {"failed", "error"}:
                self._log(f"Processing failed with status: {status}")
                self._set_safe_defaults()
                error_details = self._extract_error_details(last_json)
                self._set_status_results(was_successful=False, result_details=error_details)
                return

            # Check if we have the video - if so, we're done
            video_url = self._extract_video_url(last_json)
            if video_url:
                self._handle_completion(last_json, generation_id)
                return

            sleep(poll_interval_s)

    def _handle_completion(self, last_json: dict[str, Any] | None, generation_id: str | None = None) -> None:
        extracted_url = self._extract_video_url(last_json)
        if not extracted_url:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Processing completed but no video URL was found in the response.",
            )
            return

        try:
            self._log("Downloading video bytes from provider URL")
            video_bytes = self._download_bytes_from_url(extracted_url)
        except Exception as e:
            self._log(f"Failed to download video: {e}")
            video_bytes = None

        if video_bytes:
            try:
                output_format = self.get_parameter_value("output_format") or "mp4"
                filename = (
                    f"topaz_video_{generation_id}.{output_format}"
                    if generation_id
                    else f"topaz_video_{int(time())}.{output_format}"
                )
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_output"] = VideoUrlArtifact(value=saved_url, name=filename)
                self._log(f"Saved video to static storage as {filename}")
                self._set_status_results(
                    was_successful=True, result_details=f"Video processed successfully and saved as {filename}."
                )
            except Exception as e:
                self._log(f"Failed to save to static storage: {e}, using provider URL")
                self.parameter_output_values["video_output"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video processed successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_output"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video processed successfully. Using provider URL (could not download video bytes).",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Processing failed with no error details provided by API."

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
        return f"Processing failed with status '{status}'.\n\nFull API response:\n{response_json}"

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
        return f"Processing failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"Processing failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"Processing failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_output"] = None

    @staticmethod
    def _download_bytes_from_url(url: str) -> bytes | None:
        try:
            resp = requests.get(url, timeout=600)  # 10 min for video
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None

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
        # Try video.url pattern
        if "video" in obj:
            video_obj = obj.get("video")
            if isinstance(video_obj, dict):
                url = video_obj.get("url")
                if isinstance(url, str):
                    return url
        # Try result.sample pattern
        if "result" in obj:
            result_obj = obj.get("result")
            if isinstance(result_obj, dict):
                sample = result_obj.get("sample")
                if isinstance(sample, str):
                    return sample
        return None
