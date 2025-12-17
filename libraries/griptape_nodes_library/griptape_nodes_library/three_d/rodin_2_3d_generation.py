from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_bool import ParameterBool
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.three_d.three_d_artifact import ThreeDUrlArtifact

logger = logging.getLogger("griptape_nodes")

__all__ = ["Rodin23DGeneration"]

# Maximum number of input images supported
MAX_INPUT_IMAGES = 5

# Output format options
GEOMETRY_FORMAT_OPTIONS = ["glb", "usdz", "fbx", "obj", "stl"]
DEFAULT_GEOMETRY_FORMAT = "glb"

# Material options
MATERIAL_OPTIONS = ["PBR", "Shaded", "All"]
DEFAULT_MATERIAL = "PBR"

# Quality options (mesh detail level)
QUALITY_OPTIONS = ["high", "medium", "low", "extra-low"]
DEFAULT_QUALITY = "medium"

# Mesh mode options
MESH_MODE_OPTIONS = ["Quad", "Raw"]
DEFAULT_MESH_MODE = "Quad"

# Condition mode options for multi-image generation
CONDITION_MODE_OPTIONS = ["concat", "fuse"]
DEFAULT_CONDITION_MODE = "concat"

# Response status constants
STATUS_FAILED = "Failed"
STATUS_ERROR = "Error"
STATUS_READY = "Ready"


