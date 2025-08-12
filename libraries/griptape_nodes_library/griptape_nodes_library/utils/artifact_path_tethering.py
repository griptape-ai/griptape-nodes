import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from griptape_nodes.exe_types.core_types import Parameter, Trait
from griptape_nodes.exe_types.node_types import BaseNode
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


def default_extract_url_from_artifact_value(
    artifact_value: Any, artifact_classes: type | tuple[type, ...]
) -> str | None:
    """Default implementation to extract URL from any artifact parameter value.

    This function provides the standard pattern for extracting URLs from artifact values
    that can be in dict, artifact object, or string format. Users can override this
    behavior by providing their own extract_url_func in ArtifactTetheringConfig.

    Args:
        artifact_value: The artifact value (dict, artifact object, or string)
        artifact_classes: The artifact class(es) to check for (e.g., ImageUrlArtifact, VideoUrlArtifact)

    Returns:
        The extracted URL or None if no value is present

    Raises:
        ValueError: If the artifact value type is not supported
    """
    if not artifact_value:
        return None

    match artifact_value:
        # Handle dictionary format (most common)
        case dict():
            url = artifact_value.get("value")
        # Handle artifact objects - use isinstance for type safety
        case _ if isinstance(artifact_value, artifact_classes):
            url = artifact_value.value
        # Handle raw strings
        case str():
            url = artifact_value
        case _:
            # Generate error message with expected class names
            if isinstance(artifact_classes, tuple):
                class_names = [cls.__name__ for cls in artifact_classes]
            else:
                class_names = [artifact_classes.__name__]

            expected_types = f"dict, {', '.join(class_names)}, or str"
            error_msg = f"Unsupported artifact value type: {type(artifact_value).__name__}. Expected: {expected_types}"
            raise ValueError(error_msg)

    if not url:
        return None

    return url


