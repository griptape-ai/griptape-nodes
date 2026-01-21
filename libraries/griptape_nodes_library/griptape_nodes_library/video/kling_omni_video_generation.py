from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["KlingOmniVideoGeneration"]

# Constants
MAX_PROMPT_LENGTH = 2500
MAX_IMAGES_WITH_VIDEO = 4
MAX_IMAGES_WITHOUT_VIDEO = 7
MAX_IMAGES_FOR_END_FRAME = 2


class KlingOmniVideoGeneration(GriptapeProxyNode):
    """Generate a video using Kling Omni AI via Griptape Cloud model proxy.

    The Omni model supports various capabilities through templated prompts with elements,
    images, and videos. Use <<<element_1>>>, <<<image_1>>>, <<<video_1>>> in prompts.

    Inputs:
        - prompt (str): Text prompt with optional templates (max 2500 chars, required)
        - reference_images (list[ImageArtifact]): Reference images for generation (optional)
        - first_frame_image (ImageArtifact|ImageUrlArtifact|str): First frame image (optional)
        - end_frame_image (ImageArtifact|ImageUrlArtifact|str): End frame image (optional)
        - element_ids (str): Comma-separated element IDs (optional)
        - reference_video (VideoUrlArtifact): Reference video for editing or style reference (optional, max 1)
        - video_refer_type (str): Video reference type (base: edit video, feature: use as feature reference)
        - video_keep_sound (bool): Keep original video sound (default: False)
        - mode (str): Video generation mode (std: Standard, pro: Professional)
        - aspect_ratio (str): Aspect ratio (required when not using first frame or video editing)
        - duration (int): Video length in seconds (3-10s)
        (Always polls for result: 5s interval, 20 min timeout)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (latest polling response)
        - video_url (VideoUrlArtifact): Saved video URL
        - kling_video_id (str): The video ID from Kling AI
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # INPUTS / PROPERTIES
        self.add_parameter(
            ParameterString(
                name="prompt",
                tooltip="Text prompt with optional templates like <<<image_1>>>, <<<element_1>>> (max 2500 chars)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                multiline=True,
                placeholder_text="Describe the video... Use <<<image_1>>> to reference images.",
            )
        )

        # Image Inputs Group
        self.add_parameter(
            Parameter(
                name="first_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="First frame image (optional). Accepts ImageArtifact, ImageUrlArtifact, URL, or Base64.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "first frame"},
            )
        )
        self.add_parameter(
            Parameter(
                name="end_frame_image",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                tooltip="End frame image (optional). Requires first frame to be set.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "end frame"},
            )
        )
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
                tooltip="Reference images for generation. These appear first in the template (<<<image_1>>>, <<<image_2>>>, etc.)",
                allowed_modes={ParameterMode.INPUT},
                ui_options={"expander": True, "display_name": "reference images"},
            )
        )

        # Advanced References Group
        with ParameterGroup(name="Advanced References") as advanced_group:
            ParameterString(
                name="element_ids",
                default_value="",
                tooltip="Comma-separated element IDs (e.g., '123,456,789')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "e.g., 123,456,789", "hide": True},
            )
        advanced_group.ui_options = {"hide": False}
        self.add_node_element(advanced_group)

        # Use PublicArtifactUrlParameter for video upload handling
        self._public_video_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="reference_video",
                input_types=["VideoUrlArtifact"],
                type="VideoUrlArtifact",
                tooltip="Reference video for editing or style reference (optional, max 1)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/video.mp4"},
            ),
            disclaimer_message="The Kling Omni service utilizes this URL to access the video for generation.",
        )
        self._public_video_url_parameter.add_input_parameters()

        # Generation Settings Group
        with ParameterGroup(name="Generation Settings") as gen_settings_group:
            ParameterString(
                name="video_refer_type",
                default_value="base",
                tooltip="Video reference type: 'feature' is the feature reference video, 'base' is the video to be edited",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["base", "feature"])},
            )
            Parameter(
                name="video_keep_sound",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Keep original video sound (only applies when video_refer_type is 'base')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "keep video sound"},
            )
            ParameterString(
                name="mode",
                default_value="pro",
                tooltip="Video generation mode (std: Standard, pro: Professional)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["std", "pro"])},
            )
            ParameterString(
                name="aspect_ratio",
                default_value="16:9",
                tooltip="Aspect ratio (required when not using first frame or video editing)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "9:16", "1:1"])},
            )
            ParameterInt(
                name="duration",
                default_value=5,
                tooltip="Video length in seconds (3-10s). Only 5/10s for text-to-video and first-frame generation.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[3, 4, 5, 6, 7, 8, 9, 10])},
            )
        self.add_node_element(gen_settings_group)

        # OUTPUTS
        self.add_parameter(
            ParameterString(
                name="generation_id",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
                hide=True,
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (latest polling response)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
                hide=True,
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"pulse_on_run": True},
            )
        )

        self.add_parameter(
            ParameterString(
                name="kling_video_id",
                tooltip="The video ID from Kling AI",
                allowed_modes={ParameterMode.OUTPUT},
                placeholder_text="The Kling AI video ID",
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=True,
        )

    async def aprocess(self) -> None:
        try:
            await super().aprocess()
        finally:
            # Always cleanup uploaded video artifact
            self._public_video_url_parameter.delete_uploaded_artifact()

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Returns the static model ID for Kling Omni.
        """
        return "kling-video-o1:omnivideo"

    async def _build_payload(self) -> dict[str, Any]:  # noqa: C901, PLR0912
        """Build the request payload for Kling Omni API.

        Images are ordered: reference images FIRST, then start/end frames at the END.
        This allows users to reference <<<image_1>>>, <<<image_2>>> in the order they
        supplied the reference images.

        Returns:
            dict: The request payload (model field excluded, handled by base class)
        """
        prompt = (self.get_parameter_value("prompt") or "").strip()
        reference_images = self.get_parameter_value("reference_images") or []
        first_frame_image = await self._prepare_image_data_url_async(self.get_parameter_value("first_frame_image"))
        end_frame_image = await self._prepare_image_data_url_async(self.get_parameter_value("end_frame_image"))
        element_ids = (self.get_parameter_value("element_ids") or "").strip()

        # Get video parameters - use PublicArtifactUrlParameter to get public URL
        reference_video_param = self.get_parameter_value("reference_video")
        reference_video_url = None
        if reference_video_param:
            reference_video_url = self._public_video_url_parameter.get_public_url_for_parameter()

        video_keep_sound = self.get_parameter_value("video_keep_sound")
        if video_keep_sound is None:
            video_keep_sound = False

        video_refer_type = self.get_parameter_value("video_refer_type") or "base"
        mode = self.get_parameter_value("mode") or "pro"
        aspect_ratio = self.get_parameter_value("aspect_ratio") or "16:9"
        duration = self.get_parameter_value("duration") or 5

        payload: dict[str, Any] = {
            "model_name": "kling-video-o1",
            "prompt": prompt,
            "mode": mode,
            "aspect_ratio": aspect_ratio,
            "duration": int(duration),
        }

        # Build image_list array: reference images FIRST, then start/end frames at END
        image_list = []

        # Add reference images first (so they are image_1, image_2, etc. in order)
        # Reference images don't have a "type" field
        ref_images_input = reference_images
        if not isinstance(ref_images_input, list):
            ref_images_input = [ref_images_input] if ref_images_input else []

        for ref_image in ref_images_input:
            if ref_image:
                ref_image_url = await self._prepare_image_data_url_async(ref_image)
                if ref_image_url:
                    image_list.append({"image_url": ref_image_url})

        # Add start and end frames at the END with explicit type field
        if first_frame_image:
            image_list.append({"image_url": first_frame_image, "type": "first_frame"})
        if end_frame_image:
            image_list.append({"image_url": end_frame_image, "type": "end_frame"})

        if image_list:
            payload["image_list"] = image_list

        # Parse element IDs from comma-separated string
        if element_ids:
            element_list = []
            try:
                element_ids_parts = [part.strip() for part in element_ids.split(",") if part.strip()]
                element_list = [{"element_id": int(eid)} for eid in element_ids_parts]
            except ValueError:
                pass  # Validation already happened in validate_before_node_run
            if element_list:
                payload["element_list"] = element_list

        # Add video if provided
        if reference_video_url:
            keep_sound_str = "yes" if video_keep_sound else "no"
            payload["video_list"] = [
                {
                    "video_url": reference_video_url,
                    "refer_type": video_refer_type,
                    "keep_original_sound": keep_sound_str,
                }
            ]

        return payload

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the result and set output parameters.

        Expected structure: {"data": {"task_result": {"videos": [{"url": "...", "id": "..."}]}}}
        """
        data = result_json.get("data", {})
        task_result = data.get("task_result", {})
        videos = task_result.get("videos", [])

        if not videos or not isinstance(videos, list) or len(videos) == 0:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no videos found in response.",
            )
            return

        video_info = videos[0]
        download_url = video_info.get("url")
        video_id = video_info.get("id")

        if not download_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details=f"{self.name} generation completed but no download URL found in response.",
            )
            return

        # Set kling_video_id output parameter
        if video_id:
            self.parameter_output_values["kling_video_id"] = video_id
            logger.info("Video ID: %s", video_id)

        # Download and save video
        try:
            logger.info("%s downloading video from provider URL", self.name)
            video_bytes = await self._download_bytes_from_url(download_url)
        except Exception as e:
            logger.warning("%s failed to download video: %s", self.name, e)
            video_bytes = None

        if video_bytes:
            try:
                static_files_manager = GriptapeNodes.StaticFilesManager()
                filename = f"kling_omni_video_{generation_id}.mp4"
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("%s saved video to static storage as %s", self.name, filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except (OSError, PermissionError) as e:
                logger.warning("%s failed to save to static storage: %s, using provider URL", self.name, e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=download_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _set_safe_defaults(self) -> None:
        """Clear output parameters on error."""
        self.parameter_output_values["video_url"] = None
        self.parameter_output_values["kling_video_id"] = ""

    def validate_before_node_run(self) -> list[Exception] | None:  # noqa: C901, PLR0912
        """Validate parameters before execution."""
        exceptions = super().validate_before_node_run() or []

        # Get parameter values
        prompt = (self.get_parameter_value("prompt") or "").strip()
        reference_images = self.get_parameter_value("reference_images") or []
        first_frame_image = self.get_parameter_value("first_frame_image")
        end_frame_image = self.get_parameter_value("end_frame_image")
        element_ids = (self.get_parameter_value("element_ids") or "").strip()
        reference_video_param = self.get_parameter_value("reference_video")
        duration = self.get_parameter_value("duration") or 5

        # Validate prompt is provided
        if not prompt:
            exceptions.append(ValueError(f"{self.name} requires a prompt to generate video."))

        # Validate prompt length
        if len(prompt) > MAX_PROMPT_LENGTH:
            exceptions.append(
                ValueError(
                    f"{self.name} prompt exceeds {MAX_PROMPT_LENGTH} characters (got: {len(prompt)} characters)."
                )
            )

        # Parse element IDs from comma-separated string
        element_list = []
        if element_ids:
            try:
                element_ids_parts = [part.strip() for part in element_ids.split(",") if part.strip()]
                element_list = [{"element_id": int(eid)} for eid in element_ids_parts]
            except ValueError:
                exceptions.append(
                    ValueError(f"{self.name} validation failed: element_ids must be comma-separated integers")
                )

        # Build video list
        has_video = bool(reference_video_param)

        # Get reference images (already a list from ParameterList)
        ref_images_input = reference_images
        if not isinstance(ref_images_input, list):
            ref_images_input = [ref_images_input] if ref_images_input else []

        # Validate end frame requires first frame
        if end_frame_image and not first_frame_image:
            exceptions.append(ValueError(f"{self.name} end_frame_image requires first_frame_image to be set."))

        # Count total images and elements
        total_image_count = len(ref_images_input)
        if first_frame_image:
            total_image_count += 1
        if end_frame_image:
            total_image_count += 1
        total_element_count = len(element_list)

        # Validate image + element count limits
        if has_video:
            if total_image_count + total_element_count > MAX_IMAGES_WITH_VIDEO:
                exceptions.append(
                    ValueError(
                        f"{self.name} when using reference videos, the sum of images ({total_image_count}) "
                        f"and elements ({total_element_count}) cannot exceed {MAX_IMAGES_WITH_VIDEO}."
                    )
                )
        elif total_image_count + total_element_count > MAX_IMAGES_WITHOUT_VIDEO:
            exceptions.append(
                ValueError(
                    f"{self.name} the sum of images ({total_image_count}) "
                    f"and elements ({total_element_count}) cannot exceed {MAX_IMAGES_WITHOUT_VIDEO}."
                )
            )

        # Validate end frame not allowed with >2 images
        if end_frame_image and total_image_count > MAX_IMAGES_FOR_END_FRAME:
            exceptions.append(
                ValueError(
                    f"{self.name} end frame is not supported when there are more than {MAX_IMAGES_FOR_END_FRAME} images."
                )
            )

        # Validate video editing cannot be used with first/end frames
        video_refer_type = self.get_parameter_value("video_refer_type") or "base"
        has_base_video = has_video and video_refer_type == "base"
        if has_base_video and (first_frame_image or end_frame_image):
            exceptions.append(
                ValueError(
                    f"{self.name} video editing (refer_type='base') cannot be used with first or end frame images."
                )
            )

        # Validate duration constraints for text/first-frame generation
        is_text_or_first_frame = not has_base_video
        if is_text_or_first_frame and duration not in [5, 10]:
            exceptions.append(
                ValueError(
                    f"{self.name} text-to-video and first-frame generation only support 5 or 10 second durations (got {duration}s)."
                )
            )

        return exceptions if exceptions else None

    async def _prepare_image_data_url_async(self, image_input: Any) -> str | None:
        """Convert image input to a data URL, handling external URLs by downloading and converting."""
        if not image_input:
            return None

        image_url = self._coerce_image_url_or_data_uri(image_input)
        if not image_url:
            return None

        # If it's already a data URL, return it
        if image_url.startswith("data:image/"):
            return image_url

        # If it's an external URL, download and convert to data URL
        if image_url.startswith(("http://", "https://")):
            return await self._inline_external_url_async(image_url)

        return image_url

    async def _inline_external_url_async(self, url: str) -> str | None:
        """Download external image URL and convert to data URL."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.debug("%s failed to inline image URL: %s", self.name, e)
                return None
            else:
                b64 = base64.b64encode(resp.content).decode("utf-8")
                logger.debug("Image URL converted to data URI for proxy")
                return b64

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        """Convert various image input types to a URL or data URI string."""
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except AttributeError:
            pass

        return None
