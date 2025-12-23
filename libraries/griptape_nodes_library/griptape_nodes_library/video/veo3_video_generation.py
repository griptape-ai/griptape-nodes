from __future__ import annotations

import base64
import logging
from contextlib import suppress
from typing import Any

from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.seed_parameter import SeedParameter
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["Veo3VideoGeneration"]

# Model mapping from human-friendly names to API model IDs
MODEL_MAPPING = {
    "Veo 3.1": "veo-3.1-generate-preview",
    "Veo 3.1 Fast": "veo-3.1-fast-generate-preview",
    "Veo 3.0": "veo-3.0-generate-001",
    "Veo 3.0 Fast": "veo-3.0-fast-generate-001",
}


class Veo3VideoGeneration(GriptapeProxyNode):
    """Generate a video using Google's Veo3 model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video
        - model_id (str): Provider model (default: Veo 3.1, options: Veo 3.1, Veo 3.1 Fast, Veo 3.0, Veo 3.0 Fast)
        - negative_prompt (str): Negative prompt to avoid certain content
        - image (ImageArtifact|ImageUrlArtifact|str): Optional start frame image (supported by all models)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image (only Veo 3.1 and Veo 3.1 Fast)
        - reference_images (list[ImageArtifact]|list[ImageUrlArtifact]|list[str]): Optional reference images (only Veo 3.1, max 3 for asset, max 1 for style)
        - reference_type (str): Reference type (default: asset, options: asset, style)
        - aspect_ratio (str): Output aspect ratio (default: 16:9, options: 16:9, 9:16)
        - resolution (str): Output resolution (default: 720p, options: 720p, 1080p)
        - duration_seconds (str): Video duration in seconds (default: 6, options: 4, 6, 8; must be 8 when referenceImages provided)
        - person_generation (str): Person generation policy (default: allow_adult, options: allow_all, allow_adult, dont_allow)
        - generate_audio (bool): Generate audio for the video (default: True, supported by all veo3* models)
        - randomize_seed (bool): If true, randomize the seed on each run (default: False)
        - seed (int): Random seed for reproducible results (default: 42)
        - sample_count (int): Number of videos to generate (default: 1, range: 1-4)
        (Always polls for result: 5s interval, 10 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL(s) - up to 4 video outputs based on sample_count
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="Veo 3.1",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "model",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "Veo 3.1",
                            "Veo 3.1 Fast",
                            "Veo 3.0",
                            "Veo 3.0 Fast",
                        ]
                    )
                },
            )
        )

        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt for the video",
                multiline=True,
                placeholder_text="Describe the video...",
                allow_output=False,
                ui_options={
                    "display_name": "prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="negative_prompt",
                input_types=["str"],
                type="str",
                default_value="",
                tooltip="Negative prompt to avoid certain content",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Content to avoid...",
                    "display_name": "negative prompt",
                },
            )
        )

        # Image parameters
        self.add_parameter(
            Parameter(
                name="start_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional start frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "start frame"},
            )
        )

        self.add_parameter(
            Parameter(
                name="last_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional last frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "last frame"},
            )
        )

        # Reference images (up to 3)
        self.add_parameter(
            ParameterList(
                name="reference_images",
                input_types=[
                    "ImageArtifact",
                    "ImageUrlArtifact",
                    "str",
                    "list[ImageArtifact]",
                    "list[ImageUrlArtifact]",
                    "list[str]",
                ],
                default_value=[],
                tooltip="Optional reference images for style and content (max 3 for asset, max 1 for style)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "reference images"},
            )
        )

        # Reference type for reference images
        self.add_parameter(
            Parameter(
                name="reference_type",
                input_types=["str"],
                type="str",
                default_value="asset",
                tooltip="Type of reference: 'asset' preserves objects/characters (max 3), 'style' preserves artistic style (max 1)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["asset", "style"])},
            )
        )

        # Aspect ratio selection
        self.add_parameter(
            Parameter(
                name="aspect_ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16"])},
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="720p",
                tooltip="Output resolution (1080p only supports 8 second duration)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["720p", "1080p"])},
            )
        )

        # Duration in seconds
        self.add_parameter(
            Parameter(
                name="duration_seconds",
                input_types=["str"],
                type="str",
                default_value="6",
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["4", "6", "8"])},
            )
        )

        # Person generation policy
        self.add_parameter(
            Parameter(
                name="person_generation",
                input_types=["str"],
                type="str",
                default_value="allow_adult",
                tooltip="Person generation policy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["allow_all", "allow_adult", "dont_allow"])},
            )
        )

        # Generate audio option
        self.add_parameter(
            Parameter(
                name="generate_audio",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Generate audio for the video (supported by all veo3* models)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "generate audio"},
            )
        )

        # Initialize SeedParameter component (adds randomize_seed and seed parameters)
        self._seed_parameter = SeedParameter(self)
        self._seed_parameter.add_input_parameters()

        # Sample count (number of videos to generate)
        self.add_parameter(
            Parameter(
                name="sample_count",
                input_types=["int"],
                type="int",
                default_value=1,
                tooltip="Number of videos to generate (1-4)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "sample count"},
                traits={Slider(min_val=1, max_val=4)},
            )
        )

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

        # Create video output parameters (up to 4)
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            self.add_parameter(
                Parameter(
                    name=param_name,
                    output_type="VideoUrlArtifact",
                    type="VideoUrlArtifact",
                    tooltip=f"Saved video {i} as URL artifact for downstream display",
                    allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                    settable=False,
                    ui_options={"is_full_width": True, "pulse_on_run": True, "hide": i > 1},
                )
            )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

        # Set initial parameter visibility based on default model
        self._initialize_parameter_visibility()

    def _get_api_model_id(self) -> str:
        """Map friendly model name to API model ID."""
        friendly_name = self.get_parameter_value("model_id") or "Veo 3.1"
        return MODEL_MAPPING.get(friendly_name, friendly_name)

    def _initialize_parameter_visibility(self) -> None:
        """Initialize parameter visibility based on default model selection."""
        self._update_parameter_visibility_for_model()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        if parameter.name == "model_id":
            self._update_parameter_visibility_for_model()
        elif parameter.name == "resolution" and value == "1080p":
            # 1080p only supports 8 second duration
            current_duration = self.get_parameter_value("duration_seconds")
            if current_duration != "8":
                logger.warning("%s: 1080p resolution only supports 8 second duration", self.name)
        elif parameter.name == "reference_images":
            self._handle_reference_images_change(value)

        return super().after_value_set(parameter, value)

    def _update_parameter_visibility_for_model(self) -> None:
        """Update parameter visibility based on selected model."""
        # Map friendly name to API model ID for comparison
        api_model_id = self._get_api_model_id()

        # last_frame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if api_model_id in ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"]:
            self.show_parameter_by_name("last_frame")
        else:
            self.hide_parameter_by_name("last_frame")

        # reference_images and reference_type are only supported by veo-3.1-generate-preview
        if api_model_id == "veo-3.1-generate-preview":
            self.show_parameter_by_name("reference_images")
            self.show_parameter_by_name("reference_type")
        else:
            self.hide_parameter_by_name("reference_images")
            self.hide_parameter_by_name("reference_type")

    def _handle_reference_images_change(self, reference_images: Any) -> None:
        """Handle reference images changes - enforce duration=8 when reference images are provided."""
        has_reference_images = False
        if isinstance(reference_images, list):
            has_reference_images = len(reference_images) > 0
        elif reference_images is not None:
            has_reference_images = True

        if has_reference_images:
            # When reference images are provided, duration must be 8 seconds
            current_duration = self.get_parameter_value("duration_seconds")
            if current_duration != "8":
                logger.warning(
                    "%s: Setting duration to 8 seconds (required when reference images are provided)", self.name
                )
                self.set_parameter_value("duration_seconds", "8")

    def _show_video_output_parameters(self, count: int) -> None:
        """Show/hide video output parameters based on how many videos were generated.

        Args:
            count: Number of videos generated (1-4)
        """
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            if i <= count:
                self.show_parameter_by_name(param_name)
            else:
                self.hide_parameter_by_name(param_name)

    def _log(self, message: str) -> None:
        with suppress(Exception):
            logger.info(message)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate model-specific parameters."""
        exceptions = []
        model_id = self.get_parameter_value("model_id") or "Veo 3.1"
        api_model_id = self._get_api_model_id()

        # lastFrame is only supported by veo-3.1-generate-preview and veo-3.1-fast-generate-preview
        if self.get_parameter_value("last_frame") and api_model_id not in [
            "veo-3.1-generate-preview",
            "veo-3.1-fast-generate-preview",
        ]:
            msg = f"{self.name}: lastFrame parameter is only supported by Veo 3.1 and Veo 3.1 Fast models. Current model: {model_id}"
            exceptions.append(ValueError(msg))

        # referenceImages are only supported by veo-3.1-generate-preview
        reference_images = self.get_parameter_value("reference_images") or []
        has_reference_images = reference_images and len(reference_images) > 0
        if has_reference_images:
            if api_model_id != "veo-3.1-generate-preview":
                msg = f"{self.name}: referenceImages parameter is only supported by Veo 3.1 model. Current model: {model_id}"
                exceptions.append(ValueError(msg))

            # When referenceImages are provided, duration must be 8 seconds
            duration = self.get_parameter_value("duration_seconds") or "6"
            if duration != "8":
                msg = f"{self.name}: When referenceImages are provided, duration must be 8 seconds. Current duration: {duration}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    async def _build_payload(self) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
        """Build the request payload for Veo3 generation."""
        # Preprocess seed parameter
        self._seed_parameter.preprocess()

        # Build instances object with prompt
        instance: dict[str, Any] = {"prompt": self.get_parameter_value("prompt") or ""}

        # Add images to instance object (not parameters)
        start_frame = self.get_parameter_value("start_frame")
        if start_frame:
            image_dict = self._convert_image_to_base64_dict(start_frame)
            if image_dict:
                instance["image"] = image_dict

        last_frame = self.get_parameter_value("last_frame")
        if last_frame:
            last_frame_dict = self._convert_image_to_base64_dict(last_frame)
            if last_frame_dict:
                instance["lastFrame"] = last_frame_dict

        # Add reference images to instance object (max 3 for asset, max 1 for style)
        ref_images_input = self.get_parameter_value("reference_images") or []
        reference_type = self.get_parameter_value("reference_type") or "asset"
        if ref_images_input:
            # Ensure it's a list
            if not isinstance(ref_images_input, list):
                ref_images_input = [ref_images_input]

            # Limit based on reference type
            max_refs = 1 if reference_type == "style" else 3
            reference_images = []
            for ref_image in ref_images_input[:max_refs]:
                if ref_image:
                    ref_image_dict = self._convert_image_to_base64_dict(ref_image)
                    if ref_image_dict:
                        reference_images.append({"image": ref_image_dict, "referenceType": reference_type})

            if reference_images:
                instance["referenceImages"] = reference_images

        # Build parameters object (for non-image parameters)
        parameters: dict[str, Any] = {}

        # Add negative prompt if provided
        negative_prompt = self.get_parameter_value("negative_prompt") or ""
        if negative_prompt:
            parameters["negativePrompt"] = negative_prompt

        # Add aspect ratio
        aspect_ratio = self.get_parameter_value("aspect_ratio")
        if aspect_ratio:
            parameters["aspectRatio"] = aspect_ratio

        # Add resolution
        resolution = self.get_parameter_value("resolution")
        if resolution:
            parameters["resolution"] = resolution

        # Add duration (convert to integer)
        duration_seconds = self.get_parameter_value("duration_seconds")
        if duration_seconds:
            parameters["durationSeconds"] = int(duration_seconds)

        # Add person generation
        person_generation = self.get_parameter_value("person_generation")
        if person_generation:
            parameters["personGeneration"] = person_generation

        # Add seed
        seed = self._seed_parameter.get_seed()
        if seed is not None:
            parameters["seed"] = int(seed)

        # Add generateAudio if provided
        generate_audio = self.get_parameter_value("generate_audio")
        if generate_audio is not None:
            parameters["generateAudio"] = bool(generate_audio)

        # Add sampleCount if provided
        sample_count = self.get_parameter_value("sample_count")
        if sample_count is not None and sample_count > 0:
            parameters["sampleCount"] = int(sample_count)

        return {"instances": [instance], "parameters": parameters}

    def _convert_image_to_base64_dict(self, image_input: Any) -> dict[str, str] | None:
        """Convert image input to base64 format required by Google's API.

        Returns dict with bytesBase64Encoded and mimeType fields, or None if conversion fails.
        """
        if not image_input:
            return None

        # Handle string inputs
        if isinstance(image_input, str):
            return self._convert_string_to_base64_dict(image_input)

        # Handle artifact objects
        return self._convert_artifact_to_base64_dict(image_input)

    def _convert_string_to_base64_dict(self, image_str: str) -> dict[str, str] | None:
        """Convert string image input to base64 dict."""
        image_str = image_str.strip()
        if not image_str:
            return None

        # Handle data URI format
        if image_str.startswith("data:image/"):
            return self._parse_data_uri(image_str)

        # Handle URL - download and convert
        if image_str.startswith(("http://", "https://")):
            return self._download_url_to_base64_dict(image_str)

        # Assume raw base64 string
        return {"bytesBase64Encoded": image_str, "mimeType": "image/png"}

    def _convert_artifact_to_base64_dict(self, artifact: Any) -> dict[str, str] | None:  # noqa: C901
        """Convert artifact object to base64 dict."""
        base64_data = None
        mime_type = "image/png"

        try:
            # Try ImageUrlArtifact (.value attribute)
            if hasattr(artifact, "value"):
                url_value = getattr(artifact, "value", None)
                if isinstance(url_value, str):
                    result = self._convert_string_to_base64_dict(url_value)
                    if result:
                        return result

            # Try ImageArtifact (.base64 attribute)
            if hasattr(artifact, "base64"):
                b64_value = getattr(artifact, "base64", None)
                if isinstance(b64_value, str) and b64_value:
                    if b64_value.startswith("data:image/"):
                        result = self._parse_data_uri(b64_value)
                        if result:
                            base64_data = result["bytesBase64Encoded"]
                            mime_type = result["mimeType"]
                    else:
                        base64_data = b64_value

            # Try mime_type attribute if available
            if hasattr(artifact, "mime_type"):
                artifact_mime = getattr(artifact, "mime_type", None)
                if isinstance(artifact_mime, str) and artifact_mime.startswith("image/"):
                    mime_type = artifact_mime
        except Exception as e:
            self._log(f"Warning: failed to extract base64 from artifact: {e}")
            return None

        if not base64_data:
            return None

        return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    def _parse_data_uri(self, data_uri: str) -> dict[str, str] | None:
        """Parse data URI and extract base64 data and MIME type."""
        parts = data_uri.split(",", 1)
        if len(parts) != 2:  # noqa: PLR2004
            return None

        header = parts[0]
        base64_data = parts[1]
        mime_type = "image/png"

        if ";" in header:
            mime_part = header.split(";")[0].replace("data:", "")
            if mime_part.startswith("image/"):
                mime_type = mime_part

        return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    def _download_url_to_base64_dict(self, url: str) -> dict[str, str] | None:
        """Download image from URL and convert to base64 dict."""
        import httpx

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(url)
                resp.raise_for_status()

            content_type = (resp.headers.get("content-type") or "image/png").split(";")[0]
            mime_type = content_type if content_type.startswith("image/") else "image/png"
            base64_data = base64.b64encode(resp.content).decode("utf-8")
        except Exception as e:
            self._log(f"Warning: failed to download image from URL: {e}")
            return None
        else:
            return {"bytesBase64Encoded": base64_data, "mimeType": mime_type}

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the Veo3 result and set output parameters."""
        # Check for RAI rejection
        rai_filtered_count = result_json.get("response", {}).get("raiMediaFilteredCount", 0)
        if rai_filtered_count > 0:
            logger.warning("%s: %s video(s) filtered by RAI", self.name, rai_filtered_count)

        # Extract videos array from response
        videos_array = result_json.get("response", {}).get("videos", [])
        if not videos_array:
            logger.warning("%s: No videos in result", self.name)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no videos received",
            )
            return

        # Process all videos
        video_artifacts = self._process_videos_from_result(videos_array, generation_id)

        # Check if we got any videos
        if not video_artifacts:
            logger.warning("%s: No videos could be processed", self.name)
            self._set_safe_defaults()
            self._set_status_results(
                was_successful=False,
                result_details="Failed to process any videos from result",
            )
            return

        # Set output parameters
        self._set_video_output_parameters(video_artifacts)

    def _process_videos_from_result(
        self,
        videos_array: list[dict[str, Any]],
        generation_id: str,
    ) -> list[VideoUrlArtifact]:
        """Process all videos from the result array.

        Returns a list of VideoUrlArtifact objects.
        """
        video_artifacts = []
        static_files_manager = GriptapeNodes.StaticFilesManager()

        for idx, video_data in enumerate(videos_array, start=1):
            artifact = self._process_single_video(video_data, generation_id, idx, static_files_manager)
            if artifact:
                video_artifacts.append(artifact)

        return video_artifacts

    def _process_single_video(
        self,
        video_data: dict[str, Any],
        generation_id: str,
        idx: int,
        static_files_manager: Any,
    ) -> VideoUrlArtifact | None:
        """Process a single video from base64 data.

        Returns a VideoUrlArtifact or None if processing failed.
        """
        try:
            base64_data = video_data.get("bytesBase64Encoded")
            mime_type = video_data.get("mimeType", "video/mp4")

            if not base64_data:
                logger.warning("%s: Video %s missing base64 data", self.name, idx)
                return None

            # Decode base64
            video_bytes = base64.b64decode(base64_data)

            # Determine file extension from mime type
            extension = "mp4"
            if "/" in mime_type:
                extension = mime_type.split("/")[1]

            # Save to static storage
            filename = f"veo3_video_{generation_id}_{idx}.{extension}"
            saved_url = static_files_manager.save_static_file(video_bytes, filename)

            logger.info("%s: Saved video %s as %s (%s bytes)", self.name, idx, filename, len(video_bytes))

            return VideoUrlArtifact(value=saved_url, name=filename)

        except Exception as e:
            logger.error("%s: Failed to process video %s: %s", self.name, idx, e)
            return None

    def _set_video_output_parameters(self, video_artifacts: list[VideoUrlArtifact]) -> None:
        """Set output parameters for all generated videos."""
        # Show appropriate number of output parameters
        self._show_video_output_parameters(len(video_artifacts))

        # Set individual output parameters
        for idx, artifact in enumerate(video_artifacts, start=1):
            param_name = "video_url" if idx == 1 else f"video_url_{idx}"
            self.parameter_output_values[param_name] = artifact

        # Set success status
        video_count = len(video_artifacts)
        result_message = f"Generated {video_count} video{'s' if video_count > 1 else ''} successfully"
        self._set_status_results(
            was_successful=True,
            result_details=result_message,
        )

    def _set_safe_defaults(self) -> None:
        """Set safe default values for all outputs on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        # Clear all video output parameters
        for i in range(1, 5):
            param_name = "video_url" if i == 1 else f"video_url_{i}"
            self.parameter_output_values[param_name] = None

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from Veo3 failed generation response.

        Args:
            response_json: The JSON response from the generation status endpoint

        Returns:
            str: A formatted error message to display to the user
        """
        # Try top-level details field (Veo3-specific)
        details = response_json.get("details")
        if details:
            return f"{self.name} {details}"

        # Fall back to standard error extraction
        return super()._extract_error_message(response_json)