class Rodin23DGeneration(SuccessFailureNode):
    """Generate 3D models using Rodin Gen-2 via Griptape model proxy.

    Inputs:
        - prompt (str): Text description for Text-to-3D generation or description for Image-to-3D
        - input_images (list): Optional input images for Image-to-3D generation (up to 5)
        - condition_mode (str): Multi-image mode - "concat" for multi-view of same object, "fuse" for combining objects
        - geometry_file_format (str): Output 3D file format (glb, usdz, fbx, obj, stl)
        - material (str): Material type - PBR (physically based) or Shaded (baked lighting)
        - quality (str): Mesh quality - high (50k faces), medium (18k), low (8k), extra-low (4k)
        - mesh_mode (str): Face type - Quad (quadrilateral) or Raw (triangular)
        - randomize_seed (bool): If true, randomize the seed on each run (default: False)
        - seed (int): Random seed for reproducible results (default: 42)

    Outputs:
        - generation_id (str): Generation ID from the API
        - provider_response (dict): Verbatim provider response from the model proxy
        - model_url (ThreeDUrlArtifact): Generated 3D model as URL artifact
        - all_files (list): URLs of all generated files
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate 3D models using Rodin Gen-2 via Griptape model proxy"

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Core parameters - prompt
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text description for 3D model generation (required for Text-to-3D, optional for Image-to-3D)",
                multiline=True,
                placeholder_text="Describe the 3D model you want to generate...",
                allow_output=False,
                ui_options={
                    "display_name": "Prompt",
                },
            )
        )

        # Optional input images for Image-to-3D generation
        self.add_parameter(
            ParameterList(
                name="input_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                ],
                default_value=[],
                tooltip="Optional input images for Image-to-3D generation (up to 5 images)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"expander": True, "display_name": "Input Images"},
            )
        )

        # Condition mode for multi-image generation
        self.add_parameter(
            ParameterString(
                name="condition_mode",
                default_value=DEFAULT_CONDITION_MODE,
                tooltip="Multi-image mode: 'concat' for multi-view of same object, 'fuse' for combining multiple objects",
                allow_output=False,
                traits={Options(choices=CONDITION_MODE_OPTIONS)},
                ui_options={"display_name": "Multi-Image Mode"},
            )
        )

        # Geometry file format parameter
        self.add_parameter(
            ParameterString(
                name="geometry_file_format",
                default_value=DEFAULT_GEOMETRY_FORMAT,
                tooltip="Output 3D file format",
                allow_output=False,
                traits={Options(choices=GEOMETRY_FORMAT_OPTIONS)},
                ui_options={"display_name": "File Format"},
            )
        )

        # Material parameter
        self.add_parameter(
            ParameterString(
                name="material",
                default_value=DEFAULT_MATERIAL,
                tooltip="Material type: PBR (physically based rendering) or Shaded (baked lighting)",
                allow_output=False,
                traits={Options(choices=MATERIAL_OPTIONS)},
            )
        )

        # Quality parameter
        self.add_parameter(
            ParameterString(
                name="quality",
                default_value=DEFAULT_QUALITY,
                tooltip="Mesh quality: high (50k faces), medium (18k), low (8k), extra-low (4k)",
                allow_output=False,
                traits={Options(choices=QUALITY_OPTIONS)},
            )
        )

        # Mesh mode parameter
        self.add_parameter(
            ParameterString(
                name="mesh_mode",
                default_value=DEFAULT_MESH_MODE,
                tooltip="Face type: Quad (quadrilateral faces) or Raw (triangular faces)",
                allow_output=False,
                traits={Options(choices=MESH_MODE_OPTIONS)},
                ui_options={"display_name": "Mesh Mode"},
            )
        )

        # Advanced parameters (hidden by default)

        # Use original alpha parameter
        self.add_parameter(
            ParameterBool(
                name="use_original_alpha",
                default_value=False,
                tooltip="If true, the original transparency channel of the images will be used when processing",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "Use Original Alpha"},
            )
        )

        # Quality override parameter
        self.add_parameter(
            ParameterInt(
                name="quality_override",
                default_value=None,
                tooltip="Custom poly count (Quad: 1,000-200,000, Raw: 500-1,000,000). Overrides quality setting. Recommend 150,000+ for Gen-2.",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "Quality Override"},
            )
        )

        # T/A Pose parameter
        self.add_parameter(
            ParameterBool(
                name="ta_pose",
                default_value=False,
                tooltip="Force T/A pose for human-like models",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "T/A Pose"},
            )
        )

        # Bounding box condition parameter
        self.add_parameter(
            ParameterString(
                name="bbox_condition",
                default_value="",
                tooltip="Bounding box dimensions as comma-separated values: Width(Y), Height(Z), Length(X). Example: 1.0,2.0,3.0",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "Bounding Box (Y,Z,X)"},
            )
        )

        # HighPack addon parameter
        self.add_parameter(
            ParameterBool(
                name="high_pack",
                default_value=False,
                tooltip="Enable HighPack addon: 4K textures instead of 2K, and 16x face count in Quad mode",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "HighPack (4K Textures)"},
            )
        )

        # Preview render parameter
        self.add_parameter(
            ParameterBool(
                name="preview_render",
                default_value=False,
                tooltip="If true, an additional high-quality render image will be provided in the download list",
                allow_output=False,
                hide=True,
                ui_options={"display_name": "Preview Render"},
            )
        )

        # Seed parameter (using SeedParameter component)
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

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
                name="model_url",
                output_type="ThreeDUrlArtifact",
                type="ThreeDUrlArtifact",
                tooltip="Generated 3D model as URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True, "display_name": "3D Model"},
            )
        )

        self.add_parameter(
            Parameter(
                name="all_files",
                output_type="list",
                type="list",
                tooltip="URLs of all generated files",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "All Files"},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the 3D generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        super().after_value_set(parameter, value)
        self._seed_parameter.after_value_set(parameter, value)

    def preprocess(self) -> None:
        self._seed_parameter.preprocess()

    async def aprocess(self) -> None:
        await self._process()

    async def _process(self) -> None:
        # Preprocess to handle seed randomization
        self.preprocess()

        # Clear execution status at the start
        self._clear_execution_status()

        try:
            params = self._get_parameters()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Validate that we have either images or a prompt
        has_images = bool(params.get("input_images"))
        has_prompt = bool(params.get("prompt", "").strip())
        if not has_images and not has_prompt:
            self._set_safe_defaults()
            error_msg = "Either images or a prompt must be provided for 3D generation."
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
            return

        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}"}

        self._log("Generating 3D model with Rodin Gen-2")

        # Submit request to get generation ID
        try:
            generation_id = await self._submit_request(params, headers)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Poll for result
        await self._poll_for_result(generation_id, headers, params)

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "prompt": self.get_parameter_value("prompt") or "",
            "input_images": self.get_parameter_list_value("input_images") or [],
            "condition_mode": self.get_parameter_value("condition_mode") or DEFAULT_CONDITION_MODE,
            "geometry_file_format": self.get_parameter_value("geometry_file_format") or DEFAULT_GEOMETRY_FORMAT,
            "material": self.get_parameter_value("material") or DEFAULT_MATERIAL,
            "quality": self.get_parameter_value("quality") or DEFAULT_QUALITY,
            "mesh_mode": self.get_parameter_value("mesh_mode") or DEFAULT_MESH_MODE,
            "seed": self._seed_parameter.get_seed(),
            # Advanced parameters
            "use_original_alpha": self.get_parameter_value("use_original_alpha") or False,
            "quality_override": self.get_parameter_value("quality_override"),
            "ta_pose": self.get_parameter_value("ta_pose") or False,
            "bbox_condition": self.get_parameter_value("bbox_condition") or "",
            "high_pack": self.get_parameter_value("high_pack") or False,
            "preview_render": self.get_parameter_value("preview_render") or False,
        }

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request(self, params: dict[str, Any], headers: dict[str, str]) -> str | None:
        form_data, files = await self._build_form_data(params)
        proxy_url = urljoin(self._proxy_base, "models/rodin-gen2")

        self._log("Submitting request to Griptape model proxy with rodin-gen2")
        self._log_form_data(form_data, len(files))

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    proxy_url,
                    data=form_data,
                    files=files,
                    headers=headers,
                    timeout=120,
                )
                response.raise_for_status()
                response_json = response.json()
                self._log("Request submitted successfully")
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            try:
                error_json = e.response.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{error_details}"
            except Exception:
                msg = f"API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        # Extract generation_id from response
        generation_id = response_json.get("generation_id")
        if generation_id:
            self.parameter_output_values["generation_id"] = str(generation_id)
            self._log(f"Submitted. generation_id={generation_id}")
            return str(generation_id)
        self._log("No generation_id returned from POST response")
        return None

    async def _build_form_data(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], list[tuple[str, tuple[str, bytes, str]]]]:
        """Build multipart form data for the Rodin API."""
        form_data: dict[str, Any] = {
            "tier": "Gen-2",  # Always use Gen-2 for this node
            "geometry_file_format": params["geometry_file_format"],
            "material": params["material"],
            "quality": params["quality"],
            "mesh_mode": params["mesh_mode"],
        }

        # Add optional parameters
        self._add_optional_params(form_data, params)
        self._add_advanced_params(form_data, params)

        # Process images into file tuples for multipart upload
        files = await self._process_images_for_upload(params)

        # Add condition_mode for multi-image generation
        if len(files) > 1:
            form_data["condition_mode"] = params["condition_mode"]

        return form_data, files

    def _add_optional_params(self, form_data: dict[str, Any], params: dict[str, Any]) -> None:
        """Add optional seed and prompt parameters to form data."""
        if params.get("seed") is not None:
            form_data["seed"] = params["seed"]

        prompt = params.get("prompt", "").strip()
        if prompt:
            form_data["prompt"] = prompt

    def _add_advanced_params(self, form_data: dict[str, Any], params: dict[str, Any]) -> None:
        """Add advanced optional parameters to form data."""
        if params.get("use_original_alpha"):
            form_data["use_original_alpha"] = "true"

        if params.get("quality_override") is not None:
            form_data["quality_override"] = params["quality_override"]

        if params.get("ta_pose"):
            form_data["TAPose"] = "true"  # API uses TAPose

        self._add_bbox_condition(form_data, params)

        if params.get("high_pack"):
            form_data["addons"] = "HighPack"

        if params.get("preview_render"):
            form_data["preview_render"] = "true"

    def _add_bbox_condition(self, form_data: dict[str, Any], params: dict[str, Any]) -> None:
        """Parse and add bounding box condition to form data."""
        bbox_condition = params.get("bbox_condition", "").strip()
        if not bbox_condition:
            return

        try:
            # Parse comma-separated values: Width(Y), Height(Z), Length(X)
            values = [int(float(v.strip())) for v in bbox_condition.split(",")]
            bbox_dimensions = 3
            if len(values) == bbox_dimensions:
                # Send as JSON array string for form data
                form_data["bbox_condition"] = _json.dumps(values)
        except ValueError:
            self._log(f"Invalid bbox_condition format: {bbox_condition}")

    async def _process_images_for_upload(self, params: dict[str, Any]) -> list[tuple[str, tuple[str, bytes, str]]]:
        """Process input images into file tuples for multipart upload."""
        input_images_list = params.get("input_images", [])
        if not isinstance(input_images_list, list):
            input_images_list = [input_images_list] if input_images_list else []

        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for idx, image_input in enumerate(input_images_list):
            if len(files) >= MAX_INPUT_IMAGES:
                break

            image_bytes = await self._get_image_bytes(image_input)
            if image_bytes:
                # All images use the same field name "images" for multipart
                files.append(("images", (f"image_{idx}.png", image_bytes, "image/png")))

        return files

    async def _get_image_bytes(self, image_input: Any) -> bytes | None:
        """Get raw bytes from an image input."""
        if not image_input:
            return None

        # Handle string inputs (URL or base64)
        if isinstance(image_input, str):
            return await self._string_to_bytes(image_input)

        # Handle ImageUrlArtifact
        if hasattr(image_input, "value"):
            value = getattr(image_input, "value", None)
            if isinstance(value, str):
                return await self._string_to_bytes(value)

        # Handle ImageArtifact with base64 property
        if hasattr(image_input, "base64"):
            b64 = getattr(image_input, "base64", None)
            if isinstance(b64, str) and b64:
                return await self._string_to_bytes(b64)

        return None

    async def _string_to_bytes(self, value: str) -> bytes | None:
        """Convert a string (URL or base64) to raw bytes."""
        import base64

        # If it's a URL, download the image
        if value.startswith(("http://", "https://")):
            return await self._download_bytes_from_url(value)

        # If it's a data URI, extract and decode the base64 part
        if value.startswith("data:image/"):
            try:
                # Format: data:image/png;base64,<base64data>
                _, b64_data = value.split(",", 1)
                return base64.b64decode(b64_data)
            except Exception as e:
                self._log(f"Failed to decode data URI: {e}")
                return None

        # Assume it's raw base64
        try:
            return base64.b64decode(value)
        except Exception as e:
            self._log(f"Failed to decode base64: {e}")
            return None

    def _log_form_data(self, form_data: dict[str, Any], num_files: int) -> None:
        """Log form data for debugging (without sensitive data)."""
        with suppress(Exception):
            self._log(f"Form data: {_json.dumps(form_data, indent=2)}")
            self._log(f"Number of image files: {num_files}")

    async def _poll_for_result(self, generation_id: str, headers: dict[str, str], params: dict[str, Any]) -> None:
        """Poll the generations endpoint until ready."""
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = 240  # 20 minutes with 5s intervals (3D generation can take longer)
        poll_interval = 5

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"Polling attempt #{attempt + 1} for generation {generation_id}")
                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    result_json = response.json()

                    # Update provider_response with latest polling data
                    self.parameter_output_values["provider_response"] = result_json

                    status = result_json.get("status", "unknown")
                    self._log(f"Status: {status}")

                    if status == STATUS_READY:
                        # Extract the result files
                        result = result_json.get("result", {})
                        await self._handle_success(result_json, result, params)
                        return
                    if status in [STATUS_FAILED, STATUS_ERROR]:
                        self._log(f"Generation failed with status: {status}")
                        self._set_safe_defaults()
                        error_details = self._extract_error_details(result_json)
                        self._set_status_results(was_successful=False, result_details=error_details)
                        return

                    # Still processing, wait before next poll
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(poll_interval)

                except httpx.HTTPStatusError as e:
                    self._log(f"HTTP error while polling: {e.response.status_code} - {e.response.text}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: HTTP {e.response.status_code}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return
                except Exception as e:
                    self._log(f"Error while polling: {e}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: {e}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return

            # Timeout reached
            self._log("Polling timed out waiting for result")
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"3D generation timed out after {max_attempts * poll_interval} seconds waiting for result.",
            )

    async def _handle_success(self, response: dict[str, Any], result: dict[str, Any], params: dict[str, Any]) -> None:
        """Handle successful generation result."""
        self.parameter_output_values["provider_response"] = response

        # Get all file URLs from result - the proxy returns 'downloads' list
        files = result.get("downloads", [])
        if not files:
            # Try alternate response formats
            files = result.get("files", [])
        if not files:
            sample_url = result.get("sample")
            if sample_url:
                files = [{"url": sample_url, "name": f"model.{params['geometry_file_format']}"}]

        if not files:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no files were found in the response.",
            )
            return

        # Download and save all files
        await self._save_model_files(files, params)

    async def _save_model_files(self, files: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Download and save the generated 3D model files."""
        requested_format = params["geometry_file_format"]
        timestamp = int(time.time())
        static_files_manager = GriptapeNodes.StaticFilesManager()

        all_file_urls: list[str] = []
        primary_url: str | None = None
        primary_filename: str | None = None

        for idx, file_info in enumerate(files):
            file_url = file_info.get("url")
            file_name = file_info.get("name", f"model_{idx}.{requested_format}")

            if not file_url:
                continue

            try:
                self._log(f"Downloading file: {file_name}")
                file_bytes = await self._download_bytes_from_url(file_url)

                if file_bytes:
                    # Create safe filename
                    extension = file_name.rsplit(".", 1)[-1] if "." in file_name else requested_format
                    base_name = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
                    static_filename = f"rodin2_3d_{timestamp}_{idx}_{base_name}.{extension}"

                    saved_url = static_files_manager.save_static_file(
                        file_bytes, static_filename, ExistingFilePolicy.CREATE_NEW
                    )
                    all_file_urls.append(saved_url)
                    self._log(f"Saved file: {static_filename}")

                    # Track primary model file
                    if file_name.lower().endswith(f".{requested_format}") and primary_url is None:
                        primary_url = saved_url
                        primary_filename = static_filename
                    elif primary_url is None:
                        # Use first file as fallback
                        primary_url = saved_url
                        primary_filename = static_filename

            except Exception as e:
                self._log(f"Failed to save file {file_name}: {e}")

        # Set outputs
        self.parameter_output_values["all_files"] = all_file_urls

        if primary_url:
            self.parameter_output_values["model_url"] = ThreeDUrlArtifact(
                value=primary_url,
                meta={"filename": primary_filename, "format": requested_format},
            )
            self._set_status_results(
                was_successful=True,
                result_details=f"3D model generated successfully. Saved {len(all_file_urls)} file(s).",
            )
        else:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but failed to save model files.",
            )

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return "Generation failed with no error details provided by API."

        # Try various error sources in order of priority
        error_msg = self._get_error_from_result(response_json)
        if not error_msg:
            error_msg = self._get_error_from_provider(response_json)
        if not error_msg:
            error_msg = self._get_error_from_top_level(response_json)
        if not error_msg:
            error_msg = self._get_error_from_status(response_json)

        return error_msg or f"Generation failed.\n\nFull API response:\n{response_json}"

    def _get_error_from_result(self, response_json: dict[str, Any]) -> str | None:
        """Extract error from result field."""
        result = response_json.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return f"Generation failed: {result['error']}"
        return None

    def _get_error_from_provider(self, response_json: dict[str, Any]) -> str | None:
        """Extract error from provider_response field."""
        provider_response = response_json.get("provider_response")
        if provider_response:
            parsed = self._parse_provider_response(provider_response)
            if parsed and parsed.get("error"):
                return f"Generation failed: {parsed['error']}"
        return None

    def _get_error_from_top_level(self, response_json: dict[str, Any]) -> str | None:
        """Extract error from top-level error field."""
        top_level_error = response_json.get("error")
        if top_level_error:
            if isinstance(top_level_error, dict):
                return f"Generation failed: {top_level_error.get('message', str(top_level_error))}"
            return f"Generation failed: {top_level_error}"
        return None

    def _get_error_from_status(self, response_json: dict[str, Any]) -> str | None:
        """Extract error from status field."""
        status = response_json.get("status")
        if status in [STATUS_FAILED, STATUS_ERROR]:
            return f"Generation failed with status '{status}'."
        return None

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

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["model_url"] = None
        self.parameter_output_values["all_files"] = []

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