@dataclass(eq=False)
class ArtifactPathValidator(Trait):
    """Generic validator trait for artifact paths (file paths or URLs).

    This trait validates user input before parameter values are set, ensuring
    that file paths exist and have supported extensions, and URLs are accessible
    and point to valid content of the expected type.

    Usage example:
        parameter.add_trait(ArtifactPathValidator(
            supported_extensions={".mp4", ".avi"},
            url_content_type_prefix="video/"
        ))

    Validation rules:
    - File paths: Must exist, be readable files, and have supported extensions
    - URLs: Must be accessible via HTTP/HTTPS and return expected content-type
    - Empty values: Always allowed (validation skipped)

    Args:
        supported_extensions: Set of allowed file extensions (e.g., {".mp4", ".avi"})
        url_content_type_prefix: Expected content-type prefix for URLs (e.g., "video/", "audio/")
    """

    supported_extensions: set[str] = field(default_factory=set)
    url_content_type_prefix: str = ""
    element_id: str = field(default_factory=lambda: "ArtifactPathValidatorTrait")

    def __init__(self, supported_extensions: set[str], url_content_type_prefix: str) -> None:
        super().__init__()
        self.supported_extensions = supported_extensions
        self.url_content_type_prefix = url_content_type_prefix

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["artifact_path_validator"]

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

            path_str = ArtifactPathTethering._strip_surrounding_quotes(str(value).strip())

            # Check if it's a URL
            if path_str.startswith(("http://", "https://")):
                self._validate_url(path_str)
            else:
                self._validate_file_path(path_str)

        return [validate_path]

    def _validate_url(self, url: str) -> None:
        """Validate that the URL is accessible and points to expected artifact type.

        Uses HEAD request for efficiency while still validating content-type.
        The actual download will use GET later, but content-type is unlikely to change.
        """
        try:
            response = httpx.head(url, timeout=ArtifactPathTethering.URL_VALIDATION_TIMEOUT, follow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if not content_type.startswith(self.url_content_type_prefix):
                error_msg = f"URL does not point to expected artifact type (content-type: {content_type})"
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
            error_msg = f"File not found: {file_path}"
            raise FileNotFoundError(error_msg)

        if not path.is_file():
            error_msg = f"Path is not a file: {file_path}"
            raise ValueError(error_msg)

        if path.suffix.lower() not in self.supported_extensions:
            supported = ", ".join(self.supported_extensions)
            error_msg = f"Unsupported file format: {path.suffix}. Supported formats: {supported}"
            raise ValueError(error_msg)


@dataclass
class ArtifactTetheringConfig:
    """Configuration for artifact-path tethering behavior."""

    # Conversion functions (required)
    dict_to_artifact_func: Callable  # dict_to_video_url_artifact
    extract_url_func: Callable  # _extract_url_from_video_value

    # File processing (required)
    supported_extensions: set[str]  # {".mp4", ".avi", ".mov"}
    default_extension: str  # "mp4"
    url_content_type_prefix: str  # "video/" (for URL validation)


class ArtifactPathTethering:
    """Helper object for managing bidirectional artifact-path tethering between existing parameters.

    This class provides reusable tethering logic that synchronizes an artifact parameter
    (like image, video, audio) with a path parameter. When one is updated, the other
    automatically updates to reflect the change.

    Usage:
        1. Node creates and owns both artifact and path parameters
        2. Node creates ArtifactPathTethering helper with those parameters and config
        3. Node calls helper.on_after_value_set() in after_value_set()
        4. Node calls helper.get_artifact_output() and get_path_output() in process()
    """

    # Timeout constants - shared across all artifact types
    URL_VALIDATION_TIMEOUT: ClassVar[int] = 10  # seconds
    URL_DOWNLOAD_TIMEOUT: ClassVar[int] = 90  # seconds

    # Regex pattern for safe filename characters (alphanumeric, dots, hyphens, underscores)
    SAFE_FILENAME_PATTERN: ClassVar[str] = r"[^a-zA-Z0-9._-]"

    def __init__(
        self, node: BaseNode, artifact_parameter: Parameter, path_parameter: Parameter, config: ArtifactTetheringConfig
    ):
        """Initialize the tethering helper.

        Args:
            node: The node that owns the parameters
            artifact_parameter: The artifact parameter (e.g., image, video, audio)
            path_parameter: The path parameter (file path or URL)
            config: Configuration for this artifact type
        """
        self.node = node
        self.artifact_parameter = artifact_parameter
        self.path_parameter = path_parameter
        self.config = config

        # Tracks which parameter is currently driving updates to prevent infinite loops
        # when path changes trigger artifact updates and vice versa
        # This lock is critical: artifact change -> path update -> artifact change -> ...
        self._updating_from_parameter = None

    def on_after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes - call from node's after_value_set().

        Args:
            parameter: The parameter that changed
            value: The new value
        """
        # Check the lock first: Skip if we're already in an update cycle to prevent infinite loops
        # This happens when we programmatically update a parameter, which would trigger this method again
        if self._updating_from_parameter is not None:
            return

        # Only handle our parameters
        if parameter not in (self.artifact_parameter, self.path_parameter):
            return

        # Acquire the lock: Set which parameter is driving the current update cycle
        # This prevents the other parameter's update from triggering another cycle
        self._updating_from_parameter = parameter
        try:
            if parameter == self.artifact_parameter:
                self._handle_artifact_change(value)
            elif parameter == self.path_parameter:
                self._handle_path_change(value)
        except Exception as e:
            param_type = "artifact" if parameter == self.artifact_parameter else "path"
            error_msg = f"Failed to process {param_type}: {e}"
            raise ValueError(error_msg) from e
        finally:
            # Always clear the update lock - critical for allowing future updates
            # Even if an exception occurred, we must release the lock or tethering will be permanently broken
            self._updating_from_parameter = None

    def get_artifact_output(self) -> Any:
        """Get the processed artifact for node output."""
        artifact_value = self.node.get_parameter_value(self.artifact_parameter.name)
        if artifact_value is not None:
            return self._to_artifact(artifact_value)
        return None

    def get_path_output(self) -> str:
        """Get the path value for node output."""
        return self.node.get_parameter_value(self.path_parameter.name) or ""

    def _handle_artifact_change(self, value: Any) -> None:
        """Handle changes to the artifact parameter."""
        artifact = self._to_artifact(value)
        self.node.parameter_output_values[self.artifact_parameter.name] = artifact

        # Update path parameter with URL from artifact (bidirectional sync)
        extracted_url = self.config.extract_url_func(value)
        if extracted_url:
            self._sync_parameter_value(self.path_parameter.name, extracted_url)

    def _handle_path_change(self, value: Any) -> None:
        """Handle changes to the path parameter."""
        path_value = self._strip_surrounding_quotes(str(value).strip()) if value else ""

        if path_value:
            # Process the path (URL or file)
            if self._is_url(path_value):
                download_url = self._download_and_upload_url(path_value)
            else:
                download_url = self._upload_file_to_static_storage(path_value)

            artifact_dict = {"value": download_url, "type": f"{self.artifact_parameter.output_type}"}
            self._sync_parameter_value(self.artifact_parameter.name, artifact_dict)
        else:
            # Empty path - reset the artifact parameter
            self._sync_parameter_value(self.artifact_parameter.name, None)

    def _sync_parameter_value(self, target_param_name: str, target_value: Any) -> None:
        """Helper to sync parameter values bidirectionally without triggering infinite loops."""
        # Use initial_setup=True to avoid triggering after_value_set() again, preventing infinite recursion
        # This is the key to avoiding the lock: we bypass the normal parameter change notification
        # that would call after_value_set() and potentially create an infinite loop
        self.node.set_parameter_value(target_param_name, target_value, initial_setup=True)
        self.node.publish_update_to_parameter(target_param_name, target_value)

    def _to_artifact(self, value: Any) -> Any:
        """Convert value to appropriate artifact type."""
        if isinstance(value, dict):
            # Preserve any existing metadata
            metadata = value.get("meta", {})
            # Use config's conversion function
            artifact = self.config.dict_to_artifact_func(value)
            if metadata:
                artifact.meta = metadata
            return artifact
        return value

    @staticmethod
    def _strip_surrounding_quotes(path_str: str) -> str:
        """Strip surrounding quotes only if they match (from 'Copy as Pathname')."""
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            return path_str[1:-1]
        return path_str

    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL."""
        return path.startswith(("http://", "https://"))

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
            return f"url_artifact_{uuid.uuid4()}.{self.config.default_extension}"

        # If no good filename, create one from domain + uuid
        domain = parsed.netloc.replace("www.", "")
        domain = re.sub(self.SAFE_FILENAME_PATTERN, "_", domain)
        unique_id = str(uuid.uuid4())[:8]
        return f"{domain}_{unique_id}.{self.config.default_extension}"

    def _download_and_upload_url(self, url: str) -> str:
        """Download artifact from URL and upload to static storage, return download URL."""
        try:
            response = httpx.get(url, timeout=self.URL_DOWNLOAD_TIMEOUT)
            response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to download artifact from URL {url}: {e}"
            raise ValueError(error_msg) from e

        # Validate content type
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith(self.config.url_content_type_prefix):
            error_msg = f"URL does not point to expected artifact type (content-type: {content_type})"
            raise ValueError(error_msg)

        # Generate filename from URL
        filename = self._generate_filename_from_url(url)

        # Validate and fix file extension
        if "." in filename and filename.count(".") > 0:
            extension = f".{filename.split('.')[-1].lower()}"
            if extension not in self.config.supported_extensions:
                # Replace with default extension if unsupported
                filename = f"{filename.rsplit('.', 1)[0]}.{self.config.default_extension}"
        else:
            # No extension found, add default
            filename = f"{filename}.{self.config.default_extension}"

        # Upload to static storage
        upload_request = CreateStaticFileUploadUrlRequest(file_name=filename)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL: {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Unexpected upload URL result type: {type(upload_result)}"
            raise TypeError(error_msg)

        # Upload the downloaded artifact data
        try:
            upload_response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=response.content,
                headers=upload_result.headers,
            )
            upload_response.raise_for_status()
        except Exception as e:
            error_msg = f"Failed to upload downloaded artifact: {e}"
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

    @staticmethod
    def create_path_parameter(
        name: str,
        config: ArtifactTetheringConfig,
        display_name: str = "File Path or URL",
        tooltip: str | None = None,
    ) -> Parameter:
        """Create a properly configured path parameter with all necessary traits.

        This is a convenience method that creates a path parameter with:
        - FileSystemPicker trait for file browsing
        - ArtifactPathValidator trait for validation

        Args:
            name: Parameter name (e.g., "path", "video_path")
            config: Artifact tethering configuration
            display_name: Display name in UI
            tooltip: Tooltip text (defaults to generic description)

        Returns:
            Fully configured Parameter ready to be added to a node
        """
        if tooltip is None:
            tooltip = f"Path to a local {config.url_content_type_prefix.rstrip('/')} file or URL"

        path_parameter = Parameter(
            name=name,
            input_types=["str"],
            type="str",
            default_value="",
            tooltip=tooltip,
            ui_options={"display_name": display_name},
        )

        # Add file system picker trait
        path_parameter.add_trait(
            FileSystemPicker(
                allow_directories=False,
                allow_files=True,
                file_types=list(config.supported_extensions),
            )
        )

        # Add path validator trait
        path_parameter.add_trait(
            ArtifactPathValidator(
                supported_extensions=config.supported_extensions,
                url_content_type_prefix=config.url_content_type_prefix,
            )
        )

        return path_parameter
