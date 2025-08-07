import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, Trait
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact


@dataclass(eq=False)
class PathValidator(Trait):
    """Validator trait for image paths (file paths or URLs)."""

    supported_extensions: set[str] = field(default_factory=set)
    element_id: str = field(default_factory=lambda: "PathValidatorTrait")

    def __init__(self, supported_extensions: set[str]) -> None:
        super().__init__()
        self.supported_extensions = supported_extensions

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["path_validator"]

    def ui_options_for_trait(self) -> dict:
        return {}

    def display_options_for_trait(self) -> dict:
        return {}

    def converters_for_trait(self) -> list:
        return []

    def validators_for_trait(self) -> list:
        def validate_path(param: Parameter, value: Any) -> None:  # noqa: ARG001
            if not value or not str(value).strip():
                return  # Empty values are allowed

            path_str = LoadImage._strip_surrounding_quotes(str(value).strip())

            # Check if it's a URL
            if path_str.startswith(("http://", "https://")):
                self._validate_url(path_str)
            else:
                self._validate_file_path(path_str)

        return [validate_path]

    def _validate_url(self, url: str) -> None:
        """Validate that the URL is accessible and points to an image."""
        try:
            response = httpx.head(url, timeout=10, follow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                error_msg = f"URL does not point to an image (content-type: {content_type})"
                raise ValueError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"Failed to access URL: {e}"
            raise ValueError(error_msg) from e
        except httpx.HTTPStatusError as e:
            error_msg = f"URL returned error status {e.response.status_code}"
            raise ValueError(error_msg) from e

    def _validate_file_path(self, file_path: str) -> None:
        """Validate that the file path exists and has a supported extension."""
        path = Path(file_path)

        if not path.exists():
            error_msg = f"Image file not found: {file_path}"
            raise FileNotFoundError(error_msg)

        if not path.is_file():
            error_msg = f"Path is not a file: {file_path}"
            raise ValueError(error_msg)

        if path.suffix.lower() not in self.supported_extensions:
            supported = ", ".join(self.supported_extensions)
            error_msg = f"Unsupported image format: {path.suffix}. Supported formats: {supported}"
            raise ValueError(error_msg)


class LoadImage(DataNode):
    # Supported image file extensions
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

    # Regex pattern for safe filename characters (alphanumeric, dots, hyphens, underscores)
    SAFE_FILENAME_PATTERN: ClassVar[str] = r"[^a-zA-Z0-9._-]"

    @staticmethod
    def _strip_surrounding_quotes(path_str: str) -> str:
        """Strip surrounding quotes only if they match (from 'Copy as Pathname')."""
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            return path_str[1:-1]
        return path_str

    @staticmethod
    def _extract_url_from_image_value(image_value: Any) -> str | None:
        """Extract URL from image parameter value and strip query parameters."""
        if not image_value:
            return None

        match image_value:
            # Handle dictionary format (most common)
            case dict():
                url = image_value.get("value")
            # Handle ImageUrlArtifact objects
            case ImageUrlArtifact():
                url = image_value.value
            # Handle raw strings
            case str():
                url = image_value
            case _:
                error_msg = f"Unsupported image value type: {type(image_value)}"
                raise ValueError(error_msg)

        if not url:
            return None

        # Strip query parameters (like ?t=123456 cache busters)
        if "?" in url:
            url = url.split("?")[0]

        return url

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Tracks which parameter is currently driving updates to prevent infinite loops
        # when file_path changes trigger image updates and vice versa
        self._updating_from_parameter = None

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"
        self.image_parameter = Parameter(
            name="image",
            input_types=["ImageArtifact", "ImageUrlArtifact"],
            type="ImageArtifact",
            output_type="ImageUrlArtifact",
            default_value=None,
            ui_options={"clickable_file_browser": True, "expander": True, "edit_mask": True},
            tooltip="The loaded image.",
        )
        self.add_parameter(self.image_parameter)

        self.path_parameter = Parameter(
            name="path",
            input_types=["str"],
            type="str",
            default_value="",
            tooltip="Path to a local image file or URL to an image",
            ui_options={"display_name": "File Path or URL"},
        )

        self.path_parameter.add_trait(
            FileSystemPicker(
                allow_directories=False,
                allow_files=True,
                file_types=list(self.SUPPORTED_EXTENSIONS),
            )
        )

        self.path_parameter.add_trait(PathValidator(supported_extensions=self.SUPPORTED_EXTENSIONS))

        self.add_parameter(self.path_parameter)

    def _to_image_artifact(self, image: Any) -> Any:
        if isinstance(image, dict):
            # Preserve any existing metadata
            metadata = image.get("meta", {})
            artifact = dict_to_image_url_artifact(image)
            if metadata:
                artifact.meta = metadata
            return artifact
        return image

    def _upload_file_to_static_storage(self, file_path: str) -> str:
        """Upload file to static storage and return download URL."""
        path = Path(file_path)
        file_name = path.name

        # Create upload URL
        upload_request = CreateStaticFileUploadUrlRequest(file_name=file_name)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL: {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Unexpected upload URL result type: {type(upload_result)}"
            raise TypeError(error_msg)

        # Read and upload file
        try:
            file_data = path.read_bytes()
        except Exception as e:
            error_msg = f"Failed to read file {file_path}: {e}"
            raise ValueError(error_msg) from e

        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=file_data,
                headers=upload_result.headers,
            )
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload file: {e}"
            raise ValueError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=file_name)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL: {download_result.error}"
            raise TypeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Unexpected download URL result type: {type(download_result)}"
            raise TypeError(error_msg)

        return download_result.url

    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL."""
        return path.startswith(("http://", "https://"))

    def _generate_filename_from_url(self, url: str) -> str:
        """Generate a reasonable filename from a URL."""
        try:
            parsed = urlparse(url)

            # Try to get filename from path
            if parsed.path:
                path_parts = parsed.path.split("/")
                filename = path_parts[-1] if path_parts else ""

                # Clean up the filename - keep only safe characters
                if filename:
                    # Remove query parameters and fragments
                    filename = filename.split("?")[0].split("#")[0]
                    # Keep only alphanumeric, dots, hyphens, underscores
                    filename = re.sub(self.SAFE_FILENAME_PATTERN, "_", filename)
                    # Ensure it has an extension
                    if "." in filename:
                        return filename
        except Exception:
            # Fallback to pure UUID
            return f"url_image_{uuid.uuid4()}.png"

        # If no good filename, create one from domain + uuid
        domain = parsed.netloc.replace("www.", "")
        domain = re.sub(self.SAFE_FILENAME_PATTERN, "_", domain)
        unique_id = str(uuid.uuid4())[:8]
        return f"{domain}_{unique_id}.png"

    def _download_and_upload_url(self, url: str) -> str:
        """Download image from URL and upload to static storage, return download URL."""
        try:
            response = httpx.get(url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to download image from URL {url}: {e}"
            raise ValueError(error_msg) from e

        # Validate content type
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            error_msg = f"URL does not point to an image (content-type: {content_type})"
            raise ValueError(error_msg)

        # Generate filename from URL
        filename = self._generate_filename_from_url(url)

        # Validate file extension
        extension = f".{filename.split('.')[-1].lower()}"
        if extension not in self.SUPPORTED_EXTENSIONS:
            filename = f"{filename.rsplit('.', 1)[0]}.png"

        # Upload to static storage
        upload_request = CreateStaticFileUploadUrlRequest(file_name=filename)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL: {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Unexpected upload URL result type: {type(upload_result)}"
            raise TypeError(error_msg)

        # Upload the downloaded image data
        try:
            upload_response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=response.content,
                headers=upload_result.headers,
            )
            upload_response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload downloaded image: {e}"
            raise ValueError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=filename)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL: {download_result.error}"
            raise TypeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Unexpected download URL result type: {type(download_result)}"
            raise TypeError(error_msg)

        return download_result.url

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        # Skip if we're already in an update cycle to prevent infinite loops
        if self._updating_from_parameter is not None:
            return super().after_value_set(parameter, value)

        match parameter:
            case self.image_parameter:
                image_artifact = self._to_image_artifact(value)
                self.parameter_output_values[self.image_parameter.name] = image_artifact

                # Update path parameter with URL from image (bidirectional sync)
                extracted_url = self._extract_url_from_image_value(value)
                if extracted_url:
                    self._updating_from_parameter = parameter
                    try:
                        self.publish_update_to_parameter(self.path_parameter.name, extracted_url)
                    finally:
                        # Clear the update lock to allow future parameter updates
                        self._updating_from_parameter = None
            case self.path_parameter:
                path_value = self._strip_surrounding_quotes(str(value).strip()) if value else ""

                # Indicate that we're the controlling parameter so we don't trigger an infinite cascade of set value changes.
                self._updating_from_parameter = parameter
                try:
                    if path_value:
                        # Validation has already passed by the time we get here
                        if self._is_url(path_value):
                            download_url = self._download_and_upload_url(path_value)
                        else:
                            download_url = self._upload_file_to_static_storage(path_value)

                        # Test that artifact creation works before updating the image parameter
                        image_artifact = self._to_image_artifact({"value": download_url, "type": "ImageUrlArtifact"})
                        # Only update image parameter if artifact creation succeeded
                        self.publish_update_to_parameter(
                            self.image_parameter.name, {"value": download_url, "type": "ImageUrlArtifact"}
                        )
                    else:
                        # Empty path - reset the image parameter to None
                        self.publish_update_to_parameter(self.image_parameter.name, None)
                except Exception as e:
                    # Re-raise the exception to show error to user
                    error_msg = f"Failed to process path: {e}"
                    raise ValueError(error_msg) from e
                finally:
                    # Clear the update lock to allow future parameter updates
                    self._updating_from_parameter = None
            case _:
                # Handle any other parameters - just do default processing
                pass
        return super().after_value_set(parameter, value)

    def process(self) -> None:
        image = self.get_parameter_value("image")
        image_artifact = self._to_image_artifact(image)
        self.parameter_output_values["image"] = image_artifact
