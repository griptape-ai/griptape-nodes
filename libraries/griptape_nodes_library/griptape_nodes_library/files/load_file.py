import contextlib
import importlib
import inspect
import pkgutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.events.static_file_events import (
    CreateStaticFileDownloadUrlRequest,
    CreateStaticFileDownloadUrlResultFailure,
    CreateStaticFileDownloadUrlResultSuccess,
    CreateStaticFileUploadUrlRequest,
    CreateStaticFileUploadUrlResultFailure,
    CreateStaticFileUploadUrlResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.path_utils import PathUtils
from griptape_nodes_library.files.providers.artifact_load_provider import ArtifactLoadProvider


class LoadFile(SuccessFailureNode):
    """Universal file loader with pluggable provider system.

    Handles loading of any file type (image, video, audio, text) using
    provider-specific logic while maintaining clean user-facing paths
    and preventing file collisions through structured upload naming.
    """

    def __init__(self, **kwargs) -> None:
        # Initialize attributes that might be accessed early during parent class initialization
        self._core_parameters: list[Parameter] = []  # Core parameters owned by this class (populated automatically during init)
        self._dynamic_parameters: list[Parameter] = []  # Provider-specific parameters added dynamically (tracked for removal)
        self._current_provider: ArtifactLoadProvider | None = None  # Currently active provider instance for file processing
        self._sync_lock: str | None = None  # Prevents infinite loops during three-way parameter synchronization
        self._creating_core_parameters = True  # Flag to control whether add_parameter adds to core list or dynamic list

        super().__init__(**kwargs)

        # Core parameters - owned by the class
        self.path_parameter = Parameter(
            name="path",
            type="str",
            default_value="",
            tooltip="Path to a local file or URL to load",
            ui_options={"display_name": "File Path or URL"},
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )

        self.internal_url_parameter = Parameter(
            name="_internal_url",
            type="str",
            default_value="",
            tooltip="Internal URL for file access",
            ui_options={"hide": True},
            allowed_modes={ParameterMode.PROPERTY},
            settable=False,
        )

        self.artifact_parameter = Parameter(
            name="artifact",
            input_types=["ImageUrlArtifact", "str"],  # Start with image only
            type="Any",
            output_type="Any",
            default_value=None,
            tooltip="The loaded file artifact",
            ui_options={"expander": True},
        )

        # Provider selection parameter - dynamically populated
        provider_choices = self._get_provider_choices()
        self.provider_parameter = Parameter(
            name="provider_type",
            type="str",
            default_value="Automatic Detection",
            tooltip="File type provider to use for loading",
            ui_options={"display_name": "Provider Type"},
        )
        self.provider_parameter.add_trait(Options(choices=provider_choices))

        # Add core parameters
        self.add_parameter(self.provider_parameter)
        self.add_parameter(self.path_parameter)
        self.add_parameter(self.internal_url_parameter)
        self.add_parameter(self.artifact_parameter)

        # Provider management attributes already initialized above

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the file loading operation result",
            result_details_placeholder="Details on the load attempt will be presented here.",
        )

        self._creating_core_parameters = False

    def add_parameter(self, parameter: Parameter) -> None:
        """Add a parameter to the node.

        During core parameter creation, parameters are added to the core parameters list.
        After initialization (dynamic mode), parameters are tracked for removal.
        """
        if self._creating_core_parameters:
            self._core_parameters.append(parameter)
            super().add_parameter(parameter)
            return

        # Dynamic mode: track for later removal
        if not self.does_name_exist(parameter.name):
            self._dynamic_parameters.append(parameter)
            super().add_parameter(parameter)

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to handle three-way sync."""
        parameter = self.get_parameter_by_name(param_name)
        if parameter is None:
            return

        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        self._handle_parameter_change(parameter, value)

    def _handle_parameter_change(self, parameter: Parameter, value: Any) -> None:
        """Handle post-parameter value setting with three-way sync."""
        # Skip if we're already in a sync operation to prevent infinite loops
        if self._sync_lock is not None:
            return

        # Only handle our core parameters
        if parameter not in self._core_parameters:
            return

        # Acquire sync lock
        self._sync_lock = parameter.name

        try:
            match parameter.name:
                case self.path_parameter.name:
                    self._handle_path_change(value)
                case self.artifact_parameter.name:
                    self._handle_artifact_change(value)
                case self.provider_parameter.name:
                    self._handle_provider_change(value)
                case self.internal_url_parameter.name:
                    # Internal URL is read-only, should not be changed externally
                    pass
                case _:
                    # This should never happen due to core parameter check above
                    self._raise_unexpected_parameter_error(parameter.name)
        except Exception as e:
            logger.error(
                f"Attempted to sync parameter '{parameter.name}' with value '{value}' in LoadFile '{self.name}'. "
                f"Failed due to {e}"
            )
            # Reset to safe state on error
            self._reset_parameters_to_safe_state()
            # Re-raise as fatal error
            raise
        finally:
            # Always clear the sync lock
            self._sync_lock = None

    def _handle_path_change(self, path_value: Any) -> None:
        """Handle changes to the path parameter."""
        path_str = PathUtils.normalize_path_input(path_value)

        if not path_str:
            self._reset_path_parameters()
            return

        internal_url = self._process_path_to_url(path_str)
        if internal_url is None:
            self._reset_path_parameters()
            return

        provider = self._determine_provider_for_path(path_str)
        if provider is None:
            self._reset_path_parameters()
            return

        self._create_artifact_from_provider(provider, internal_url)

    def _reset_path_parameters(self) -> None:
        """Reset path-related parameters to empty state."""
        self._sync_parameter(self.artifact_parameter.name, None)
        self._sync_parameter(self.internal_url_parameter.name, "")
        self._clear_provider_specific_parameters()

    def _process_path_to_url(self, path_str: str) -> str | None:
        """Process path string to internal URL."""
        try:
            if PathUtils.is_url(path_str):
                return self._process_url(path_str)

            file_path = PathUtils.to_path_object(path_str)
            if file_path is None:
                self._raise_path_error(f"Invalid path format: {path_str}")
                return None  # This line will never be reached due to exception above
            return self._process_file_path(file_path)
        except (ValueError, OSError) as e:
            logger.warning(f"Attempted to process path '{path_str}' in LoadFile '{self.name}'. Failed due to {e}")
            return None

    def _determine_provider_for_path(self, path_str: str) -> ArtifactLoadProvider | None:
        """Determine which provider to use for the given path."""
        current_provider_type = self.get_parameter_value(self.provider_parameter.name)

        if current_provider_type == "Automatic Detection":
            return self._auto_detect_provider_for_path(path_str)

        return self._get_explicit_provider(current_provider_type)

    def _auto_detect_provider_for_path(self, path_str: str) -> ArtifactLoadProvider | None:
        """Auto-detect provider based on path."""
        try:
            if PathUtils.is_url(path_str):
                provider = self._auto_detect_provider_for_url(path_str)
            else:
                file_path = PathUtils.to_path_object(path_str)
                if file_path is None:
                    self._raise_path_error(f"Invalid path format: {path_str}")
                    return None  # This line will never be reached due to exception above
                provider = self._auto_detect_provider_for_file(file_path)

            if provider is None:
                self._raise_path_error(f"No provider found for path: {path_str}")
                return None  # This line will never be reached due to exception above

            self._switch_to_provider(provider)
        except ValueError as e:
            logger.warning(
                f"Attempted to auto-detect provider for path '{path_str}' in LoadFile '{self.name}'. Failed due to {e}"
            )
            return None
        else:
            return provider

    def _get_explicit_provider(self, provider_type: str) -> ArtifactLoadProvider | None:
        """Get explicitly selected provider."""
        provider = self._current_provider
        if provider is None:
            provider = self._get_provider_by_name(provider_type)
            if provider is None:
                self._raise_path_error(f"Selected provider '{provider_type}' not found")
                return None  # This line will never be reached due to exception above
            self._switch_to_provider(provider)
        return provider

    def _create_artifact_from_provider(self, provider: ArtifactLoadProvider, internal_url: str) -> None:
        """Create artifact using provider and sync parameters."""
        try:
            artifact = provider.create_artifact_from_url(internal_url)
            self._sync_parameter(self.artifact_parameter.name, artifact)
            self._sync_parameter(self.internal_url_parameter.name, internal_url)
        except Exception as e:
            logger.warning(
                f"Attempted to create artifact from URL '{internal_url}' in LoadFile '{self.name}'. Failed due to {e}"
            )
            self._reset_path_parameters()

    def _raise_path_error(self, message: str) -> None:
        """Raise a ValueError for path processing errors."""
        raise ValueError(message)

    def _raise_unexpected_parameter_error(self, parameter_name: str) -> None:
        """Raise a RuntimeError for unexpected parameter in sync."""
        msg = f"Unexpected parameter '{parameter_name}' in LoadFile parameter sync"
        raise RuntimeError(msg)

    def _handle_artifact_change(self, artifact_value: Any) -> None:
        """Handle changes to the artifact parameter."""
        if artifact_value is None:
            # Clear everything
            self._sync_parameter(self.path_parameter.name, "")
            self._sync_parameter(self.internal_url_parameter.name, "")
            self._clear_provider_specific_parameters()
            return

        try:
            # Try to detect provider for artifact
            provider = self._detect_provider_for_artifact(artifact_value)
            if provider is None:
                msg = f"No provider found for artifact type: {type(artifact_value).__name__}"
                raise ValueError(msg)  # noqa: TRY301

            self._switch_to_provider(provider)
            extracted_url = provider.extract_url_from_artifact(artifact_value)
            if extracted_url:
                self._sync_parameter(self.internal_url_parameter.name, extracted_url)
                # Try to determine original path if possible
                display_path = self._extract_display_path_from_url(extracted_url)
                self._sync_parameter(self.path_parameter.name, display_path)

        except Exception as e:
            logger.warning(f"Attempted to process artifact in LoadFile '{self.name}'. Failed due to {e}")

    def _handle_provider_change(self, provider_value: str) -> None:
        """Handle changes to the provider parameter."""
        if provider_value == "Automatic Detection":
            # Re-detect provider based on current path/artifact
            current_path = self.get_parameter_value(self.path_parameter.name)
            if current_path:
                self._handle_path_change(current_path)
            return

        # Switch to specific provider
        provider = self._get_provider_by_name(provider_value)
        if provider is None:
            logger.warning(
                f"Attempted to switch to provider '{provider_value}' in LoadFile '{self.name}'. "
                f"Failed due to provider not found"
            )
            return

        self._switch_to_provider(provider)
        # Re-validate current artifact with new provider
        current_artifact = self.get_parameter_value(self.artifact_parameter.name)
        if current_artifact is not None:
            try:
                provider.validate_artifact_loadable(current_artifact)
            except Exception as e:
                logger.warning(
                    f"Attempted to validate current artifact with provider '{provider_value}' in LoadFile '{self.name}'. "
                    f"Failed due to {e}"
                )
                self._sync_parameter(self.artifact_parameter.name, None)

    def _switch_to_provider(self, new_provider: ArtifactLoadProvider) -> None:
        """Switch to a new provider, managing dynamic parameters."""
        if self._current_provider == new_provider:
            return

        # Remove old provider parameters
        if self._current_provider is not None:
            self._remove_provider_parameters()

        # Add new provider parameters
        self._add_provider_parameters(new_provider)
        self._current_provider = new_provider

        # Update provider_type parameter to match (if not locked)
        if self._sync_lock != self.provider_parameter.name:
            self._sync_parameter(self.provider_parameter.name, new_provider.provider_name)

    def _add_provider_parameters(self, provider: ArtifactLoadProvider) -> None:
        """Add provider-specific parameters to the node."""
        for param in provider.get_additional_parameters():
            # Check if parameter already exists
            existing_param = None
            with contextlib.suppress(KeyError):
                existing_param = self.get_parameter_by_name(param.name)

            if existing_param is not None:
                # Parameter exists - validate compatibility and preserve value if possible
                if self._are_parameters_compatible(existing_param, param):
                    # Update the parameter definition but keep the value
                    current_value = existing_param.default_value
                    self.remove_parameter_element_by_name(existing_param.name)
                    self.add_parameter(param)
                    if current_value is not None:
                        param.default_value = current_value
                else:
                    # Incompatible - replace with new parameter
                    self.remove_parameter_element_by_name(existing_param.name)
                    self.add_parameter(param)
            else:
                # New parameter - add it
                self.add_parameter(param)

    def _remove_provider_parameters(self) -> None:
        """Remove all dynamic provider-specific parameters from the node."""
        for param in self._dynamic_parameters[:]:  # Copy list to avoid mutation during iteration
            with contextlib.suppress(KeyError):
                self.remove_parameter_element_by_name(param.name)
                self._dynamic_parameters.remove(param)

    def _clear_provider_specific_parameters(self) -> None:
        """Clear all provider-specific parameters."""
        if self._current_provider is not None:
            self._remove_provider_parameters()
            self._current_provider = None

    def _are_parameters_compatible(self, param1: Parameter, param2: Parameter) -> bool:
        """Check if two parameters are compatible for value preservation."""
        return param1.name == param2.name and param1.type == param2.type and param1.input_types == param2.input_types

    def _auto_detect_provider_for_file(self, file_path: Path) -> ArtifactLoadProvider | None:
        """Auto-detect provider for a file path."""
        return self._auto_detect_provider(file_path=file_path)

    def _auto_detect_provider_for_url(self, url: str) -> ArtifactLoadProvider | None:
        """Auto-detect provider for a URL."""
        return self._auto_detect_provider(url=url)

    def _detect_provider_for_artifact(self, artifact: Any) -> ArtifactLoadProvider | None:
        """Detect provider based on artifact type."""
        # Simple detection based on type name
        artifact_type = type(artifact).__name__
        for provider in self._get_all_providers():
            if provider.artifact_type == artifact_type:
                return provider
        return None

    def _process_file_path(self, file_path: Path) -> str:
        """Process a file path and return internal URL."""
        workspace_path = GriptapeNodes.ConfigManager().workspace_path

        if PathUtils.is_within_workspace(file_path, workspace_path):
            # File is within workspace - create direct reference
            return self._create_workspace_url(file_path, workspace_path)

        # File is external - upload to static storage
        return self._upload_external_file(file_path)

    def _process_url(self, url: str) -> str:
        """Process a URL and return internal URL."""
        # For URLs, always download and upload to static storage
        return self._download_and_upload_url(url)

    def _create_workspace_url(self, file_path: Path, workspace_path: Path) -> str:
        """Create a URL for a workspace-relative file."""
        try:
            relative_path = PathUtils.make_workspace_relative(file_path, workspace_path)
        except ValueError as e:
            msg = (
                f"Attempted to create workspace URL for file '{file_path}' with workspace '{workspace_path}'. "
                f"Failed due to {e}"
            )
            raise ValueError(msg) from e

        # Add cache-busting timestamp
        timestamp = int(time.time())
        return f"http://localhost:8124/workspace/{relative_path}?t={timestamp}"

    def _upload_external_file(self, file_path: Path) -> str:
        """Upload external file to static storage and return URL."""
        # Generate collision-free filename
        context_manager = GriptapeNodes.ContextManager()
        workflow_name = "unknown_workflow"
        if context_manager.has_current_workflow():
            with contextlib.suppress(Exception):
                workflow_name = context_manager.get_current_workflow_name()

        upload_filename = PathUtils.generate_upload_filename(
            workflow_name=workflow_name,
            node_name=self.name,
            parameter_name=self.artifact_parameter.name,
            original_filename=file_path.name,
        )

        # Create upload URL request
        upload_request = CreateStaticFileUploadUrlRequest(file_name=f"uploads/{upload_filename}")
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            msg = (
                f"Attempted to create upload URL for file '{file_path.name}' in LoadFile '{self.name}'. "
                f"Failed due to {upload_result.error}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            msg = (
                f"Attempted to create upload URL for file '{file_path.name}' in LoadFile '{self.name}'. "
                f"Failed due to unexpected result type: {type(upload_result).__name__}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        # Read and upload file
        try:
            file_data = file_path.read_bytes()
        except Exception as e:
            msg = f"Attempted to read file '{file_path}' for upload in LoadFile '{self.name}'. Failed due to {e}"
            raise RuntimeError(msg) from e

        try:
            response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=file_data,
                headers=upload_result.headers,
                timeout=60,
            )
            response.raise_for_status()
        except Exception as e:
            msg = (
                f"Attempted to upload file '{file_path}' (size: {len(file_data)} bytes) to static storage "
                f"in LoadFile '{self.name}'. Failed due to {e}"
            )
            raise RuntimeError(msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=f"uploads/{upload_filename}")
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            msg = (
                f"Attempted to create download URL for file '{upload_filename}' in LoadFile '{self.name}'. "
                f"Failed due to {download_result.error}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            msg = (
                f"Attempted to create download URL for file '{upload_filename}' in LoadFile '{self.name}'. "
                f"Failed due to unexpected result type: {type(download_result).__name__}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        return download_result.url

    def _download_and_upload_url(self, url: str) -> str:
        """Download from URL and upload to static storage."""
        # Download from URL
        try:
            response = httpx.get(url, timeout=90)
            response.raise_for_status()
        except Exception as e:
            msg = f"Attempted to download content from URL '{url}' in LoadFile '{self.name}'. Failed due to {e}"
            raise RuntimeError(msg) from e

        # Generate filename from URL or use UUID
        context_manager = GriptapeNodes.ContextManager()
        workflow_name = "unknown_workflow"
        if context_manager.has_current_workflow():
            with contextlib.suppress(Exception):
                workflow_name = context_manager.get_current_workflow_name()

        # Try to extract filename from URL
        parsed = urlparse(url)
        if parsed.path:
            original_filename = Path(parsed.path).name
        else:
            original_filename = f"url_content_{uuid.uuid4().hex[:8]}"

        upload_filename = PathUtils.generate_upload_filename(
            workflow_name=workflow_name,
            node_name=self.name,
            parameter_name=self.artifact_parameter.name,
            original_filename=original_filename,
        )

        # Upload to static storage
        upload_request = CreateStaticFileUploadUrlRequest(file_name=f"uploads/{upload_filename}")
        upload_result = GriptapeNodes.handle_request(upload_request)

        if isinstance(upload_result, CreateStaticFileUploadUrlResultFailure):
            msg = (
                f"Attempted to create upload URL for downloaded content from '{url}' in LoadFile '{self.name}'. "
                f"Failed due to {upload_result.error}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        if not isinstance(upload_result, CreateStaticFileUploadUrlResultSuccess):
            msg = (
                f"Attempted to create upload URL for downloaded content from '{url}' in LoadFile '{self.name}'. "
                f"Failed due to unexpected result type: {type(upload_result).__name__}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        # Upload the downloaded content
        try:
            upload_response = httpx.request(
                upload_result.method,
                upload_result.url,
                content=response.content,
                headers=upload_result.headers,
                timeout=60,
            )
            upload_response.raise_for_status()
        except Exception as e:
            msg = (
                f"Attempted to upload downloaded content from '{url}' (size: {len(response.content)} bytes) "
                f"to static storage in LoadFile '{self.name}'. Failed due to {e}"
            )
            raise RuntimeError(msg) from e

        # Get download URL
        download_request = CreateStaticFileDownloadUrlRequest(file_name=f"uploads/{upload_filename}")
        download_result = GriptapeNodes.handle_request(download_request)

        if isinstance(download_result, CreateStaticFileDownloadUrlResultFailure):
            msg = (
                f"Attempted to create download URL for uploaded content from '{url}' in LoadFile '{self.name}'. "
                f"Failed due to {download_result.error}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        if not isinstance(download_result, CreateStaticFileDownloadUrlResultSuccess):
            msg = (
                f"Attempted to create download URL for uploaded content from '{url}' in LoadFile '{self.name}'. "
                f"Failed due to unexpected result type: {type(download_result).__name__}"
            )
            raise RuntimeError(  # noqa: TRY004
                msg
            )

        return download_result.url

    def _extract_display_path_from_url(self, internal_url: str) -> str:
        """Extract a display-friendly path from an internal URL."""
        parsed = urlparse(internal_url)

        if "uploads/" in parsed.path:
            # This is an uploaded file - try to extract original filename
            path_parts = parsed.path.split("/")
            if path_parts:
                filename = path_parts[-1]
                # Try to extract original filename from our naming scheme
                parts = filename.split("_", 3)  # workflow_node_param_original
                if len(parts) >= 4:  # noqa: PLR2004
                    return parts[3]  # Return original filename part
                return filename
        elif parsed.path.startswith("/workspace/"):
            # This is a workspace file
            return parsed.path.removeprefix("/workspace/")

        return internal_url

    def _get_all_providers(self) -> list[ArtifactLoadProvider]:
        """Get all available provider instances by discovering subclasses.

        Returns:
            List of all discovered provider instances
        """
        provider_classes = self._discover_provider_classes()
        instances = []

        for provider_class in provider_classes:
            try:
                instance = provider_class()
                instances.append(instance)
            except Exception as e:
                logger.warning("Failed to instantiate provider %s: %s", provider_class.__name__, e)

        return instances

    def _get_provider_by_name(self, provider_name: str) -> ArtifactLoadProvider | None:
        """Get a provider by name.

        Args:
            provider_name: Name of the provider to find

        Returns:
            Provider instance or None if not found
        """
        for provider in self._get_all_providers():
            if provider.provider_name == provider_name:
                return provider
        return None

    def _auto_detect_provider(
        self, file_path: Path | None = None, url: str | None = None
    ) -> ArtifactLoadProvider | None:
        """Automatically detect the best provider for a file path or URL.

        Args:
            file_path: Path to check (mutually exclusive with url)
            url: URL to check (mutually exclusive with file_path)

        Returns:
            Best matching provider or None if no provider can handle the input
        """
        if file_path is None and url is None:
            return None

        if file_path is not None and url is not None:
            msg = "Cannot specify both file_path and url"
            raise ValueError(msg)

        candidates = []

        for provider in self._get_all_providers():
            if file_path is not None:
                if provider.can_handle_file(file_path):
                    priority = provider.get_priority_score(file_path)
                    candidates.append((provider, priority))
            elif url is not None and provider.can_handle_url(url):
                candidates.append((provider, 0))  # URLs don't have priority scoring yet

        if not candidates:
            return None

        # Sort by priority (highest first) and return the best candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _get_provider_choices(self) -> list[str]:
        """Get available provider choices for the UI.

        Returns:
            List of provider names including "Automatic Detection"
        """
        choices = ["Automatic Detection"]
        choices.extend(provider.provider_name for provider in self._get_all_providers())
        return choices

    def _discover_provider_classes(self) -> list[type[ArtifactLoadProvider]]:
        """Discover all ArtifactLoadProvider subclasses dynamically.

        Returns:
            List of concrete provider classes
        """
        # Import all modules in the providers package to ensure classes are loaded
        self._import_provider_modules()

        # Get all subclasses of ArtifactLoadProvider
        return [
            subclass
            for subclass in ArtifactLoadProvider.__subclasses__()
            if not inspect.isabstract(subclass)  # Only include concrete classes (not abstract)
        ]

    def _import_provider_modules(self) -> None:
        """Import all modules in the providers package to load classes."""
        try:
            import griptape_nodes_library.files.providers as providers_package

            package_path = providers_package.__path__

            # Walk through all modules in the providers package
            for _importer, modname, _ispkg in pkgutil.walk_packages(
                package_path, prefix="griptape_nodes_library.files.providers."
            ):
                try:
                    importlib.import_module(modname)
                except ImportError as e:
                    logger.debug("Could not import provider module %s: %s", modname, e)
        except Exception as e:
            logger.warning("Failed to import provider modules: %s", e)

    def _sync_parameter(self, param_name: str, value: Any) -> None:
        """Safely sync a parameter value during sync operations."""
        try:
            # Use the event system for proper parameter updates
            GriptapeNodes.handle_request(
                SetParameterValueRequest(
                    parameter_name=param_name,
                    node_name=self.name,
                    value=value,
                )
            )
            # Also update output values for immediate availability
            self.parameter_output_values[param_name] = value
        except Exception as e:
            logger.warning(
                f"Attempted to sync parameter '{param_name}' with value '{value}' in LoadFile '{self.name}'. "
                f"Failed due to {e}"
            )

    def _reset_parameters_to_safe_state(self) -> None:
        """Reset parameters to a safe state after sync errors."""
        try:
            self._sync_parameter(self.path_parameter.name, "")
            self._sync_parameter(self.internal_url_parameter.name, "")
            self._sync_parameter(self.artifact_parameter.name, None)
            self._clear_provider_specific_parameters()
        except Exception as e:
            logger.error(f"Attempted to reset parameters to safe state in LoadFile '{self.name}'. Failed due to {e}")

    def process(self) -> None:
        """Process the file loading operation."""
        # Reset execution state and result details
        self._clear_execution_status()

        # Clear output values to prevent stale data
        self.parameter_output_values[self.path_parameter.name] = ""
        self.parameter_output_values[self.internal_url_parameter.name] = ""
        self.parameter_output_values[self.artifact_parameter.name] = None

        # Get current values
        path_value = self.get_parameter_value(self.path_parameter.name)
        artifact_value = self.get_parameter_value(self.artifact_parameter.name)
        internal_url = self.get_parameter_value(self.internal_url_parameter.name)

        # Determine input source
        input_source = None
        if artifact_value is not None:
            input_source = "artifact parameter"
        elif path_value:
            input_source = "path parameter"

        if input_source is None:
            error_details = "No file path or artifact provided"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            self._handle_failure_exception(RuntimeError(error_details))
            return

        try:
            # Load and validate the artifact
            if artifact_value is None and path_value:
                # Need to load from path
                if not internal_url:
                    # Trigger path processing
                    self._handle_path_change(path_value)
                    internal_url = self.get_parameter_value(self.internal_url_parameter.name)

                if self._current_provider is not None and internal_url:
                    artifact_value = self._current_provider.create_artifact_from_url(internal_url)

            if artifact_value is None:
                msg = (
                    f"Attempted to load artifact from {input_source} in LoadFile '{self.name}'. "
                    f"Failed due to no artifact created"
                )
                raise RuntimeError(  # noqa: TRY301
                    msg
                )

            # Validate the artifact with current provider
            if self._current_provider is not None:
                self._current_provider.validate_artifact_loadable(artifact_value)
                # Process provider-specific parameters
                self._current_provider.process_additional_parameters(self, artifact_value)

            # Set successful output values
            self.parameter_output_values[self.artifact_parameter.name] = artifact_value
            self.parameter_output_values[self.path_parameter.name] = path_value or ""
            self.parameter_output_values[self.internal_url_parameter.name] = internal_url or ""

            # Success case at the end
            provider_info = f" using {self._current_provider.provider_name} provider" if self._current_provider else ""
            success_details = f"File loaded successfully from {input_source}{provider_info}"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"LoadFile '{self.name}': {success_details}")

        except Exception as e:
            error_details = f"Attempted to load file from {input_source} in LoadFile '{self.name}'. Failed due to {e}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(error_details)
            self._handle_failure_exception(e)
