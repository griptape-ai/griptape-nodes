import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait
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
from griptape_nodes_library.utils.video_utils import validate_url


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

            path_str = ArtifactPathTethering._sanitize_path_string(str(value).strip())

            # Check if it's a URL
            if path_str.startswith(("http://", "https://")):
                valid = validate_url(path_str)
                if not valid:
                    error_msg = f"Invalid URL: '{path_str}'"
                    raise ValueError(error_msg)
            else:
                self._validate_file_path(path_str)

        return [validate_path]

    def _validate_file_path(self, file_path: str) -> None:
        """Validate that the file path exists and has a supported extension."""
        path = Path(file_path)

        if not path.is_absolute():
            path = GriptapeNodes.ConfigManager().workspace_path / path

        if not path.exists():
            error_msg = f"File not found: '{file_path}'"
            raise FileNotFoundError(error_msg)

        if not path.is_file():
            path_type = "directory" if path.is_dir() else "special file" if path.exists() else "unknown"
            error_msg = f"Path exists but is not a file: '{file_path}' (found: {path_type})"
            raise ValueError(error_msg)

        if path.suffix.lower() not in self.supported_extensions:
            supported = ", ".join(self.supported_extensions)
            error_msg = f"Unsupported file format '{path.suffix}' for file '{file_path}'. Supported: {supported}"
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

    def get_artifact_output(self) -> Any:
        """Get the processed artifact for node output."""
        return self.node.get_parameter_value(self.artifact_parameter.name)

    def get_path_output(self) -> str:
        """Get the path value for node output."""
        result = self.node.get_parameter_value(self.path_parameter.name) or ""
        return result

    def on_incoming_connection(self, target_parameter: Parameter) -> None:
        """Handle incoming connection establishment to the artifact parameter.

        When the artifact parameter receives an incoming connection,
        make both artifact and path parameters read-only to prevent
        manual modifications that could conflict with connected values.

        Note: Path parameter cannot receive connections (PROPERTY+OUTPUT only).

        Args:
            target_parameter: The parameter that received the connection
        """
        if target_parameter == self.artifact_parameter:
            # Make both tethered parameters read-only
            self.artifact_parameter.settable = False
            self.path_parameter.settable = False

    def on_incoming_connection_removed(self, target_parameter: Parameter) -> None:
        """Handle incoming connection removal from the artifact parameter.

        When a connection is removed from the artifact parameter,
        make both parameters settable again.

        Args:
            target_parameter: The parameter that had its connection removed
        """
        if target_parameter == self.artifact_parameter:
            # Make both tethered parameters settable again
            self.artifact_parameter.settable = True
            self.path_parameter.settable = True

    def on_before_value_set(self, parameter: Parameter, value: Any) -> Any:
        """Handle parameter value setting for tethered parameters.

        This allows legitimate upstream values and internal synchronization
        to be set by temporarily making parameters settable when the artifact
        parameter has connections.

        Args:
            parameter: The parameter being set
            value: The value being set

        Returns:
            The value to actually set (unchanged in this case)
        """
        if parameter in (self.artifact_parameter, self.path_parameter):
            # Check if the artifact parameter has incoming connections
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            connections = GriptapeNodes.FlowManager().get_connections()
            target_connections = connections.incoming_index.get(self.node.name)

            has_artifact_connection = target_connections and target_connections.get(self.artifact_parameter.name)

            if has_artifact_connection:
                # Always allow internal synchronization (when _updating_from_parameter is set)
                # or legitimate upstream value propagation
                # Temporarily make both parameters settable
                self.artifact_parameter.settable = True
                self.path_parameter.settable = True

        return value

    def on_after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle post-parameter value setting for tethered parameters.

        This handles both the existing synchronization logic AND restores
        read-only state when the artifact parameter has connections.

        Args:
            parameter: The parameter that was set
            value: The value that was set
        """
        # First, handle existing synchronization logic (from original on_after_value_set)
        # Check the lock first: Skip if we're already in an update cycle to prevent infinite loops
        if self._updating_from_parameter is not None:
            return

        # Only handle our parameters
        if parameter not in (self.artifact_parameter, self.path_parameter):
            return

        # Acquire the lock: Set which parameter is driving the current update cycle
        self._updating_from_parameter = parameter
        try:
            if parameter == self.artifact_parameter:
                self._handle_artifact_change(value)
            elif parameter == self.path_parameter:
                self._handle_path_change(value)
        except Exception as e:
            # Defensive parameter type detection
            match parameter:
                case self.artifact_parameter:
                    param_type_for_error_str = "artifact"
                case self.path_parameter:
                    param_type_for_error_str = "path"
                case _:
                    param_type_for_error_str = "<UNKNOWN PARAMETER>"

            # Include input value for forensics
            if isinstance(value, str):
                value_info = f" Input: '{value}'"
            else:
                value_info = f" Input: <{type(value).__name__}> (not human readable)"

            error_msg = f"Failed to process {param_type_for_error_str} parameter '{parameter.name}' in node '{self.node.__class__.__name__}': {e}{value_info}"
            raise ValueError(error_msg) from e
        finally:
            # Always clear the update lock
            self._updating_from_parameter = None

        # Second, handle connection-aware settable restoration
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        connections = GriptapeNodes.FlowManager().get_connections()
        target_connections = connections.incoming_index.get(self.node.name)

        has_artifact_connection = target_connections and target_connections.get(self.artifact_parameter.name)

        # If artifact parameter has connections, make both read-only again
        if has_artifact_connection:
            self.artifact_parameter.settable = False
            self.path_parameter.settable = False

    def _handle_artifact_change(self, value: Any) -> None:
        """Handle changes to the artifact parameter."""
        if isinstance(value, str):
            # String input - route to path parameter logic
            self._handle_string_input_to_artifact(value)
        else:
            # Artifact input - handle as normal
            self._handle_artifact_input(value)

    def _handle_string_input_to_artifact(self, path_value: str) -> None:
        """Handle string input to artifact parameter by processing it as a path."""
        path_value = self._sanitize_path_string(path_value.strip()) if path_value else ""

        if path_value:
            try:
                # Process the path (URL or file) - reuse existing path logic
                if self._is_url(path_value):
                    download_url = self._download_and_upload_url(path_value)
                else:
                    download_url = self._upload_file_to_static_storage(path_value)

                # Create artifact dict and convert to artifact
                artifact_dict = {"value": download_url, "type": f"{self.artifact_parameter.output_type}"}
                artifact = self._to_artifact(artifact_dict)

                # Store artifact using sync helper (sets parameter value and publishes update)
                self._sync_parameter_value(
                    source_param_name=self.artifact_parameter.name,
                    target_param_name=self.artifact_parameter.name,
                    target_value=artifact,
                )

                # Update path parameter
                self._sync_parameter_value(
                    source_param_name=self.artifact_parameter.name,
                    target_param_name=self.path_parameter.name,
                    target_value=download_url,
                )
            except Exception:
                # If processing fails, treat as invalid input - reset parameters
                self._sync_parameter_value(
                    source_param_name=self.artifact_parameter.name,
                    target_param_name=self.artifact_parameter.name,
                    target_value=None,
                )
                self._sync_parameter_value(
                    source_param_name=self.artifact_parameter.name,
                    target_param_name=self.path_parameter.name,
                    target_value="",
                )
                # Don't re-raise - let the node continue with None value
        else:
            # Empty string - reset both parameters
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=None,
            )
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.path_parameter.name,
                target_value="",
            )

    def _handle_artifact_input(self, value: Any) -> None:
        """Handle artifact input to artifact parameter."""
        if value:
            # Convert to artifact and update artifact parameter
            artifact = self._to_artifact(value)
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=artifact,
            )

            # Extract URL and update path parameter
            extracted_url = self.config.extract_url_func(value)
            if extracted_url:
                self._sync_parameter_value(
                    source_param_name=self.artifact_parameter.name,
                    target_param_name=self.path_parameter.name,
                    target_value=extracted_url,
                )
        else:
            # No value - reset both parameters
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=None,
            )
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.path_parameter.name,
                target_value="",
            )

    def _handle_path_change(self, value: Any) -> None:
        """Handle changes to the path parameter."""
        path_value = self._sanitize_path_string(str(value).strip()) if value else ""

        if path_value:
            # Process the path (URL or file)
            if self._is_url(path_value):
                download_url = self._download_and_upload_url(path_value)
            else:
                download_url = self._upload_file_to_static_storage(path_value)

            # Update both parameters with the processed URL
            artifact_dict = {"value": download_url, "type": f"{self.artifact_parameter.output_type}"}
            artifact = self._to_artifact(artifact_dict)
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=artifact,
            )
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name,
                target_param_name=self.path_parameter.name,
                target_value=download_url,
            )
        else:
            # Empty path - reset both parameters
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=None,
            )
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name, target_param_name=self.path_parameter.name, target_value=""
            )

    def _sync_parameter_value(self, source_param_name: str, target_param_name: str, target_value: Any) -> None:
        """Helper to sync parameter values bidirectionally without triggering infinite loops."""
        # Use node manager's request system to ensure full parameter setting flow including downstream propagation
        # The _updating_from_parameter lock prevents infinite recursion in on_after_value_set
        from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        GriptapeNodes.handle_request(
            SetParameterValueRequest(
                parameter_name=target_param_name,
                node_name=self.node.name,
                value=target_value,
                incoming_connection_source_node_name=self.node.name,
                incoming_connection_source_parameter_name=source_param_name,
            )
        )

        # Also update output values so they're ready for process()
        self.node.parameter_output_values[target_param_name] = target_value

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
    def _sanitize_path_string(path_str: str) -> str:
        r"""Strip surrounding quotes and shell escape characters from paths.

        Handles macOS Finder's 'Copy as Pathname' format which escapes
        spaces, apostrophes, and other special characters with backslashes.
        Only removes backslashes before shell-special characters to avoid
        breaking Windows paths like C:\Users\file.txt.

        Args:
            path_str: The path string to sanitize

        Returns:
            Sanitized path string
        """
        # First, strip surrounding quotes
        if len(path_str) >= 2 and (  # noqa: PLR2004
            (path_str.startswith("'") and path_str.endswith("'"))
            or (path_str.startswith('"') and path_str.endswith('"'))
        ):
            path_str = path_str[1:-1]

        # Handle Windows extended-length paths (\\?\...) specially
        # These are used for paths longer than 260 characters on Windows
        # We need to sanitize the path part but preserve the prefix
        extended_length_prefix = ""
        if path_str.startswith("\\\\?\\"):
            extended_length_prefix = "\\\\?\\"
            path_str = path_str[4:]  # Remove prefix temporarily

        # Remove shell escape characters (backslashes before special chars only)
        # Matches: space ' " ( ) { } [ ] & | ; < > $ ` ! * ? /
        # Does NOT match: \U \t \f etc in Windows paths like C:\Users
        path_str = re.sub(r"\\([ '\"(){}[\]&|;<>$`!*?/])", r"\1", path_str)

        # Restore extended-length prefix if it was present
        if extended_length_prefix:
            path_str = extended_length_prefix + path_str

        return path_str

    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL."""
        return path.startswith(("http://", "https://"))

    def _resolve_file_path(self, file_path: str) -> Path:
        """Resolve file path to absolute path relative to workspace."""
        path = Path(file_path)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if path.is_absolute():
            if path.is_relative_to(workspace_path):
                path = path.relative_to(workspace_path)
                path = workspace_path / path
        else:
            path = workspace_path / path

        return path

    def _determine_storage_filename(self, path: Path) -> str:
        """Determine the filename to use for static storage, preserving subdirectory structure if in staticfiles."""
        workspace_path = GriptapeNodes.ConfigManager().workspace_path
        static_files_dir = GriptapeNodes.ConfigManager().get_config_value(
            "static_files_directory", default="staticfiles"
        )
        static_files_path = workspace_path / static_files_dir

        try:
            if path.is_relative_to(static_files_path):
                relative_path = path.relative_to(static_files_path)
                return str(relative_path.as_posix())
        except (ValueError, AttributeError):
            pass

        return path.name

    def _create_upload_url(self, file_name_for_storage: str) -> CreateStaticFileUploadUrlResultSuccess:
        """Create and validate upload URL for static storage."""
        upload_request = CreateStaticFileUploadUrlRequest(file_name=file_name_for_storage)
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            error_msg = f"Failed to create upload URL for file '{file_name_for_storage}': {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected result type: {type(upload_result).__name__} (expected: CreateStaticFileUploadUrlResultSuccess, file: '{file_name_for_storage}')"
            raise TypeError(error_msg)

        return upload_result

    def _read_file_data(self, path: Path, file_path: str) -> tuple[bytes, int]:
        """Read file data with specific exception handling.

        Uses OSManager.normalize_path_for_platform() to ensure Windows long path
        support (paths >260 characters).
        """
        # Normalize path for platform (handles Windows long paths with \\?\ prefix)
        normalized_path_str = GriptapeNodes.OSManager().normalize_path_for_platform(path)
        normalized_path = Path(normalized_path_str)

        try:
            file_data = normalized_path.read_bytes()
        except FileNotFoundError:
            error_msg = f"File not found: '{file_path}'"
            raise ValueError(error_msg) from None
        except PermissionError:
            error_msg = f"Permission denied reading file: '{file_path}'"
            raise ValueError(error_msg) from None
        except OSError as e:
            error_msg = f"Failed to read file '{file_path}': {e}"
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error reading file '{file_path}': {e}"
            raise ValueError(error_msg) from e

        file_size = len(file_data)
        return file_data, file_size

    def _upload_file_data(
        self, upload_result: CreateStaticFileUploadUrlResultSuccess, file_data: bytes, file_size: int, file_path: str
    ) -> None:
        """Upload file data to static storage with specific exception handling."""
        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=file_data,
                headers=upload_result.headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_msg = f"Failed to upload file '{file_path}' to static storage (HTTP {e.response.status_code}, method: {upload_result.method}, size: {file_size} bytes): {e}"
            raise ValueError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"Failed to upload file '{file_path}' to static storage (network error, method: {upload_result.method}, size: {file_size} bytes): {e}"
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error uploading file '{file_path}' to static storage (method: {upload_result.method}, size: {file_size} bytes): {e}"
            raise ValueError(error_msg) from e

    def _create_download_url(self, file_name_for_storage: str) -> CreateStaticFileDownloadUrlResultSuccess:
        """Create and validate download URL for static storage."""
        download_request = CreateStaticFileDownloadUrlRequest(file_name=file_name_for_storage)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL for file '{file_name_for_storage}': {download_result.error}"
            raise TypeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected result type: {type(download_result).__name__} (expected: CreateStaticFileDownloadUrlResultSuccess, file: '{file_name_for_storage}')"
            raise TypeError(error_msg)

        return download_result

    def _upload_file_to_static_storage(self, file_path: str) -> str:
        """Upload file to static storage and return download URL."""
        path = self._resolve_file_path(file_path)
        file_name_for_storage = self._determine_storage_filename(path)
        upload_result = self._create_upload_url(file_name_for_storage)
        file_data, file_size = self._read_file_data(path, file_path)
        self._upload_file_data(upload_result, file_data, file_size, file_path)
        download_result = self._create_download_url(file_name_for_storage)
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
            error_msg = f"Failed to download artifact from URL '{url}' (timeout: {self.URL_DOWNLOAD_TIMEOUT}s): {e}"
            raise ValueError(error_msg) from e

        # Validate content type
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith(self.config.url_content_type_prefix):
            artifact_type = self.config.url_content_type_prefix.rstrip("/")
            error_msg = f"URL '{url}' content-type '{content_type}' does not match expected '{self.config.url_content_type_prefix}*' for {artifact_type} artifacts"
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
            error_msg = f"Failed to create upload URL for file '{filename}': {upload_result.error}"
            raise TypeError(error_msg)

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected result type: {type(upload_result).__name__} (expected: CreateStaticFileUploadUrlResultSuccess, file: '{filename}')"
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
            content_size = len(response.content)
            error_msg = f"Failed to upload downloaded artifact from '{url}' to static storage (method: {upload_result.method}, size: {content_size} bytes): {e}"
            raise ValueError(error_msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=filename)
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            error_msg = f"Failed to create download URL for file '{filename}': {download_result.error}"
            raise TypeError(error_msg)

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            error_msg = f"Static file API returned unexpected result type: {type(download_result).__name__} (expected: CreateStaticFileDownloadUrlResultSuccess, file: '{filename}')"
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
            type="str",
            default_value="",
            tooltip=tooltip,
            ui_options={"display_name": display_name},
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )

        # Add file system picker trait
        # workspace_only=False allows files outside workspace since we copy them to staticfiles
        path_parameter.add_trait(
            FileSystemPicker(
                allow_directories=False,
                allow_files=True,
                file_types=list(config.supported_extensions),
                workspace_only=False,
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
