"""Manager for artifact operations."""

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar

import semver
from pydantic import BaseModel, ValidationError

from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.artifact_events import (
    GeneratePreviewFromDefaultsRequest,
    GeneratePreviewFromDefaultsResultFailure,
    GeneratePreviewFromDefaultsResultSuccess,
    GeneratePreviewRequest,
    GeneratePreviewResultFailure,
    GeneratePreviewResultSuccess,
    GetArtifactProviderDetailsRequest,
    GetArtifactProviderDetailsResultFailure,
    GetArtifactProviderDetailsResultSuccess,
    GetPreviewForArtifactRequest,
    GetPreviewForArtifactResultFailure,
    GetPreviewForArtifactResultSuccess,
    GetPreviewGeneratorDetailsRequest,
    GetPreviewGeneratorDetailsResultFailure,
    GetPreviewGeneratorDetailsResultSuccess,
    ListArtifactProvidersRequest,
    ListArtifactProvidersResultFailure,
    ListArtifactProvidersResultSuccess,
    ListPreviewGeneratorsRequest,
    ListPreviewGeneratorsResultFailure,
    ListPreviewGeneratorsResultSuccess,
    PreviewGenerationPolicy,
    RegisterArtifactProviderRequest,
    RegisterArtifactProviderResultFailure,
    RegisterArtifactProviderResultSuccess,
    RegisterPreviewGeneratorRequest,
    RegisterPreviewGeneratorResultFailure,
    RegisterPreviewGeneratorResultSuccess,
)
from griptape_nodes.retained_mode.events.config_events import (
    GetConfigValueRequest,
    GetConfigValueResultSuccess,
    SetConfigValueRequest,
)
from griptape_nodes.retained_mode.events.os_events import (
    DeleteFileRequest,
    ExistingFilePolicy,
    GetFileInfoRequest,
    GetFileInfoResultSuccess,
    ReadFileRequest,
    ReadFileResultSuccess,
    ResolveMacroPathRequest,
    ResolveMacroPathResultSuccess,
    WriteFileRequest,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.artifact_providers import (
    BaseArtifactPreviewGenerator,
    BaseArtifactProvider,
    ImageArtifactProvider,
    ProviderRegistry,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class PreviewMetadata(BaseModel):
    """Metadata for a generated preview artifact.

    Attributes:
        version: Metadata format version (semver)
        source_macro_path: Macro template string for source artifact
        source_file_size: Source file size in bytes
        source_file_modified_time: Source file modification timestamp (Unix time)
        preview_file_names: Name(s) of preview file(s) - str for single file, dict for multiple
        preview_generator_name: Friendly name of preview generator used
        preview_generator_parameters: Parameters supplied to preview generator
    """

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    version: str
    source_macro_path: str
    source_file_size: int
    source_file_modified_time: float
    preview_file_names: str | dict[str, str]
    preview_generator_name: str
    preview_generator_parameters: dict[str, Any]


class PreviewSettings(BaseModel):
    """Preview settings read from config with fallback to defaults.

    Attributes:
        format: Preview format (e.g., 'png', 'webp')
        generator_name: Friendly name of preview generator
        generator_params: Generator-specific parameters
    """

    format: str
    generator_name: str
    generator_params: dict[str, Any]


class ArtifactManager:
    """Manages artifact operations including preview generation.

    Coordinates artifact type providers to handle different media formats.
    Providers are looked up by file extension for efficient routing.
    """

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the ArtifactManager.

        Args:
            event_manager: Optional event manager for handling artifact events
        """
        # Provider registry for managing artifact providers
        self._registry = ProviderRegistry()

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(
                GeneratePreviewRequest, self.on_handle_generate_preview_request
            )
            event_manager.assign_manager_to_request_type(
                GeneratePreviewFromDefaultsRequest, self.on_handle_generate_preview_from_defaults_request
            )
            event_manager.assign_manager_to_request_type(
                GetPreviewForArtifactRequest, self.on_handle_get_preview_for_artifact_request
            )
            event_manager.assign_manager_to_request_type(
                RegisterArtifactProviderRequest, self.on_handle_register_artifact_provider_request
            )
            event_manager.assign_manager_to_request_type(
                ListArtifactProvidersRequest, self.on_handle_list_artifact_providers_request
            )
            event_manager.assign_manager_to_request_type(
                GetArtifactProviderDetailsRequest, self.on_handle_get_artifact_provider_details_request
            )
            event_manager.assign_manager_to_request_type(
                RegisterPreviewGeneratorRequest, self.on_handle_register_preview_generator_request
            )
            event_manager.assign_manager_to_request_type(
                ListPreviewGeneratorsRequest, self.on_handle_list_preview_generators_request
            )
            event_manager.assign_manager_to_request_type(
                GetPreviewGeneratorDetailsRequest, self.on_handle_get_preview_generator_details_request
            )

            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )

    async def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        """Handle app initialization complete event.

        Registers default artifact providers after the system is fully initialized.

        Args:
            _payload: App initialization complete payload
        """
        # Register default providers (order matters: Image, Video, Audio)
        # Generator settings are now registered automatically via _register_provider_settings()
        failures = []
        for provider_class in [ImageArtifactProvider]:
            request = RegisterArtifactProviderRequest(provider_class=provider_class)
            result = self.on_handle_register_artifact_provider_request(request)
            if isinstance(result, RegisterArtifactProviderResultFailure):
                provider_name = provider_class.__name__
                failures.append(f"{provider_name}: {result.result_details}")

        if failures:
            failure_details = "; ".join(failures)
            error_message = (
                f"Attempted to register default artifact providers during initialization. "
                f"Failed due to: {failure_details}"
            )
            logger.error(error_message)
            raise RuntimeError(error_message)

    async def on_handle_generate_preview_request(  # noqa: PLR0911, C901, PLR0912, PLR0915
        self, request: GeneratePreviewRequest
    ) -> GeneratePreviewResultSuccess | GeneratePreviewResultFailure:
        """Handle generate preview request.

        Args:
            request: Contains macro_path, artifact_provider_name, format (optional), preview_generator_name (optional)

        Returns:
            Success or failure result
        """
        # FAILURE CASE: Resolve source path from MacroPath
        resolve_request = ResolveMacroPathRequest(macro_path=request.macro_path)
        resolve_result = GriptapeNodes.handle_request(resolve_request)

        if not isinstance(resolve_result, ResolveMacroPathResultSuccess):
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to resolve macro path. Failed due to: {resolve_result.result_details}"
            )

        source_path = resolve_result.resolved_path

        # FAILURE CASE: Verify file exists
        file_info_request = GetFileInfoRequest(path=source_path, workspace_only=False)
        file_info_result = GriptapeNodes.handle_request(file_info_request)

        if not isinstance(file_info_result, GetFileInfoResultSuccess):
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. "
                f"Failed due to: {file_info_result.result_details}"
            )

        if file_info_result.file_entry is None:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. Failed due to: file not found"
            )

        # FAILURE CASE: Extract file extension
        file_extension = Path(source_path).suffix[1:].lower()
        if not file_extension:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. Failed due to: no file extension"
            )

        # FAILURE CASE: Look up provider by friendly name
        provider_class = self._registry.get_provider_class_by_friendly_name(request.artifact_provider_name)
        if provider_class is None:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. "
                f"Failed due to: provider '{request.artifact_provider_name}' not found"
            )

        # FAILURE CASE: Verify provider supports this file format
        if file_extension not in provider_class.get_supported_formats():
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. "
                f"Failed due to: provider '{request.artifact_provider_name}' does not support file format '{file_extension}'"
            )

        # FAILURE CASE: Instantiate provider
        try:
            provider_instance = self._registry.get_or_create_provider_instance(provider_class)
        except Exception as e:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # Determine generator name (use request value or default)
        if request.preview_generator_name is not None:
            generator_name = request.preview_generator_name
        else:
            generator_name = provider_class.get_default_preview_generator()

        # Determine preview format (use request value or default)
        if request.format is not None:
            preview_format = request.format
        else:
            preview_format = provider_class.get_default_preview_format()

        # Calculate destination path using nodes_previews pattern
        source_path_obj = Path(source_path)
        destination_dir = source_path_obj.parent / "nodes_previews"
        preview_file_name = f"{source_path_obj.name}.{preview_format}"

        # FAILURE CASE: Call provider and get returned filenames
        try:
            preview_file_names = await provider_instance.attempt_generate_preview(
                preview_generator_friendly_name=generator_name,
                source_file_location=source_path,
                preview_format=preview_format,
                destination_preview_directory=str(destination_dir),
                destination_preview_file_name=preview_file_name,
                params=request.preview_generator_parameters,
            )
        except Exception as e:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. Failed due to: {e}"
            )

        # OPTIONAL: Generate metadata if requested
        metadata_path = None
        if request.generate_preview_metadata_json:
            # Helper to clean up preview file(s) on metadata failure
            def fail_with_cleanup(error_details: str) -> GeneratePreviewResultFailure:
                if isinstance(preview_file_names, str):
                    preview_path = str(destination_dir / preview_file_names)
                    delete_request = DeleteFileRequest(path=preview_path, workspace_only=False)
                    delete_result = GriptapeNodes.handle_request(delete_request)

                    if delete_result.failed():
                        error_details += (
                            f". Additionally, failed to delete preview file: {delete_result.result_details}"
                        )
                else:
                    # Multi-file cleanup
                    for filename in preview_file_names.values():
                        preview_path = str(destination_dir / filename)
                        delete_request = DeleteFileRequest(path=preview_path, workspace_only=False)
                        delete_result = GriptapeNodes.handle_request(delete_request)

                        if delete_result.failed():
                            error_details += f". Additionally, failed to delete preview file {filename}: {delete_result.result_details}"

                return GeneratePreviewResultFailure(result_details=error_details)

            # Step 1: Create metadata object
            metadata = PreviewMetadata(
                version=PreviewMetadata.LATEST_SCHEMA_VERSION,
                source_macro_path=request.macro_path.parsed_macro.template,
                source_file_size=file_info_result.file_entry.size,
                source_file_modified_time=file_info_result.file_entry.modified_time,
                preview_file_names=preview_file_names,
                preview_generator_name=generator_name,
                preview_generator_parameters=deepcopy(request.preview_generator_parameters),
            )

            # Step 2: Serialize to JSON
            try:
                metadata_content = json.dumps(metadata.model_dump(), indent=2)
            except Exception as e:
                return fail_with_cleanup(
                    f"Attempted to generate preview for '{source_path}'. "
                    f"Preview created but metadata serialization failed: {e}"
                )

            # Step 3: Write metadata file (named after source file, not preview)
            metadata_path = str(destination_dir / f"{source_path_obj.name}.json")
            metadata_write_request = WriteFileRequest(
                file_path=metadata_path,
                content=metadata_content,
                create_parents=True,
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
            metadata_write_result = GriptapeNodes.handle_request(metadata_write_request)

            if not isinstance(metadata_write_result, WriteFileResultSuccess):
                return fail_with_cleanup(
                    f"Attempted to generate preview for '{source_path}'. "
                    f"Preview created but metadata write failed: {metadata_write_result.result_details}"
                )

        # SUCCESS PATH: Build result message and paths
        if isinstance(preview_file_names, str):
            paths_to_preview = str(destination_dir / preview_file_names)
        else:
            paths_to_preview = {key: str(destination_dir / filename) for key, filename in preview_file_names.items()}

        result_message = f"Successfully generated preview of {source_path}"
        if metadata_path is not None:
            result_message += f". Metadata at {metadata_path}"

        return GeneratePreviewResultSuccess(result_details=result_message, paths_to_preview=paths_to_preview)

    async def on_handle_generate_preview_from_defaults_request(
        self, request: GeneratePreviewFromDefaultsRequest
    ) -> GeneratePreviewFromDefaultsResultSuccess | GeneratePreviewFromDefaultsResultFailure:
        """Handle generate preview request using config defaults.

        Reads settings from config with intelligent fallback, then delegates to GeneratePreviewRequest.
        Provider's generate_preview() does all validation.

        Args:
            request: Contains macro_path and artifact_provider_name

        Returns:
            Success or failure result
        """
        # FAILURE CASE: Look up provider
        provider_class = self._registry.get_provider_class_by_friendly_name(request.artifact_provider_name)
        if provider_class is None:
            return GeneratePreviewFromDefaultsResultFailure(
                result_details=f"Attempted to generate preview using defaults. "
                f"Failed due to: provider '{request.artifact_provider_name}' not found"
            )

        # Read settings from config with fallback (no validation)
        settings = self._get_preview_settings_from_config(provider_class, request.artifact_provider_name)

        # Delegate to GeneratePreviewRequest (provider will validate)
        generate_request = GeneratePreviewRequest(
            macro_path=request.macro_path,
            artifact_provider_name=request.artifact_provider_name,
            format=settings.format,
            preview_generator_name=settings.generator_name,
            preview_generator_parameters=settings.generator_params,
            generate_preview_metadata_json=True,
        )

        result = await self.on_handle_generate_preview_request(generate_request)

        # FAILURE CASE: Delegation/validation failed
        if isinstance(result, GeneratePreviewResultFailure):
            return GeneratePreviewFromDefaultsResultFailure(result_details=result.result_details)

        # SUCCESS PATH: Preview generated successfully
        return GeneratePreviewFromDefaultsResultSuccess(
            result_details=result.result_details, paths_to_preview=result.paths_to_preview
        )

    async def on_handle_get_preview_for_artifact_request(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self, request: GetPreviewForArtifactRequest
    ) -> GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure:
        """Handle get preview for artifact request with policy-based generation.

        Args:
            request: Contains macro_path, artifact_provider_name, and preview_generation_policy

        Returns:
            Success with path_to_preview string, or failure with details
        """
        # FAILURE CASE: Resolve source path from MacroPath
        resolve_request = ResolveMacroPathRequest(macro_path=request.macro_path)
        resolve_result = GriptapeNodes.handle_request(resolve_request)

        if not isinstance(resolve_result, ResolveMacroPathResultSuccess):
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to resolve source macro path. Failed due to: {resolve_result.result_details}"
            )

        source_path = resolve_result.resolved_path

        # FAILURE CASE: Verify source file exists and get its metadata
        file_info_request = GetFileInfoRequest(path=source_path, workspace_only=False)
        file_info_result = GriptapeNodes.handle_request(file_info_request)

        if not isinstance(file_info_result, GetFileInfoResultSuccess):
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get file info for '{source_path}'. Failed due to: {file_info_result.result_details}"
            )

        if file_info_result.file_entry is None:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: source file not found"
            )

        # FAILURE CASE: Validate provider
        provider_class = self._registry.get_provider_class_by_friendly_name(request.artifact_provider_name)
        if provider_class is None:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: provider '{request.artifact_provider_name}' not found"
            )

        # Calculate metadata path
        source_path_obj = Path(source_path)
        destination_dir = source_path_obj.parent / "nodes_previews"
        metadata_path = str(destination_dir / f"{source_path_obj.name}.json")

        # Check if metadata file exists
        metadata_info_request = GetFileInfoRequest(path=metadata_path, workspace_only=False)
        metadata_info_result = GriptapeNodes.handle_request(metadata_info_request)

        metadata_exists = (
            isinstance(metadata_info_result, GetFileInfoResultSuccess) and metadata_info_result.file_entry is not None
        )

        # EARLY CASE: Missing metadata - match on policy
        if not metadata_exists:
            match request.preview_generation_policy:
                case PreviewGenerationPolicy.DO_NOT_GENERATE:
                    return GetPreviewForArtifactResultFailure(
                        result_details=f"Attempted to get preview for '{source_path}'. Failed due to: metadata file not found at '{metadata_path}'"
                    )
                case (
                    PreviewGenerationPolicy.ONLY_IF_STALE
                    | PreviewGenerationPolicy.IF_DOES_NOT_MATCH_USER_PREVIEW_SETTINGS
                    | PreviewGenerationPolicy.ALWAYS
                ):
                    # Generate from defaults since no metadata exists
                    generate_request = GeneratePreviewFromDefaultsRequest(
                        macro_path=request.macro_path,
                        artifact_provider_name=request.artifact_provider_name,
                    )
                    generate_result = await self.on_handle_generate_preview_from_defaults_request(generate_request)

                    if isinstance(generate_result, GeneratePreviewFromDefaultsResultSuccess):
                        return GetPreviewForArtifactResultSuccess(
                            result_details=f"Preview generated for '{source_path}'",
                            paths_to_preview=generate_result.paths_to_preview,
                        )
                    return GetPreviewForArtifactResultFailure(
                        result_details=f"Attempted to generate preview for '{source_path}'. Failed due to: {generate_result.result_details}"
                    )
                case _:
                    return GetPreviewForArtifactResultFailure(
                        result_details=f"Attempted to get preview for '{source_path}'. Failed due to: unknown policy '{request.preview_generation_policy}'"
                    )

        # Read metadata file
        read_metadata_request = ReadFileRequest(
            file_path=metadata_path,
            workspace_only=False,
            should_transform_image_content_to_thumbnail=False,
        )
        read_metadata_result = GriptapeNodes.handle_request(read_metadata_request)

        if not isinstance(read_metadata_result, ReadFileResultSuccess):
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: could not read metadata file at '{metadata_path}'"
            )

        # Parse and validate metadata using Pydantic
        try:
            metadata_dict = json.loads(read_metadata_result.content)
            metadata = PreviewMetadata.model_validate(metadata_dict)
        except json.JSONDecodeError as e:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: malformed metadata JSON - {e}"
            )
        except ValidationError as e:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: invalid metadata - {e}"
            )

        # Validate preview metadata version
        try:
            metadata_version = semver.VersionInfo.parse(metadata.version)
            latest_version = semver.VersionInfo.parse(PreviewMetadata.LATEST_SCHEMA_VERSION)

            if metadata_version < latest_version:
                metadata_version_outdated = True
            else:
                metadata_version_outdated = False
        except ValueError as e:
            return GetPreviewForArtifactResultFailure(
                result_details=(
                    f"Attempted to get preview for '{source_path}'. "
                    f"Invalid metadata version format '{metadata.version}': {e}"
                )
            )

        # Check preview files exist on disk
        preview_files_missing = False
        if isinstance(metadata.preview_file_names, str):
            # Single file case
            preview_file_path = str(destination_dir / metadata.preview_file_names)
            preview_info_request = GetFileInfoRequest(path=preview_file_path, workspace_only=False)
            preview_info_result = GriptapeNodes.handle_request(preview_info_request)

            if not isinstance(preview_info_result, GetFileInfoResultSuccess) or preview_info_result.file_entry is None:
                preview_files_missing = True
        else:
            # Multi-file case
            for filename in metadata.preview_file_names.values():
                file_path = str(destination_dir / filename)
                preview_file_check_request = GetFileInfoRequest(path=file_path, workspace_only=False)
                preview_file_check_result = GriptapeNodes.handle_request(preview_file_check_request)

                if (
                    not isinstance(preview_file_check_result, GetFileInfoResultSuccess)
                    or preview_file_check_result.file_entry is None
                ):
                    preview_files_missing = True
                    break

        # Check source staleness
        source_size = file_info_result.file_entry.size
        source_mtime = file_info_result.file_entry.modified_time
        source_is_stale = self._is_preview_source_stale(metadata, source_size, source_mtime)

        # Determine if there's any validity issue
        has_validity_issue = metadata_version_outdated or preview_files_missing or source_is_stale

        # Match on policy to determine if regeneration is needed
        should_regenerate_preview = False

        match request.preview_generation_policy:
            case PreviewGenerationPolicy.DO_NOT_GENERATE:
                if has_validity_issue:
                    if metadata_version_outdated:
                        return GetPreviewForArtifactResultFailure(
                            result_details=(
                                f"Attempted to get preview for '{source_path}'. "
                                f"Preview metadata version {metadata.version} is outdated. "
                                f"Latest version is {PreviewMetadata.LATEST_SCHEMA_VERSION}. "
                                f"Please regenerate the preview."
                            )
                        )
                    if preview_files_missing:
                        return GetPreviewForArtifactResultFailure(
                            result_details=f"Attempted to get preview for '{source_path}'. Preview file(s) not found."
                        )
                    if source_is_stale:
                        return GetPreviewForArtifactResultFailure(
                            result_details=(
                                f"Attempted to get preview for '{source_path}'. "
                                f"Preview metadata exists but is stale (source file modified since preview generation). "
                                f"Please regenerate the preview."
                            )
                        )
            case PreviewGenerationPolicy.ONLY_IF_STALE:
                if has_validity_issue:
                    should_regenerate_preview = True
            case PreviewGenerationPolicy.IF_DOES_NOT_MATCH_USER_PREVIEW_SETTINGS:
                if has_validity_issue:
                    should_regenerate_preview = True
                else:
                    # Check if settings match
                    preview_settings = self._get_preview_settings_from_config(
                        provider_class, request.artifact_provider_name
                    )
                    settings_match = self._does_preview_match_current_settings(
                        metadata, preview_settings.generator_name, preview_settings.generator_params
                    )
                    if not settings_match:
                        should_regenerate_preview = True
            case PreviewGenerationPolicy.ALWAYS:
                should_regenerate_preview = True
            case _:
                return GetPreviewForArtifactResultFailure(
                    result_details=f"Attempted to get preview for '{source_path}'. Failed due to: unknown policy '{request.preview_generation_policy}'"
                )

        # If regeneration needed, generate from defaults
        if should_regenerate_preview:
            generate_request = GeneratePreviewFromDefaultsRequest(
                macro_path=request.macro_path,
                artifact_provider_name=request.artifact_provider_name,
            )
            generate_result = await self.on_handle_generate_preview_from_defaults_request(generate_request)

            if isinstance(generate_result, GeneratePreviewFromDefaultsResultSuccess):
                return GetPreviewForArtifactResultSuccess(
                    result_details=f"Preview regenerated for '{source_path}'",
                    paths_to_preview=generate_result.paths_to_preview,
                )
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to regenerate preview for '{source_path}'. Failed due to: {generate_result.result_details}"
            )

        # Construct preview path(s) from metadata
        if isinstance(metadata.preview_file_names, str):
            paths_to_preview = str(destination_dir / metadata.preview_file_names)
        else:
            preview_file_paths = {}
            for key, filename in metadata.preview_file_names.items():
                preview_file_paths[key] = str(destination_dir / filename)
            paths_to_preview = preview_file_paths

        # SUCCESS PATH: Return path(s) to preview
        return GetPreviewForArtifactResultSuccess(
            result_details=f"Preview retrieved for '{source_path}'",
            paths_to_preview=paths_to_preview,
        )

    def on_handle_list_artifact_providers_request(
        self, _request: ListArtifactProvidersRequest
    ) -> ListArtifactProvidersResultSuccess | ListArtifactProvidersResultFailure:
        """Handle list artifact providers request."""
        friendly_names = [
            provider_class.get_friendly_name() for provider_class in self._registry.get_all_provider_classes()
        ]

        return ListArtifactProvidersResultSuccess(
            result_details="Successfully listed artifact providers", friendly_names=friendly_names
        )

    def on_handle_get_artifact_provider_details_request(
        self, request: GetArtifactProviderDetailsRequest
    ) -> GetArtifactProviderDetailsResultSuccess | GetArtifactProviderDetailsResultFailure:
        """Handle get artifact provider details request."""
        # FAILURE CASE: Provider not found
        provider_class = self._registry.get_provider_class_by_friendly_name(request.friendly_name)
        if provider_class is None:
            return GetArtifactProviderDetailsResultFailure(
                result_details=f"Attempted to get artifact provider details for '{request.friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # SUCCESS PATH: Return provider details with registered generators from registry
        preview_generators = self._registry.get_preview_generators_for_provider(provider_class)
        preview_generator_names = [gen.get_friendly_name() for gen in preview_generators]
        return GetArtifactProviderDetailsResultSuccess(
            result_details="Successfully retrieved artifact provider details",
            friendly_name=provider_class.get_friendly_name(),
            supported_formats=provider_class.get_supported_formats(),
            preview_formats=provider_class.get_preview_formats(),
            registered_preview_generators=preview_generator_names,
        )

    def on_handle_register_artifact_provider_request(
        self, request: RegisterArtifactProviderRequest
    ) -> RegisterArtifactProviderResultSuccess | RegisterArtifactProviderResultFailure:
        """Handle artifact provider registration request.

        Args:
            request: The registration request containing the provider class

        Returns:
            Success or failure result
        """
        provider_class = request.provider_class

        # FAILURE CASE: Try to register provider
        try:
            self._registry.register_provider(provider_class)
            self._register_provider_settings(provider_class)
        except Exception as e:
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider {provider_class.__name__}. Failed due to: {e}"
            )

        # SUCCESS PATH: Provider registered
        # NOTE: Provider is NOT instantiated here - lazy instantiation happens on first use
        return RegisterArtifactProviderResultSuccess(result_details="Artifact provider registered successfully")

    def on_handle_register_preview_generator_request(
        self, request: RegisterPreviewGeneratorRequest
    ) -> RegisterPreviewGeneratorResultSuccess | RegisterPreviewGeneratorResultFailure:
        """Handle preview generator registration request.

        Args:
            request: The registration request containing provider and generator info

        Returns:
            Success or failure result
        """
        # FAILURE CASE: Provider not found
        provider_class = self._registry.get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # FAILURE CASE: Generator registration failed
        try:
            # Register with registry (no provider instantiation - lazy instantiation preserved)
            self._registry.register_preview_generator_with_provider(provider_class, request.preview_generator_class)

            # Register generator settings using static method (no provider instantiation)
            from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
                BaseArtifactProvider,
            )

            config_schema = BaseArtifactProvider.get_preview_generator_config_schema(
                provider_class, request.preview_generator_class
            )
            for key, default_value in config_schema.items():
                SetConfigValueRequest(category_and_key=key, value=default_value)
                # GriptapeNodes.handle_request(request) TODO: Add back after https://github.com/griptape-ai/griptape-nodes/issues/3931
        except Exception as e:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: {e}"
            )

        # SUCCESS PATH: Generator registered
        generator_name = request.preview_generator_class.get_friendly_name()
        return RegisterPreviewGeneratorResultSuccess(
            result_details=f"Preview generator '{generator_name}' registered successfully"
        )

    def on_handle_list_preview_generators_request(
        self, request: ListPreviewGeneratorsRequest
    ) -> ListPreviewGeneratorsResultSuccess | ListPreviewGeneratorsResultFailure:
        """Handle list preview generators request.

        Args:
            request: The request containing the provider friendly name

        Returns:
            Success or failure result
        """
        # FAILURE CASE: Provider not found
        provider_class = self._registry.get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return ListPreviewGeneratorsResultFailure(
                result_details=f"Attempted to list preview generators for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # SUCCESS PATH: Return generator list from registry
        preview_generators = self._registry.get_preview_generators_for_provider(provider_class)
        preview_generator_names = [gen.get_friendly_name() for gen in preview_generators]
        return ListPreviewGeneratorsResultSuccess(
            result_details="Successfully listed preview generators",
            preview_generator_names=preview_generator_names,
        )

    def on_handle_get_preview_generator_details_request(
        self, request: GetPreviewGeneratorDetailsRequest
    ) -> GetPreviewGeneratorDetailsResultSuccess | GetPreviewGeneratorDetailsResultFailure:
        """Handle get preview generator details request.

        Args:
            request: The request containing provider and generator friendly names

        Returns:
            Success or failure result
        """
        # FAILURE CASE: Provider not found
        provider_class = self._registry.get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return GetPreviewGeneratorDetailsResultFailure(
                result_details=f"Attempted to get preview generator details for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # FAILURE CASE: Generator not found
        generator_class = self._registry.get_preview_generator_by_name(
            provider_class, request.preview_generator_friendly_name
        )
        if generator_class is None:
            return GetPreviewGeneratorDetailsResultFailure(
                result_details=f"Attempted to get preview generator details for '{request.preview_generator_friendly_name}' "
                f"in provider '{request.provider_friendly_name}'. Failed due to: generator not found"
            )

        # FAILURE CASE: Generator metadata access failed
        try:
            friendly_name = generator_class.get_friendly_name()
            source_formats = generator_class.get_supported_source_formats()
            preview_formats = generator_class.get_supported_preview_formats()
            parameters = generator_class.get_parameters()
        except Exception as e:
            return GetPreviewGeneratorDetailsResultFailure(
                result_details=f"Attempted to get preview generator details for '{request.preview_generator_friendly_name}' "
                f"in provider '{request.provider_friendly_name}'. Failed due to: metadata access error - {e}"
            )

        # Convert ProviderValue to tuple for serialization
        parameters_dict = {name: (pv.default_value, pv.required) for name, pv in parameters.items()}

        # SUCCESS PATH: Return generator details
        return GetPreviewGeneratorDetailsResultSuccess(
            result_details="Successfully retrieved preview generator details",
            friendly_name=friendly_name,
            supported_source_formats=source_formats,
            supported_preview_formats=preview_formats,
            parameters=parameters_dict,
        )

    def get_artifact_schemas(self) -> dict:
        """Generate artifact configuration schemas for all registered providers.

        NO INSTANTIATION: Uses static methods and registry tracking to avoid loading heavyweight dependencies.

        Returns detailed schema information including:
        - Enum values for format and generator dropdowns
        - Type information for generator parameters
        - Default values and descriptions

        Returns:
            Dictionary mapping provider keys to their schemas
        """
        schemas = {}

        for provider_class in self._registry.get_all_provider_classes():
            provider_friendly_name = provider_class.get_friendly_name()
            provider_key = provider_friendly_name.lower().replace(" ", "_")

            provider_formats = sorted(provider_class.get_preview_formats())
            default_format = provider_class.get_default_preview_format()
            default_preview_generator_name = provider_class.get_default_preview_generator()

            preview_generator_names = []
            preview_generator_schemas = {}

            # Get preview generators from registry without instantiation
            for preview_generator_class in self._registry.get_preview_generators_for_provider(provider_class):
                preview_generator_friendly_name = preview_generator_class.get_friendly_name()
                preview_generator_key = preview_generator_friendly_name.lower().replace(" ", "_")
                preview_generator_names.append(preview_generator_friendly_name)

                parameters = preview_generator_class.get_parameters()
                param_schemas = {}
                for param_name, provider_value in parameters.items():
                    param_schemas[param_name] = {
                        "type": provider_value.json_schema_type,
                        "default": provider_value.default_value,
                        "description": provider_value.description,
                    }

                preview_generator_schemas[preview_generator_key] = param_schemas

            schemas[provider_key] = {
                "preview_generation": {
                    "preview_format": {
                        "type": "string",
                        "enum": provider_formats,
                        "default": default_format,
                        "description": f"{provider_friendly_name} format for generated previews",
                    },
                    "preview_generator": {
                        "type": "string",
                        "enum": sorted(preview_generator_names),
                        "default": default_preview_generator_name,
                        "description": "Preview generator to use for creating previews",
                    },
                    "preview_generator_configurations": preview_generator_schemas,
                }
            }

        return schemas

    def _register_provider_settings(self, provider_class: type) -> None:
        """Register provider settings and default generators in config system.

        Args:
            provider_class: The provider class to register settings for

        Note:
            Default generators are registered WITHOUT instantiating the provider (lazy instantiation).
            Generator settings are registered statically using class methods.
        """
        # Register provider-level settings
        config_schema = self._registry.get_provider_config_schema(provider_class)

        for key, default_value in config_schema.items():
            SetConfigValueRequest(category_and_key=key, value=default_value)
            # GriptapeNodes.handle_request(request) TODO: Add back after https://github.com/griptape-ai/griptape-nodes/issues/3931

        # Register default preview generators and their settings WITHOUT instantiating provider
        for preview_generator_class in provider_class.get_default_generators():
            # Register with registry
            self._registry.register_preview_generator_with_provider(provider_class, preview_generator_class)

            # Register generator settings using static method (no provider instantiation)
            from griptape_nodes.retained_mode.managers.artifact_providers.base_artifact_provider import (
                BaseArtifactProvider,
            )

            config_schema = BaseArtifactProvider.get_preview_generator_config_schema(
                provider_class, preview_generator_class
            )
            for key, default_value in config_schema.items():
                SetConfigValueRequest(category_and_key=key, value=default_value)
                # GriptapeNodes.handle_request(request) TODO: Add back after https://github.com/griptape-ai/griptape-nodes/issues/3931

    def _get_default_params_for_generator(self, generator_class: type[BaseArtifactPreviewGenerator]) -> dict[str, Any]:
        """Get default parameter values for a preview generator.

        Args:
            generator_class: The generator class to get default parameters for

        Returns:
            Dictionary of parameter names to default values
        """
        parameters = generator_class.get_parameters()
        default_params = {}
        for param_name, provider_value in parameters.items():
            default_params[param_name] = provider_value.default_value
        return default_params

    def _get_preview_settings_from_config(
        self, provider_class: type[BaseArtifactProvider], provider_name: str
    ) -> PreviewSettings:
        """Read preview settings from config with intelligent fallback.

        NO VALIDATION - just reads config and falls back to defaults if missing.
        Prevents "half-valid" states by checking if generator is registered.

        Args:
            provider_class: The provider class
            provider_name: The provider friendly name (for logging)

        Returns:
            PreviewSettings object containing format, generator_name, and generator_params
            - All values are from config OR defaults, never mixed
            - Provider's generate_preview() will validate these values
        """
        # Step 1: Read format from config (or use default if missing)
        format_config_key = provider_class.get_preview_format_config_key()
        format_request = GetConfigValueRequest(category_and_key=format_config_key)
        format_result = GriptapeNodes.handle_request(format_request)

        if isinstance(format_result, GetConfigValueResultSuccess):
            # Config exists - use it (provider will validate later)
            preview_format = format_result.value
        else:
            # Config missing - use default
            preview_format = provider_class.get_default_preview_format()

        # Step 2: Read generator from config (or use default if missing/invalid)
        generator_config_key = provider_class.get_preview_generator_config_key()
        generator_request = GetConfigValueRequest(category_and_key=generator_config_key)
        generator_result = GriptapeNodes.handle_request(generator_request)

        registered_generators = self._registry.get_preview_generators_for_provider(provider_class)
        registered_generator_names = [gen.get_friendly_name() for gen in registered_generators]

        generator_from_config_is_registered = False
        if isinstance(generator_result, GetConfigValueResultSuccess):
            user_generator = generator_result.value

            if user_generator in registered_generator_names:
                # Config exists and generator is registered - use it
                generator_name = user_generator
                generator_from_config_is_registered = True
            else:
                # Config exists but generator NOT registered - fall back to default
                logger.warning(
                    "Config preview generator '%s' not registered with provider '%s'. "
                    "Falling back to default generator and default parameters.",
                    user_generator,
                    provider_name,
                )
                generator_name = provider_class.get_default_preview_generator()
        else:
            # Config missing - use default
            generator_name = provider_class.get_default_preview_generator()

        # Step 3: Read params (only if generator from config was registered)
        if generator_from_config_is_registered:
            # Generator from config is valid - read its params from config
            generator_key = generator_name.lower().replace(" ", "_")
            params_config_key = (
                f"{provider_class.get_config_key_prefix()}.preview_generator_configurations.{generator_key}"
            )
            params_request = GetConfigValueRequest(category_and_key=params_config_key)
            params_result = GriptapeNodes.handle_request(params_request)

            if isinstance(params_result, GetConfigValueResultSuccess):
                # Params exist in config - use them (provider will validate later)
                generator_params = params_result.value
            else:
                # Params missing from config - use defaults for this generator
                generator_class = self._registry.get_preview_generator_by_name(provider_class, generator_name)
                if generator_class is None:
                    msg = f"Generator '{generator_name}' not found in registry but was validated as registered"
                    raise RuntimeError(msg)
                generator_params = self._get_default_params_for_generator(generator_class)
        else:
            # Generator from config was invalid OR missing - use default params
            # This prevents "half-valid" states (user's params with default generator)
            generator_class = self._registry.get_preview_generator_by_name(provider_class, generator_name)
            if generator_class is None:
                msg = f"Default generator '{generator_name}' not found in registry but provider claims it as default"
                raise RuntimeError(msg)
            generator_params = self._get_default_params_for_generator(generator_class)

        # Return all settings (provider will validate them)
        return PreviewSettings(
            format=preview_format,
            generator_name=generator_name,
            generator_params=generator_params,
        )

    def _is_preview_source_stale(
        self,
        metadata: PreviewMetadata,
        source_size: int,
        source_mtime: float,
    ) -> bool:
        """Check if preview source file has changed since generation.

        Args:
            metadata: Preview metadata containing stored source file info
            source_size: Current size of source file in bytes
            source_mtime: Current modification time of source file

        Returns:
            True if source file has changed (stale), False otherwise
        """
        return metadata.source_file_size != source_size or metadata.source_file_modified_time != source_mtime

    def _does_preview_match_current_settings(
        self,
        metadata: PreviewMetadata,
        current_generator_name: str,
        current_generator_params: dict[str, Any],
    ) -> bool:
        """Check if preview was generated with current generator settings.

        Args:
            metadata: Preview metadata containing stored generator info
            current_generator_name: Current generator name from config
            current_generator_params: Current generator parameters from config

        Returns:
            True if settings match, False otherwise
        """
        return (
            metadata.preview_generator_name == current_generator_name
            and metadata.preview_generator_parameters == current_generator_params
        )
