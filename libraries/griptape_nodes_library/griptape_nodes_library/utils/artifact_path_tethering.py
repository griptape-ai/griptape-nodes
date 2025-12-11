import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import unquote, urlparse

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait
from griptape_nodes.exe_types.node_types import BaseNode, TransformedParameterValue
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.utils import get_content_type_from_extension, is_url, validate_url


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

    def validators_for_trait(self) -> list:
        def validate_path(param: Parameter, value: Any) -> None:  # noqa: ARG001
            if not value or not str(value).strip():
                return  # Empty values are allowed

            path_str = OSManager.strip_surrounding_quotes(str(value).strip())

            # Check if it's a URL
            if is_url(path_str):
                valid = validate_url(path_str)
                if not valid:
                    error_msg = f"Invalid URL: '{path_str}'"
                    raise ValueError(error_msg)
            else:
                # Sanitize file paths before validation to handle shell escapes from macOS Finder
                from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

                sanitized_path = GriptapeNodes.OSManager().sanitize_path_string(path_str)

                # Validate file path exists and has supported extension
                path = Path(sanitized_path)

                if not path.is_absolute():
                    path = GriptapeNodes.ConfigManager().workspace_path / path

                if not path.exists():
                    error_msg = f"File not found: '{sanitized_path}'"
                    raise FileNotFoundError(error_msg)

                if not path.is_file():
                    path_type = "directory" if path.is_dir() else "special file" if path.exists() else "unknown"
                    error_msg = f"Path exists but is not a file: '{sanitized_path}' (found: {path_type})"
                    raise ValueError(error_msg)

                if path.suffix.lower() not in self.supported_extensions:
                    supported = ", ".join(self.supported_extensions)
                    error_msg = (
                        f"Unsupported file format '{path.suffix}' for file '{sanitized_path}'. Supported: {supported}"
                    )
                    raise ValueError(error_msg)

        return [validate_path]


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
        3. Node calls helper.on_before_value_set() in before_value_set()
        4. Node calls helper.on_after_value_set() in after_value_set()
        5. Node calls helper.on_incoming_connection() in after_incoming_connection()
        6. Node calls helper.on_incoming_connection_removed() in after_incoming_connection_removed()
    """

    # Timeout constants - shared across all artifact types
    URL_DOWNLOAD_TIMEOUT: ClassVar[int] = 900  # seconds (15 minutes)

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

    def on_before_value_set(self, parameter: Parameter, value: Any) -> Any | TransformedParameterValue:
        """Handle parameter value setting for tethered parameters.

        This transforms string inputs to artifacts BEFORE propagation to downstream nodes.

        Args:
            parameter: The parameter being set
            value: The value being set

        Returns:
            The value to actually set (may be transformed from str to artifact).
            Returns TransformedParameterValue when transforming type to ensure proper validation.
        """
        # Transform string inputs to artifacts for the artifact parameter BEFORE propagation
        # This ensures downstream nodes receive the correct artifact type immediately
        # Skip transformation if we're already in an update cycle to prevent infinite loops
        if parameter == self.artifact_parameter and isinstance(value, str) and self._updating_from_parameter is None:
            artifact = self._process_path_string(value)
            # Return both the transformed value and its type for proper validation
            return TransformedParameterValue(value=artifact, parameter_type=self.artifact_parameter.output_type)

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

    def _sync_both_parameters(self, artifact: Any, source_param_name: str) -> None:
        """Sync both artifact and path parameters from an artifact value.

        Unified sync logic for bidirectional tethering. Extracts URL from artifact
        and updates both parameters consistently.

        Args:
            artifact: The artifact object (or None to reset both parameters)
            source_param_name: Name of the parameter that triggered the sync
        """
        if artifact:
            download_url = self.config.extract_url_func(artifact)
            artifact_value = artifact
            path_value = download_url if download_url else ""
        else:
            # No artifact, so clear both.
            artifact_value = None
            path_value = ""

        self._sync_parameter_value(
            source_param_name=source_param_name,
            target_param_name=self.artifact_parameter.name,
            target_value=artifact_value,
        )
        self._sync_parameter_value(
            source_param_name=source_param_name,
            target_param_name=self.path_parameter.name,
            target_value=path_value,
        )

    def _handle_artifact_change(self, value: Any) -> None:
        """Handle changes to the artifact parameter.

        After transformation in before_value_set, this only handles artifact objects
        and syncs the path parameter with the artifact's URL.
        """
        if isinstance(value, str):
            error_msg = f"Unexpected string value in _handle_artifact_change for artifact parameter '{self.artifact_parameter.name}'. Strings should have been transformed to artifacts in on_before_value_set."
            raise TypeError(error_msg)

        # Convert to artifact and sync both parameters
        artifact = self._to_artifact(value) if value else None
        self._sync_both_parameters(artifact, self.artifact_parameter.name)

    def _process_path_string(self, path_value: str) -> Any | None:
        """Process a path string (URL or file path) and return an artifact.

        This is the core transformation logic extracted for reuse. Returns None if
        the path is empty or processing fails.

        Args:
            path_value: The path or URL string to process

        Returns:
            The artifact object, or None if processing failed
        """
        path_value = OSManager.strip_surrounding_quotes(path_value.strip()) if path_value else ""

        if not path_value:
            return None

        try:
            # Process the path (URL or file) - reuse existing path logic
            if is_url(path_value):
                # Check if it's a file:// URI pointing to workspace staticfiles
                # If so, no need to re-download/upload - just pass through
                if self._is_workspace_staticfiles_uri(path_value):
                    download_url = path_value
                else:
                    # External URL or file outside workspace - download and upload
                    download_url = self._download_and_upload_url(path_value)
            else:
                # Sanitize file paths (not URLs) to handle shell escapes from macOS Finder
                sanitized_path = GriptapeNodes.OSManager().sanitize_path_string(path_value)
                download_url = self._upload_file_to_static_storage(sanitized_path)

            # Create artifact dict and convert to artifact
            artifact_dict = {"value": download_url, "type": f"{self.artifact_parameter.output_type}"}
            return self._to_artifact(artifact_dict)
        except Exception:
            # If processing fails, return None (let the node continue with None value)
            return None

    def _handle_path_change(self, value: Any) -> None:
        """Handle changes to the path parameter."""
        path_value = str(value).strip() if value else ""

        # Process path string and sync both parameters
        artifact = self._process_path_string(path_value)
        self._sync_both_parameters(artifact, self.path_parameter.name)

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

    def _resolve_file_path(self, file_path: str) -> Path:
        """Resolve file path to absolute path relative to workspace."""
        path = Path(file_path)
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if path.is_absolute():
            # User may have specified an absolute path,
            # but see if that is actually relative to the workspace.
            if path.is_relative_to(workspace_path):
                path = path.relative_to(workspace_path)
                path = workspace_path / path
        else:
            # Relative path
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

    def _upload_file_to_static_storage(self, file_path: str) -> str:
        """Upload file to static storage and return file:// URI."""
        path = self._resolve_file_path(file_path)
        file_name_for_storage = self._determine_storage_filename(path)

        # Read file data
        file_data = GriptapeNodes.FileManager().read_file(str(path), workspace_only=False)

        # Write to workspace and get file:// URI
        file_uri = GriptapeNodes.FileManager().write_file(file_data, file_name_for_storage)
        return file_uri

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

    def _is_workspace_staticfiles_uri(self, url: str) -> bool:
        """Check if a file:// URI points to a file already in the workspace staticfiles directory.

        Args:
            url: The URL to check (should be a file:// URI)

        Returns:
            True if the file:// URI points to workspace staticfiles, False otherwise
        """
        if not url.startswith("file://"):
            return False

        # Decode the file:// URI to a path
        from urllib.request import url2pathname

        parsed = urlparse(url)
        file_path = Path(url2pathname(unquote(parsed.path)))

        # Check if it's in the workspace
        workspace_path = GriptapeNodes.ConfigManager().workspace_path
        try:
            if not file_path.is_relative_to(workspace_path):
                return False
        except ValueError:
            return False

        # Check if it's in the staticfiles directory (or a workflow-specific staticfiles subdirectory)
        static_files_dir = GriptapeNodes.ConfigManager().get_config_value(
            "static_files_directory", default="staticfiles"
        )

        try:
            relative_path = file_path.relative_to(workspace_path)
        except ValueError:
            return False

        # Check if the path contains the staticfiles directory anywhere in its hierarchy
        # This handles both "staticfiles/image.png" and "myflow/staticfiles/image.png"
        return static_files_dir in relative_path.parts

    def _download_and_upload_url(self, url: str) -> str:
        """Download artifact from URL and upload to static storage, return file:// URI."""
        # Read file from URL (supports http://, https://, file://)
        content = GriptapeNodes.FileManager().read_file(url, workspace_only=False)

        # Validate content type by checking file extension or URL
        content_type = get_content_type_from_extension(url)
        if not content_type:
            parsed = urlparse(url)
            if parsed.scheme == "file":
                file_path = Path(unquote(parsed.path))
                content_type = get_content_type_from_extension(file_path)

            if not content_type:
                error_msg = f"Unable to determine content type from URI '{url}'"
                raise ValueError(error_msg)

        # Validate content type matches expected prefix
        if not content_type.startswith(self.config.url_content_type_prefix):
            artifact_type = self.config.url_content_type_prefix.rstrip("/")
            error_msg = f"URI '{url}' content-type '{content_type}' does not match expected '{self.config.url_content_type_prefix}*' for {artifact_type} artifacts"
            raise ValueError(error_msg)

        # Generate filename from URL
        filename = self._generate_filename_from_url(url)

        # Validate and fix file extension
        if "." in filename and filename.count(".") > 0:
            extension = f".{filename.split('.')[-1].lower()}"
            if extension not in self.config.supported_extensions:
                filename = f"{filename.rsplit('.', 1)[0]}.{self.config.default_extension}"
        else:
            filename = f"{filename}.{self.config.default_extension}"

        # Write to workspace and return file:// URI
        file_uri = GriptapeNodes.FileManager().write_file(content, filename)
        return file_uri

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
