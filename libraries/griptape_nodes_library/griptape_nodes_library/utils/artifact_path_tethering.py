from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, Trait
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.utils import is_url, validate_uri


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

            path_str = OSManager.strip_surrounding_quotes(str(value).strip())

            # Check if it's a URL/URI (http://, https://, file://)
            if is_url(path_str):
                valid = validate_uri(path_str)
                if not valid:
                    error_msg = f"Invalid URL/URI: '{path_str}'"
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
        """Handle string input to artifact parameter by processing it as a path.

        Normalizes local file paths to file:// URIs and syncs with path parameter.
        Note: Unlike path parameter, artifact parameter doesn't have validation trait,
        so we handle errors gracefully by resetting parameters.
        """
        path_value = OSManager.strip_surrounding_quotes(path_value.strip()) if path_value else ""

        if not path_value:
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
            return

        try:
            # Normalize local paths to file:// URIs, keep URLs as-is
            if self._is_url(path_value):
                normalized_url = path_value
            else:
                normalized_url = self._normalize_path_to_uri(path_value)

            # Create artifact with the normalized URL
            artifact_dict = {"value": normalized_url, "type": f"{self.artifact_parameter.output_type}"}
            artifact = self._to_artifact(artifact_dict)

            # Update both parameters
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=artifact,
            )
            self._sync_parameter_value(
                source_param_name=self.artifact_parameter.name,
                target_param_name=self.path_parameter.name,
                target_value=normalized_url,
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

    def _handle_artifact_input(self, value: Any) -> None:
        """Handle artifact input to artifact parameter.

        Note: UI/browser handles resolving localhost static storage URLs to file:// URIs
        before setting the parameter value, so this method can assume it receives the
        correct URL format.
        """
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
        """Handle changes to the path parameter.

        Normalizes local file paths to file:// URIs and syncs with artifact parameter.
        Validation has already been performed by ArtifactPathValidator trait.
        """
        path_value = OSManager.strip_surrounding_quotes(str(value).strip()) if value else ""

        if not path_value:
            # Empty path - reset both parameters
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name,
                target_param_name=self.artifact_parameter.name,
                target_value=None,
            )
            self._sync_parameter_value(
                source_param_name=self.path_parameter.name,
                target_param_name=self.path_parameter.name,
                target_value="",
            )
            return

        # Normalize local paths to file:// URIs, keep URLs as-is
        if self._is_url(path_value):
            normalized_url = path_value
        else:
            normalized_url = self._normalize_path_to_uri(path_value)

        # Create artifact with the normalized URL
        artifact_dict = {"value": normalized_url, "type": f"{self.artifact_parameter.output_type}"}
        artifact = self._to_artifact(artifact_dict)

        # Update both parameters
        self._sync_parameter_value(
            source_param_name=self.path_parameter.name,
            target_param_name=self.artifact_parameter.name,
            target_value=artifact,
        )
        self._sync_parameter_value(
            source_param_name=self.path_parameter.name,
            target_param_name=self.path_parameter.name,
            target_value=normalized_url,
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

    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL/URI.

        Supports http://, https://, and file:// URIs.
        """
        return is_url(path)

    def _normalize_path_to_uri(self, path: str) -> str:
        """Normalize a local file path to a file:// URI.

        Args:
            path: Local file path (absolute or relative)

        Returns:
            file:// URI for the absolute path
        """
        file_path = Path(path)

        if not file_path.is_absolute():
            file_path = GriptapeNodes.ConfigManager().workspace_path / file_path

        return file_path.as_uri()

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
