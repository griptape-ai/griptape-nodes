"""FileLocation class for encapsulating file paths with save policies."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from asyncio_thread_runner import ThreadRunner

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.drivers.location import LocationDriverRegistry
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import GetPathForMacroRequest, GetPathForMacroResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.image_metadata_injector import inject_workflow_metadata_if_image
from griptape_nodes.utils.url_utils import is_url_or_path


@dataclass(frozen=True)
class FileLocation:
    """Encapsulates a file path with save policies and macro template for deferred resolution.

    Stores the macro template and base variables instead of a pre-resolved path. This allows
    resolution at save-time with additional variables like {index} for multi-image generation.

    Attributes:
        macro_template: Macro template string (e.g., "{outputs}/{workflow_name}_{file_name_base}.{file_extension}")
        base_variables: Variables for macro resolution (e.g., {"file_name_base": "output", "file_extension": "png"})
        existing_file_policy: How to handle existing files (OVERWRITE, CREATE_NEW, FAIL)
        create_parent_dirs: Whether to create intermediate directories
    """

    macro_template: str
    base_variables: dict[str, str | int]
    existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE
    create_parent_dirs: bool = True

    def save(self, data: bytes) -> str:
        """Save data by resolving macro template and using location driver (synchronous).

        WARNING: This method may make synchronous HTTP requests which will block.
        For async contexts (node process methods), consider using asave() instead.

        Args:
            data: Binary data to save

        Returns:
            URL of the saved file for UI display

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails or macro resolution fails
        """
        with ThreadRunner() as runner:
            return runner.run(self.asave(data))

    async def asave(self, data: bytes) -> str:
        """Save data by resolving macro template and using location driver (asynchronous).

        This is the primary save implementation. Use this in async contexts like
        node process methods to avoid blocking.

        Flow:
        1. Resolve macro template to actual location
        2. Inject workflow metadata if image format supports it
        3. Find appropriate driver for location
        4. Delegate save to driver

        Args:
            data: Binary data to save

        Returns:
            URL of the saved file for UI display

        Raises:
            FileExistsError: If file exists and policy is FAIL
            RuntimeError: If save operation fails or macro resolution fails or no driver can handle location

        Example:
            >>> file_location = FileLocation.from_value("{outputs}/image.png", base_variables={...})
            >>> url = await file_location.asave(image_bytes)
        """
        # STEP 1: Resolve macro template (pre-processing)
        location = self._resolve_location()

        # STEP 2: Inject metadata if image format supports it
        file_name = Path(location).name
        data = inject_workflow_metadata_if_image(data, file_name)

        # STEP 3: Get driver for resolved location
        driver = LocationDriverRegistry.get_driver_for_location(location)

        if driver is None:
            error_msg = f"No driver can handle location: {location[:100]}"
            raise RuntimeError(error_msg)

        # STEP 4: Delegate to driver
        return await driver.asave(location, data, self.existing_file_policy.value)

    def load(self, timeout: float = 120.0) -> bytes:
        """Load file data from macro template or direct location (synchronous).

        WARNING: This method makes synchronous HTTP requests which will block.
        For async contexts (node process methods), use aload() instead.

        Supports:
        - Macro templates: "{outputs}/file.png" → resolved to file path
        - HTTP/HTTPS URLs: "https://example.com/image.png" → downloaded
        - Data URIs: "data:image/png;base64,..." → decoded
        - File paths: "/path/to/file.png" → read directly
        - Custom drivers can be registered for additional location types

        Args:
            timeout: Timeout in seconds for network operations (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If location format is invalid
            RuntimeError: If load operation fails or no driver can handle location
        """
        with ThreadRunner() as runner:
            return runner.run(self.aload(timeout=timeout))

    async def aload(self, timeout: float = 120.0) -> bytes:  # noqa: ASYNC109
        """Load file data from macro template or direct location (asynchronous).

        This is the primary load implementation. Use this in async contexts like
        node process methods to avoid blocking.

        Supports:
        - Macro templates: "{outputs}/file.png" → resolved to file path
        - HTTP/HTTPS URLs: "https://example.com/image.png" → downloaded
        - Data URIs: "data:image/png;base64,..." → decoded
        - File paths: "/path/to/file.png" → read directly
        - Custom drivers can be registered for additional location types

        Args:
            timeout: Timeout in seconds for network operations (default: 120.0)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If location format is invalid
            RuntimeError: If load operation fails or no driver can handle location

        Example:
            >>> file_location = FileLocation.from_value(url, base_variables={...})
            >>> image_bytes = await file_location.aload()
        """
        # STEP 1: Resolve macro templates (pre-processing)
        location = self._resolve_location()

        # STEP 2: Get driver for resolved location
        driver = LocationDriverRegistry.get_driver_for_location(location)

        if driver is None:
            error_msg = f"No driver can handle location: {location[:100]}"
            raise RuntimeError(error_msg)

        # STEP 3: Delegate to driver
        return await driver.aload(location, timeout)

    def to_dict(self) -> dict[str, Any]:
        """Serialize FileLocation for workflow save.

        Returns:
            Dictionary with macro_template, base_variables, existing_file_policy, create_parent_dirs
        """
        return {
            "macro_template": self.macro_template,
            "base_variables": self.base_variables,
            "existing_file_policy": self.existing_file_policy.value,
            "create_parent_dirs": self.create_parent_dirs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileLocation":
        """Deserialize FileLocation from workflow load with backward compatibility.

        Args:
            data: Dictionary with serialized FileLocation data

        Returns:
            FileLocation instance
        """
        # Backward compatibility: convert old format (resolved_path) to new format (macro_template + variables)
        if "resolved_path" in data and "macro_template" not in data:
            # Old format: just use the resolved path as a literal template
            resolved_path = data["resolved_path"]
            return cls(
                macro_template=resolved_path,
                base_variables={},
                existing_file_policy=ExistingFilePolicy(data["existing_file_policy"]),
                create_parent_dirs=data.get("create_parent_dirs", True),
            )

        # New format
        return cls(
            macro_template=data["macro_template"],
            base_variables=data["base_variables"],
            existing_file_policy=ExistingFilePolicy(data["existing_file_policy"]),
            create_parent_dirs=data.get("create_parent_dirs", True),
        )

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        base_variables: dict[str, str | int] | None = None,
        existing_file_policy: ExistingFilePolicy = ExistingFilePolicy.OVERWRITE,
        create_parent_dirs: bool = True,
    ) -> "FileLocation":
        """Create FileLocation from any supported input type.

        This factory method handles all common input types, eliminating the need for
        conditionals in node code. Supports strings, FileLocation objects, dicts,
        and Griptape artifacts.

        Args:
            value: Input value of any supported type
            base_variables: Variables for macro resolution (e.g., {"node_name": "MyNode"})
            existing_file_policy: How to handle existing files (default: OVERWRITE)
            create_parent_dirs: Whether to create parent directories (default: True)

        Returns:
            FileLocation instance ready for save/load operations

        Raises:
            ValueError: If value is None or empty string
            TypeError: If value type is not supported

        Supported input types:
        - FileLocation: returned as-is
        - str: converted to FileLocation with macro template
        - dict: deserialized from workflow save format
        - ImageArtifact: base64 extracted and used as macro template
        - ImageUrlArtifact: value extracted and used as macro template
        - Any object with 'value' attribute: value extracted and converted

        Example:
            >>> # Simple usage in nodes - no conditionals needed!
            >>> file_location = FileLocation.from_value(
            ...     self.get_parameter_value("file_path"),
            ...     base_variables={"node_name": self.name},
            ... )
            >>> static_url = file_location.save(image_bytes)
        """
        # Already a FileLocation - return as-is
        if isinstance(value, FileLocation):
            return value

        # Dict - deserialize from workflow save
        if isinstance(value, dict):
            return cls.from_dict(value)

        # None or empty string - error
        if value is None:
            error_msg = "Cannot create FileLocation from None"
            raise ValueError(error_msg)

        if isinstance(value, str) and not value:
            error_msg = "Cannot create FileLocation from empty string"
            raise ValueError(error_msg)

        # Extract value from Griptape artifacts
        extracted_value = cls._extract_artifact_value(value)
        if extracted_value is not None:
            value = extracted_value

        # String path/URL/macro template
        if isinstance(value, str):
            return cls(
                macro_template=value,
                base_variables=base_variables or {},
                existing_file_policy=existing_file_policy,
                create_parent_dirs=create_parent_dirs,
            )

        # Unsupported type
        error_msg = f"Cannot create FileLocation from type {type(value).__name__}"
        raise TypeError(error_msg)

    @staticmethod
    def _extract_artifact_value(value: Any) -> str | None:
        """Extract string value from Griptape artifacts (ImageArtifact, ImageUrlArtifact, etc.).

        Args:
            value: Potential artifact object

        Returns:
            Extracted string value, or None if not an artifact or no value found
        """
        # ImageArtifact - extract base64
        if hasattr(value, "base64"):
            b64 = getattr(value, "base64", None)
            if isinstance(b64, str) and b64:
                # Return data URI format if not already
                if b64.startswith("data:image/"):
                    return b64
                return f"data:image/png;base64,{b64}"

        # ImageUrlArtifact or other artifacts with 'value' attribute
        if hasattr(value, "value"):
            url_value = getattr(value, "value", None)
            if isinstance(url_value, str) and url_value:
                return url_value

        return None

    def _resolve_location(self) -> str:
        """Resolve macro template to actual location.

        If macro_template is a direct location (URL, data URI, path), returns it as-is.
        If it's a macro template, resolves it using ProjectManager.

        Returns:
            Resolved location string

        Raises:
            RuntimeError: If macro resolution fails
        """
        # Already a direct location - return as-is
        if is_url_or_path(self.macro_template):
            return self.macro_template

        # Macro template - resolve it
        parsed_macro = ParsedMacro(self.macro_template)
        resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=self.base_variables)
        result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

        if not isinstance(result, GetPathForMacroResultSuccess):
            error_msg = f"Failed to resolve macro template '{self.macro_template}' with variables {self.base_variables}"
            raise RuntimeError(error_msg)  # noqa: TRY004

        return str(result.absolute_path)

    def __str__(self) -> str:
        """Return resolved path for string conversion (resolves macro with base variables)."""
        parsed_macro = ParsedMacro(self.macro_template)
        resolve_request = GetPathForMacroRequest(parsed_macro=parsed_macro, variables=self.base_variables)
        result = GriptapeNodes.ProjectManager().on_get_path_for_macro_request(resolve_request)

        if isinstance(result, GetPathForMacroResultSuccess):
            return str(result.absolute_path)

        # Fallback: return the template itself if resolution fails
        return self.macro_template
