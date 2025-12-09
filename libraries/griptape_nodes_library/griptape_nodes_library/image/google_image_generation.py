from __future__ import annotations

import base64
import io as _io
import json as _json
import logging
import os
from time import time
from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
import PIL.Image
from griptape.artifacts.image_url_artifact import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_float import ParameterFloat
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")

__all__ = ["GoogleImageGeneration"]

# Maximum image counts for reference images
MAX_INPUT_IMAGES = 14
# Deprecated constants - kept for backwards compatibility
MAX_OBJECT_IMAGES = 6
MAX_HUMAN_IMAGES = 5

# Maximum image size in bytes (7MB)
MAX_IMAGE_SIZE_BYTES = 7 * 1024 * 1024


class GoogleImageGeneration(SuccessFailureNode):
    """Generate images using Google Gemini models via Griptape Cloud model proxy."""

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"
    SUPPORTED_MODELS_TO_API_MODELS: ClassVar[dict[str, str]] = {
        "nano-banana-3-pro": "gemini-3-pro-image-preview",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate images using Google Gemini models via Griptape Cloud model proxy"

        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

        # Model ID
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                default_value=next(iter(self.SUPPORTED_MODELS_TO_API_MODELS.keys())),
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model",
                },
                traits={
                    Options(
                        choices=list(self.SUPPORTED_MODELS_TO_API_MODELS.keys()),
                    )
                },
            )
        )

        # Prompt
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Text prompt for image generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Enter prompt..."},
            )
        )

        # Input images (optional, max 14)
        self.add_parameter(
            ParameterList(
                name="input_images",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                default_value=[],
                tooltip="Optional reference images for the generation",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Input Images", "expander": True},
                max_items=MAX_INPUT_IMAGES,
            )
        )

        # Object images (deprecated, hidden - use input_images instead)
        self.add_parameter(
            ParameterList(
                name="object_images",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                default_value=[],
                tooltip="Deprecated: Use input_images instead",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Object Images", "expander": True},
                max_items=MAX_OBJECT_IMAGES,
                hide=True,
            )
        )

        # Human images (deprecated, hidden - use input_images instead)
        self.add_parameter(
            ParameterList(
                name="human_images",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                default_value=[],
                tooltip="Deprecated: Use input_images instead",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"display_name": "Human Images", "expander": True},
                max_items=MAX_HUMAN_IMAGES,
                hide=True,
            )
        )

        # Strict image size validation
        self.add_parameter(
            Parameter(
                name="auto_image_resize",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip=f"If disabled, raises an error when input images exceed the {MAX_IMAGE_SIZE_BYTES / (1024 * 1024)}MB limit. If enabled, oversized images are best-effort scaled to fit within the {MAX_IMAGE_SIZE_BYTES / (1024 * 1024)}MB limit.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Aspect ratio
        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Aspect ratio for generated images",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"])},
            )
        )

        # Image size (resolution)
        self.add_parameter(
            Parameter(
                name="image_size",
                input_types=["str"],
                type="str",
                default_value="1K",
                tooltip="Image size/resolution for generated images",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["1K", "2K", "4K"])},
            )
        )

        # Temperature
        self.add_parameter(
            ParameterFloat(
                name="temperature",
                tooltip="Temperature for controlling generation randomness (0.0-2.0)",
                default_value=1.0,
                slider=True,
                min_val=0.0,
                max_val=2.0,
                step=0.1,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Google Search
        self.add_parameter(
            Parameter(
                name="use_google_search",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Enable Google Search to ground the model's responses",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="image",
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="First generated image as artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="all_images",
                output_type="list[ImageUrlArtifact]",
                type="list[ImageUrlArtifact]",
                tooltip="All generated images",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="text",
                output_type="str",
                type="str",
                tooltip="Text output from the model response",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Text output will appear here."},
                settable=False,
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the image generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []
        prompt = self.get_parameter_value("prompt")
        if not prompt:
            exceptions.append(ValueError(f"{self.name} prompt must be provided"))

        # Get all image lists
        input_images = self.get_parameter_list_value("input_images") or []
        object_images = self.get_parameter_list_value("object_images") or []
        human_images = self.get_parameter_list_value("human_images") or []

        # Validate combined image count does not exceed maximum
        total_images = len(input_images) + len(object_images) + len(human_images)
        if total_images > MAX_INPUT_IMAGES:
            exceptions.append(
                ValueError(f"{self.name} total input images cannot exceed {MAX_INPUT_IMAGES}, got {total_images}")
            )

        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        self._clear_execution_status()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._set_safe_defaults()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        try:
            params = await self._get_parameters()
        except ValueError as e:
            self._handle_failure_exception(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            await self._submit_request_and_process(params, headers)
        except RuntimeError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

    async def _get_parameters(self) -> dict[str, Any]:
        """Build the request payload matching Gemini API structure."""
        prompt = self.get_parameter_value("prompt")
        aspect_ratio = self.get_parameter_value("aspect_ratio")
        image_size = self.get_parameter_value("image_size")
        temperature = self.get_parameter_value("temperature")
        use_google_search = self.get_parameter_value("use_google_search")
        auto_image_resize = self.get_parameter_value("auto_image_resize")

        # Get all image lists and combine them
        input_images = self.get_parameter_list_value("input_images") or []
        object_images = self.get_parameter_list_value("object_images") or []
        human_images = self.get_parameter_list_value("human_images") or []
        all_images = input_images + object_images + human_images

        # Build contents array with prompt and optional images
        parts = []

        # Add prompt first
        if prompt:
            parts.append({"text": prompt})

        # Add all input images
        for img in all_images:
            try:
                result = await self._process_input_image(img, auto_image_resize=auto_image_resize)
            except ValueError as e:
                self._set_safe_defaults()
                self._set_status_results(was_successful=False, result_details=str(e))
                raise
            if result:
                mime_type, image_data = result
                parts.append({"inlineData": {"mimeType": mime_type, "data": image_data}})

        payload = {
            "model": self.SUPPORTED_MODELS_TO_API_MODELS.get(self.get_parameter_value("model")),
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "temperature": temperature,
                "imageConfig": {"aspectRatio": aspect_ratio, "imageSize": image_size},
            },
        }

        # Add Google Search tool if enabled
        if use_google_search:
            payload["tools"] = [{"google_search": {}}]

        return payload

    def _validate_api_key(self) -> str:
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    async def _submit_request_and_process(self, params: dict[str, Any], headers: dict[str, str]) -> None:
        post_url = urljoin(self._proxy_base, f"models/{params['model']}")
        payload = params

        msg = f"{self.name} submitting request to proxy model={params['model']}"
        logger.info(msg)

        try:
            async with httpx.AsyncClient() as client:
                post_resp = await client.post(post_url, json=payload, headers=headers, timeout=None)
                post_resp.raise_for_status()
                response_json = post_resp.json()
        except httpx.HTTPStatusError as e:
            self._set_safe_defaults()
            msg = f"{self.name} proxy POST error status={e.response.status_code} headers={dict(e.response.headers)} body={e.response.text}"
            logger.info(msg)
            try:
                error_json = e.response.json()
                error_details = self._extract_error_details(error_json)
                msg = f"{self.name} {error_details}"
            except Exception:
                msg = f"{self.name} proxy POST error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(msg) from e
        except Exception as e:
            self._set_safe_defaults()
            msg = f"{self.name} proxy POST request failed: {e}"
            logger.info(msg)
            raise RuntimeError(msg) from e

        msg = f"{self.name} received response from API"
        logger.info(msg)

        # Process the response immediately
        await self._handle_response(response_json)

    async def _handle_response(self, response_json: dict[str, Any] | None) -> None:
        """Parse Gemini API response structure and extract images and text."""
        if not response_json:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} received empty response from API.",
            )
            return

        candidates = response_json.get("candidates", [])
        if not candidates:
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} no candidates found in response.",
            )
            return

        image_artifacts = []
        text_outputs = []

        for candidate_idx, candidate in enumerate(candidates):
            self._process_candidate(candidate, candidate_idx, image_artifacts, text_outputs)

        self._store_results(image_artifacts, text_outputs)

    def _process_candidate(
        self,
        candidate: dict[str, Any],
        candidate_idx: int,
        image_artifacts: list[ImageUrlArtifact],
        text_outputs: list[str],
    ) -> None:
        """Process a single candidate and extract images and text."""
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        for part_idx, part in enumerate(parts):
            self._process_part(part, candidate_idx, part_idx, image_artifacts, text_outputs)

    def _process_part(
        self,
        part: dict[str, Any],
        candidate_idx: int,
        part_idx: int,
        image_artifacts: list[ImageUrlArtifact],
        text_outputs: list[str],
    ) -> None:
        """Process a single part and extract text or image data."""
        if "text" in part:
            text_outputs.append(part["text"])

        inline_data = part.get("inlineData")
        if inline_data:
            self._process_inline_image(inline_data, candidate_idx, part_idx, image_artifacts)

    def _process_inline_image(
        self,
        inline_data: dict[str, Any],
        candidate_idx: int,
        part_idx: int,
        image_artifacts: list[ImageUrlArtifact],
    ) -> None:
        """Process inline image data and save to static storage."""
        mime_type = inline_data.get("mimeType", "image/png")
        base64_data = inline_data.get("data", "")

        if not base64_data:
            return

        try:
            image_bytes = base64.b64decode(base64_data)
            timestamp = int(time())
            ext = "png" if "png" in mime_type else "jpg"
            filename = f"google_image_{timestamp}_{candidate_idx}_{part_idx}.{ext}"

            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(image_bytes, filename)
            image_artifacts.append(ImageUrlArtifact(value=saved_url, name=filename))

            msg = f"{self.name} saved image from candidate {candidate_idx + 1}, part {part_idx + 1}"
            logger.info(msg)
        except Exception as e:
            msg = f"{self.name} failed to process image from candidate {candidate_idx + 1}: {e}"
            logger.info(msg)

    def _store_results(self, image_artifacts: list[ImageUrlArtifact], text_outputs: list[str]) -> None:
        """Store image and text results and set status."""
        self.parameter_output_values["text"] = "\n".join(text_outputs) if text_outputs else ""

        if image_artifacts:
            self.parameter_output_values["all_images"] = image_artifacts
            self.parameter_output_values["image"] = image_artifacts[0]
            count = len(image_artifacts)
            details = f"{self.name} generated {count} image{'s' if count > 1 else ''} successfully."
            if text_outputs:
                details += "\n\nModel commentary:\n" + "\n".join(text_outputs)
            self._set_status_results(was_successful=True, result_details=details)
        else:
            self.parameter_output_values["image"] = None
            self.parameter_output_values["all_images"] = []
            details = f"{self.name} no images found in response."
            if text_outputs:
                details += "\n\nModel text output:\n" + "\n".join(text_outputs)
            self._set_status_results(was_successful=False, result_details=details)

    def _extract_error_details(self, response_json: dict[str, Any] | None) -> str:
        """Extract error details from API response."""
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        top_level_error = response_json.get("error")
        parsed_provider_response = self._parse_provider_response(response_json.get("provider_response"))

        provider_error_msg = self._format_provider_error(parsed_provider_response, top_level_error)
        if provider_error_msg:
            return provider_error_msg

        if top_level_error:
            return self._format_top_level_error(top_level_error)

        status = self._extract_status(response_json) or "unknown"
        return f"{self.name} generation failed with status '{status}'.\n\nFull API response:\n{response_json}"

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
            details = f"{self.name} {error_message}"

            if error_code := provider_error.get("code"):
                details += f"\nError Code: {error_code}"
            if error_type := provider_error.get("type"):
                details += f"\nError Type: {error_type}"
            if top_level_error:
                details = f"{self.name} {top_level_error}\n\n{details}"
            return details

        error_msg = str(provider_error)
        if top_level_error:
            return f"{self.name} {top_level_error}\n\nProvider error: {error_msg}"
        return f"{self.name} generation failed. Provider error: {error_msg}"

    def _format_top_level_error(self, top_level_error: Any) -> str:
        """Format error message from top-level error field."""
        if isinstance(top_level_error, dict):
            error_msg = top_level_error.get("message") or top_level_error.get("error") or str(top_level_error)
            return f"{self.name} generation failed with error: {error_msg}\n\nFull error details:\n{top_level_error}"
        return f"{self.name} generation failed with error: {top_level_error!s}"

    def _set_safe_defaults(self) -> None:
        self.parameter_output_values["image"] = None
        self.parameter_output_values["all_images"] = []
        self.parameter_output_values["text"] = ""

    async def _process_input_image(self, image_input: Any, *, auto_image_resize: bool = True) -> tuple[str, str] | None:
        """Process input image and convert to base64 with mime type.

        Args:
            image_input: The image input to process
            auto_image_resize: If False, raises ValueError for oversized images instead of auto-resizing

        Returns:
            Tuple of (mime_type, base64_data) or None if processing fails

        Raises:
            ValueError: If auto_image_resize is False and the image exceeds the size limit
        """
        if not image_input:
            return None

        image_value = self._extract_image_value(image_input)
        if not image_value:
            return None

        data_uri = await self._convert_to_base64_data_uri(image_value)
        if not data_uri:
            return None

        return self._extract_mime_and_base64_from_data_uri(data_uri, auto_image_resize=auto_image_resize)

    def _extract_mime_and_base64_from_data_uri(
        self, data_uri: str, *, auto_image_resize: bool = True
    ) -> tuple[str, str] | None:
        """Extract mime type and base64 data from data URI.

        Args:
            data_uri: The data URI string to extract from
            auto_image_resize: If False, raises ValueError for oversized images instead of auto-resizing

        Returns:
            Tuple of (mime_type, base64_data) or None if extraction fails

        Raises:
            ValueError: If auto_image_resize is False and the image exceeds the size limit
        """
        if not data_uri.startswith("data:image/"):
            return None

        parts = data_uri.split(",", 1)
        if len(parts) < 1:
            return None

        mime_part = parts[0]
        if "image/" not in mime_part:
            return None

        mime_type = self._parse_mime_type_from_header(mime_part)
        if not mime_type:
            return None

        base64_data = parts[1] if len(parts) > 1 else ""
        if not base64_data:
            return None

        return self._validate_image_size(base64_data, mime_type, auto_image_resize=auto_image_resize)

    def _parse_mime_type_from_header(self, mime_part: str) -> str | None:
        """Parse mime type from data URI header.

        Args:
            mime_part: Header part of data URI (e.g., "data:image/png;base64")

        Returns:
            Mime type string or None if parsing fails
        """
        try:
            return mime_part.split(":")[1].split(";")[0]
        except IndexError:
            return None

    def _shrink_image(self, image_bytes: bytes) -> bytes:
        """Best-effort shrink using Pillow to ensure <= byte_limit while maximizing quality.

        Uses a strategy that finds the largest file size (best quality) that still
        fits under the limit, rather than returning the first valid result.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Possibly converted/compressed bytes, or original if shrinking fails
        """
        try:
            img = PIL.Image.open(_io.BytesIO(image_bytes))
            img = img.convert("RGBA") if img.mode in ("P", "LA") else img
            # Prefer WEBP for better compression and alpha support
            target_format = "WEBP"

            orig_w, orig_h = img.size

            # Try lossless first (best quality)
            buf = _io.BytesIO()
            img.save(buf, format=target_format, lossless=True, method=6)
            data = buf.getvalue()
            image_size_bytes = len(data)
            logger.info(
                "%s downscale attempt: lossless size=%.2fMB",
                self.name,
                image_size_bytes / (1024 * 1024),
            )
            if image_size_bytes <= MAX_IMAGE_SIZE_BYTES:
                logger.info("%s shrunk image to %.2fMB (lossless)", self.name, image_size_bytes / (1024 * 1024))
                return data

            # Finer-grained scales for better quality preservation
            scales = [1.0, 0.75, 0.5]
            qualities = [100, 95, 85]

            for scale in scales:
                w = max(1, int(orig_w * scale))
                h = max(1, int(orig_h * scale))
                resized = img.resize((w, h)) if (w, h) != (orig_w, orig_h) else img

                for q in qualities:
                    buf = _io.BytesIO()
                    resized.save(buf, format=target_format, quality=q, method=6)
                    data = buf.getvalue()
                    image_size_bytes = len(data)
                    logger.info(
                        "%s downscale attempt: scale=%.2f quality=%d size=%.2fMB",
                        self.name,
                        scale,
                        q,
                        image_size_bytes / (1024 * 1024),
                    )
                    if image_size_bytes <= MAX_IMAGE_SIZE_BYTES:
                        logger.info("%s shrunk image to %.2fMB (q=%d)", self.name, image_size_bytes / (1024 * 1024), q)
                        return data
        except Exception as e:
            logger.warning("%s downscale failed: %s", self.name, e)
        logger.warning("%s returning original image bytes after downscale attempts", self.name)
        return image_bytes

    def _validate_image_size(
        self, base64_data: str, mime_type: str, *, auto_image_resize: bool = True
    ) -> tuple[str, str] | None:
        """Validate image size and optionally shrink if too large.

        Args:
            base64_data: Base64 encoded image data
            mime_type: Original MIME type of the image
            auto_image_resize: If False, raises ValueError for oversized images instead of auto-resizing

        Returns:
            Tuple of (mime_type, base64_data) - possibly shrunk, or None if decode fails

        Raises:
            ValueError: If auto_image_resize is False and the image exceeds the size limit
        """
        try:
            image_bytes = base64.b64decode(base64_data)
        except Exception as e:
            msg = f"{self.name} failed to decode image: {e}"
            logger.warning(msg)
            return None

        image_size = len(image_bytes)
        if image_size <= MAX_IMAGE_SIZE_BYTES:
            return (mime_type, base64_data)

        size_mb = image_size / (1024 * 1024)
        max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)

        if not auto_image_resize:
            msg = f"{self.name} input image exceeds maximum size of {max_mb:.0f}MB (image is {size_mb:.2f}MB)"
            raise ValueError(msg)

        # Try to shrink the image
        logger.info("%s image is %.2fMB, attempting to shrink...", self.name, size_mb)
        shrunk_bytes = self._shrink_image(image_bytes)

        if len(shrunk_bytes) <= MAX_IMAGE_SIZE_BYTES:
            # Successfully shrunk - encode back to base64 with new WEBP mime type
            new_base64 = base64.b64encode(shrunk_bytes).decode("utf-8")
            return ("image/webp", new_base64)

        # Couldn't shrink enough, return original
        logger.warning("%s could not shrink image below %.0fMB limit, using original", self.name, max_mb)
        return (mime_type, base64_data)

    def _extract_image_value(self, image_input: Any) -> str | None:
        """Extract string value from various image input types."""
        if isinstance(image_input, str):
            return image_input

        try:
            # ImageUrlArtifact: .value holds URL string
            if hasattr(image_input, "value"):
                value = getattr(image_input, "value", None)
                if isinstance(value, str):
                    return value

            # ImageArtifact: .base64 holds raw or data-URI
            if hasattr(image_input, "base64"):
                b64 = getattr(image_input, "base64", None)
                if isinstance(b64, str) and b64:
                    return b64
        except Exception as e:
            msg = f"{self.name} failed to extract image value: {e}"
            logger.info(msg)

        return None

    async def _convert_to_base64_data_uri(self, image_value: str) -> str | None:
        """Convert image value to base64 data URI."""
        # If it's already a data URI, return it
        if image_value.startswith("data:image/"):
            return image_value

        # If it's a URL, download and convert to base64
        if image_value.startswith(("http://", "https://")):
            return await self._download_and_encode_image(image_value)

        # Assume it's raw base64 without data URI prefix
        return f"data:image/png;base64,{image_value}"

    async def _download_and_encode_image(self, url: str) -> str | None:
        """Download image from URL and encode as base64 data URI."""
        try:
            image_bytes = await self._download_bytes_from_url(url)
            if image_bytes:
                b64_string = base64.b64encode(image_bytes).decode("utf-8")
                return f"data:image/png;base64,{b64_string}"
        except Exception as e:
            msg = f"{self.name} failed to download image from URL {url}: {e}"
            logger.info(msg)
        return None

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

    @staticmethod
    def _extract_status(obj: dict[str, Any] | None) -> str | None:
        if not obj:
            return None
        if "status" in obj:
            status_val = obj.get("status")
            if isinstance(status_val, str):
                return status_val
        return None
