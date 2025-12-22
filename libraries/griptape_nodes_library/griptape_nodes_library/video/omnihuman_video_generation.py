from __future__ import annotations

import io
import json as _json
import logging
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from griptape.artifacts import ImageUrlArtifact, VideoUrlArtifact
from griptape.artifacts.url_artifact import UrlArtifact
from PIL import Image

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.param_components.artifact_url.public_artifact_url_parameter import (
    PublicArtifactUrlParameter,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.base_proxy_node import GriptapeProxyNode
from griptape_nodes_library.utils.image_utils import resize_image_for_resolution, shrink_image_to_size

logger = logging.getLogger("griptape_nodes")

__all__ = ["OmnihumanVideoGeneration"]

# Maximum image size in bytes (5MB)
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
# Maximum image resolution (4096x4096)
MAX_IMAGE_DIMENSION = 4096


class OmnihumanVideoGeneration(GriptapeProxyNode):
    """Generate video effects from a single image, text prompt, and audio file using OmniHuman 1.5.

    This is Step 3 of the OmniHuman workflow. It generates video matching the input image based
    on the provided audio and optional mask. The generation process is asynchronous and will
    poll for completion.

    Inputs:
        - image_url (str): Source image URL
        - audio_url (str): Audio file URL
        - mask_image_urls (list): Optional mask image URLs from subject detection
        - prompt (str): Text prompt to guide generation
        - seed (int): Random seed for generation (-1 for random)
        - fast_mode (bool): Enable fast mode (sacrifices some effects for speed

    Outputs:
        - generation_id (str): Griptape Cloud generation identifier
        - video_url (VideoUrlArtifact): Generated video URL artifact
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the video generation result or any errors
    """

    MODEL_IDS: ClassVar[list[str]] = [
        "omnihuman-1-0",
        "omnihuman-1-5",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate talking head videos using OmniHuman 1.5 via Griptape Cloud"

        # INPUTS
        # add model_id parameter with fixed value
        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="omnihuman-1-5",
                tooltip="Model identifier to use for generation",
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
                default_value="",
                tooltip="Source image URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/image.jpg"},
            ),
            disclaimer_message="The OmniHuman service utilizes this URL to access the image for video generation.",
        )
        self._public_image_url_parameter.add_input_parameters()

        # Image size validation
        self.add_parameter(
            Parameter(
                name="auto_image_resize",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip=f"If disabled, raises an error when input image exceeds the {MAX_IMAGE_SIZE_BYTES / (1024 * 1024):.0f}MB size limit or {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} resolution limit. If enabled, oversized images are automatically resized to fit within these limits.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self._public_audio_url_parameter = PublicArtifactUrlParameter(
            node=self,
            artifact_url_parameter=Parameter(
                name="audio_url",
                input_types=["AudioUrlArtifact"],
                type="AudioUrlArtifact",
                default_value="",
                tooltip="Audio file URL.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "https://example.com/audio.mp3"},
            ),
        )
        self._public_audio_url_parameter.add_input_parameters()

        self.add_parameter(
            Parameter(
                name="mask_image_urls",
                input_types=["list"],
                type="list",
                output_type="list",
                default_value=[],
                tooltip="Optional mask image URLs from subject detection (will auto-detect if enabled and not provided)",
                ui_options={"placeholder_text": "https://example.com/mask1.png"},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="auto_detect_masks",
                input_types=["bool"],
                type="bool",
                default_value=True,
                tooltip="Automatically detect subject masks if none provided (calls subject detection API)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"hide": True},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation identifier",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Generated video URL artifact",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=-1,
                tooltip="Random seed for generation (-1 for random)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "-1 for random"},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="Text prompt to guide generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Text prompt to guide generation"},
            )
        )

        self.add_parameter(
            Parameter(
                name="fast_mode",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="Enable fast mode (sacrifices some effects for speed)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Create status parameters for success/failure tracking
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        # if the model_id parameter is omnihuman-1-0, remove seed, fast_mode, and prompt parameters
        if parameter.name == "model_id" and value == "omnihuman-1-0":
            self.hide_parameter_by_name("seed")
            self.hide_parameter_by_name("fast_mode")
            self.hide_parameter_by_name("prompt")
        else:
            self.show_parameter_by_name("seed")
            self.show_parameter_by_name("fast_mode")
            self.show_parameter_by_name("prompt")

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model_id") or "omnihuman-1-5"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for OmniHuman video generation."""
        # Store downscaled filename for cleanup
        self._downscaled_filename: str | None = None

        # Check if we need to use a downscaled image
        downscaled_image, downscaled_filename = await self._get_image_for_api()
        self._downscaled_filename = downscaled_filename

        # Get parameters
        image_url_param = self.get_parameter_value("image_url")
        audio_url = self.get_parameter_value("audio_url")
        mask_image_urls = self.get_parameter_value("mask_image_urls")
        prompt = self.get_parameter_value("prompt")
        seed = self.get_parameter_value("seed")
        fast_mode = self.get_parameter_value("fast_mode")
        model_id = self._get_api_model_id()

        # Validate required parameters
        if not image_url_param:
            msg = "image_url parameter is required."
            raise ValueError(msg)

        # Use downscaled image if available, otherwise use original
        if downscaled_image is not None:
            # Upload downscaled image to get public URL
            image_url = self._get_public_url_for_artifact(downscaled_image)
        else:
            image_url = self._public_image_url_parameter.get_public_url_for_parameter()

        if not audio_url:
            msg = "audio_url parameter is required."
            raise ValueError(msg)
        audio_url = self._public_audio_url_parameter.get_public_url_for_parameter()

        # Handle artifacts
        if hasattr(mask_image_urls, "value"):
            mask_image_urls = mask_image_urls.value

        # Auto-detect masks if enabled and no mask_image_urls provided
        auto_detect = self.get_parameter_value("auto_detect_masks")
        if auto_detect and (not mask_image_urls or len(mask_image_urls) == 0):
            logger.info("%s: No masks provided, running subject detection to generate masks", self.name)
            api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
            mask_image_urls = await self._auto_detect_masks(image_url, api_key)
            if mask_image_urls:
                logger.info("%s: Auto-detected %d mask(s)", self.name, len(mask_image_urls))

        body = {
            "req_key": self._get_req_key(model_id),
            "image_url": str(image_url).strip(),
            "audio_url": str(audio_url).strip(),
            "mask_url": "; ".join([str(url).strip() for url in mask_image_urls]) if mask_image_urls else None,
            "prompt": prompt if prompt else None,
            "seed": seed if seed else None,
            "fast_mode": fast_mode if fast_mode else None,
        }
        # Remove None values
        return {k: v for k, v in body.items() if v is not None}

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse OmniHuman result and save generated video."""
        # Extract video URL from provider response
        video_url = self._extract_video_url(result_json)

        if not video_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        # Set video URL artifact
        self.parameter_output_values["video_url"] = VideoUrlArtifact(value=video_url)

        # Try to download and save video
        try:
            logger.info("Downloading video bytes from provider URL")
            video_filename = await self._save_video_bytes(video_url, generation_id)
        except Exception as e:
            logger.error("Failed to download video: %s", e)
            video_filename = None

        self._set_status_results(
            was_successful=True,
            result_details=f"Video generation completed successfully. Video URL: {video_url}"
            + (f", saved as: {video_filename}" if video_filename else ""),
        )

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs on error."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["video_url"] = None

    async def aprocess(self) -> None:
        """Process video generation with cleanup."""
        self._downscaled_filename = None
        try:
            await super().aprocess()
        finally:
            # Cleanup uploaded artifacts and downscaled image
            self._public_image_url_parameter.delete_uploaded_artifact()
            self._public_audio_url_parameter.delete_uploaded_artifact()
            if hasattr(self, "_downscaled_filename"):
                self._cleanup_downscaled_image(self._downscaled_filename)

    def _get_static_files_path(self) -> Path:
        """Get the absolute path to the static files directory."""
        static_files_manager = GriptapeNodes.StaticFilesManager()
        static_files_dir = static_files_manager._get_static_files_directory()
        workspace_path = GriptapeNodes.ConfigManager().workspace_path
        return workspace_path / static_files_dir

    def _cleanup_downscaled_image(self, filename: str | None) -> None:
        """Delete the downscaled image file if it exists."""
        if not filename:
            return

        try:
            static_files_manager = GriptapeNodes.StaticFilesManager()
            static_files_dir = static_files_manager._get_static_files_directory()
            file_path = Path(static_files_dir) / filename
            static_files_manager.storage_driver.delete_file(file_path)
            logger.info("%s: Cleaned up downscaled image: %s", self.name, filename)
        except Exception as e:
            logger.warning("%s: Failed to cleanup downscaled image %s: %s", self.name, filename, e)

    async def _get_image_for_api(self) -> tuple[ImageUrlArtifact | None, str | None]:
        """Get the image to use for the API call, shrinking if needed.

        Returns a tuple of (artifact, filename):
        - artifact: The downscaled image artifact if shrinking was needed, or None to use original
        - filename: The filename of the downscaled image for cleanup, or None
        """
        # Get the image file contents
        file_contents = await self._get_image_file_contents()
        if file_contents is None:
            return None, None

        # Check file size
        size_bytes = len(file_contents)
        size_mb = size_bytes / (1024 * 1024)
        max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
        exceeds_size = size_bytes > MAX_IMAGE_SIZE_BYTES

        # Check resolution
        img = Image.open(io.BytesIO(file_contents))
        width, height = img.size
        exceeds_resolution = width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION

        # If neither constraint is exceeded, use original
        if not exceeds_size and not exceeds_resolution:
            return None, None

        # Check if auto resize is enabled
        auto_image_resize = self.get_parameter_value("auto_image_resize")
        if not auto_image_resize:
            issues = []
            if exceeds_size:
                issues.append(f"size {size_mb:.2f}MB exceeds {max_mb:.0f}MB limit")
            if exceeds_resolution:
                issues.append(f"resolution {width}x{height} exceeds {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} limit")
            msg = f"{self.name} input image: {', '.join(issues)}"
            raise ValueError(msg)

        # Log what needs to be fixed
        if exceeds_size and exceeds_resolution:
            logger.info("%s: Input image is %.2fMB and %dx%d, resizing...", self.name, size_mb, width, height)
        elif exceeds_size:
            logger.info("%s: Input image is %.2fMB, shrinking to under %.0fMB...", self.name, size_mb, max_mb)
        else:
            logger.info(
                "%s: Input image is %dx%d, resizing to under %dx%d...",
                self.name,
                width,
                height,
                MAX_IMAGE_DIMENSION,
                MAX_IMAGE_DIMENSION,
            )

        # Resize for resolution if needed, then shrink for size
        resized_bytes = (
            resize_image_for_resolution(file_contents, MAX_IMAGE_DIMENSION, self.name)
            if exceeds_resolution
            else file_contents
        )
        shrunk_bytes = shrink_image_to_size(resized_bytes, MAX_IMAGE_SIZE_BYTES, self.name)

        if len(shrunk_bytes) >= len(file_contents):
            # Shrinking didn't help
            logger.info("%s: Could not shrink image, using original", self.name)
            return None, None

        # Save shrunk image to static files
        shrunk_filename = f"shrunk_{uuid4().hex}.webp"
        shrunk_url = GriptapeNodes.StaticFilesManager().save_static_file(shrunk_bytes, shrunk_filename)

        new_artifact = ImageUrlArtifact(value=shrunk_url)
        logger.info("%s: Resized image to %.2fMB", self.name, len(shrunk_bytes) / (1024 * 1024))
        return new_artifact, shrunk_filename

    async def _get_image_file_contents(self) -> bytes | None:
        """Get the file contents of the input image."""
        parameter_value = self.get_parameter_value("image_url")
        url = parameter_value.value if isinstance(parameter_value, UrlArtifact) else parameter_value

        if not url:
            return None

        # External URLs need to be downloaded
        if self._is_external_url(url):
            return await self._download_image_bytes(url)

        # Read from local static files
        return self._read_local_file(url)

    def _is_external_url(self, url: str) -> bool:
        """Check if a URL is external (not localhost)."""
        return url.startswith(("http://", "https://")) and "localhost" not in url

    def _read_local_file(self, url: str) -> bytes | None:
        """Read file contents from local static files directory."""
        filename = Path(urlparse(url).path).name
        file_path = self._get_static_files_path() / filename

        if not file_path.exists():
            return None

        with file_path.open("rb") as f:
            return f.read()

    async def _download_image_bytes(self, url: str) -> bytes | None:
        """Download image bytes from an external URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=120.0)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.warning("%s: Failed to download image from %s: %s", self.name, url, e)
            return None

    def _get_public_url_for_artifact(self, artifact: ImageUrlArtifact) -> str:
        """Get a public URL for an image artifact by uploading to Griptape Cloud."""
        url = artifact.value

        # If already a public URL, return it
        if self._is_external_url(url):
            return url

        # Read file contents and upload to cloud
        file_contents = self._read_local_file(url)
        if file_contents is None:
            msg = f"Could not read file for artifact: {url}"
            raise ValueError(msg)

        filename = Path(urlparse(url).path).name
        gtc_file_path = Path("staticfiles") / "artifact_url_storage" / uuid4().hex / filename

        return self._public_image_url_parameter._storage_driver.upload_file(
            path=gtc_file_path, file_content=file_contents
        )

    async def _auto_detect_masks(self, image_url: str, api_key: str) -> list[str]:
        """Automatically detect masks by calling the subject detection API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Build payload for subject detection
        provider_params = {
            "req_key": "realman_avatar_object_detection_cv",
            "image_url": image_url,
        }

        post_url = urljoin(self._proxy_base, "models/omnihuman-1-5-subject-detection")
        logger.info("%s: Calling subject detection API for auto-mask generation", self.name)

        try:
            # TODO: https://github.com/griptape-ai/griptape-nodes/issues/3041
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    post_url,
                    json=provider_params,
                    headers=headers,
                    timeout=300.0,
                )

                if response.status_code >= 400:  # noqa: PLR2004
                    logger.error(
                        "%s: Subject detection failed with status %d: %s",
                        self.name,
                        response.status_code,
                        response.text,
                    )
                    return []

                response_json = response.json()
                # Extract mask URLs from response
                resp_data = _json.loads(response_json.get("data", {}).get("resp_data", "{}"))
                mask_urls = resp_data.get("object_detection_result", {}).get("mask", {}).get("url", [])
                return mask_urls if isinstance(mask_urls, list) else []

        except Exception as e:
            logger.error("%s: Auto-detection failed: %s", self.name, e)
            return []

    def _get_req_key(self, model_id: str) -> str:
        """Get the request key based on model_id."""
        if model_id == "omnihuman-1-0":
            return "realman_avatar_picture_omni_cv"
        if model_id == "omnihuman-1-5":
            return "realman_avatar_picture_omni15_cv"
        msg = f"Unsupported model_id: {model_id}"
        raise ValueError(msg)

    @staticmethod
    def _extract_video_url(response_json: dict[str, Any]) -> str | None:
        """Extract video URL from OmniHuman API response."""
        if not isinstance(response_json, dict):
            return None

        # Parse nested resp_data JSON string
        resp_data_str = response_json.get("data", {}).get("resp_data", "{}")
        if not resp_data_str:
            return None

        resp_data = _json.loads(resp_data_str)
        video_url = resp_data.get("video_url")

        if isinstance(video_url, str) and video_url.startswith("http"):
            return video_url

        return None

    async def _save_video_bytes(self, url: str, generation_id: str) -> str | None:
        """Download video bytes from URL and save to static storage."""
        video_bytes = await self._download_bytes_from_url(url)
        if not video_bytes:
            return None

        filename = f"omnihuman_video_{generation_id}.mp4"
        static_files_manager = GriptapeNodes.StaticFilesManager()
        static_files_manager.save_static_file(video_bytes, filename)
        return filename
