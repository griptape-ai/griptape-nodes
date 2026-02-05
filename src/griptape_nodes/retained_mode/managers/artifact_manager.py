"""Manager for artifact operations."""

import json
import logging
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from griptape_nodes.retained_mode.events.artifact_events import (
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
    RegisterArtifactProviderRequest,
    RegisterArtifactProviderResultFailure,
    RegisterArtifactProviderResultSuccess,
    RegisterPreviewGeneratorRequest,
    RegisterPreviewGeneratorResultFailure,
    RegisterPreviewGeneratorResultSuccess,
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
        preview_file_name: Name of the preview file (without path)
    """

    LATEST_SCHEMA_VERSION: ClassVar[str] = "0.1.0"

    version: str
    source_macro_path: str
    source_file_size: int
    source_file_modified_time: float
    preview_file_name: str


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

        # Register default providers (order matters: Image, Video, Audio)
        failures = []
        for provider_class in [ImageArtifactProvider]:
            try:
                self._registry.register_provider(provider_class)
            except Exception as e:
                provider_name = provider_class.__name__
                failures.append(f"{provider_name}: {e}")

        if failures:
            failure_details = "; ".join(failures)
            error_message = (
                f"Attempted to register default artifact providers during initialization. "
                f"Failed due to: {failure_details}"
            )
            raise RuntimeError(error_message)

    async def on_handle_generate_preview_request(  # noqa: PLR0911, C901, PLR0912
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
        # Build preview filename once, then construct full path
        preview_file_name = f"{source_path_obj.name}.{preview_format}"
        destination_preview_file_path = str(destination_dir / preview_file_name)

        # FAILURE CASE: Call provider.generate_preview()
        try:
            await provider_instance.generate_preview(
                preview_generator_friendly_name=generator_name,
                source_file_location=source_path,
                preview_format=preview_format,
                destination_preview_file_location=destination_preview_file_path,
                params=request.preview_generator_parameters,
            )
        except Exception as e:
            return GeneratePreviewResultFailure(
                result_details=f"Attempted to generate preview for '{source_path}'. Failed due to: {e}"
            )

        # OPTIONAL: Generate metadata if requested
        metadata_path = None
        if request.generate_preview_metadata_json:
            # Helper to clean up preview file on metadata failure
            def fail_with_cleanup(error_details: str) -> GeneratePreviewResultFailure:
                delete_request = DeleteFileRequest(path=destination_preview_file_path, workspace_only=False)
                delete_result = GriptapeNodes.handle_request(delete_request)

                if delete_result.failed():
                    error_details += f". Additionally, failed to delete preview file: {delete_result.result_details}"

                return GeneratePreviewResultFailure(result_details=error_details)

            # Step 1: Create metadata object
            metadata = PreviewMetadata(
                version=PreviewMetadata.LATEST_SCHEMA_VERSION,
                source_macro_path=request.macro_path.parsed_macro.template,
                source_file_size=file_info_result.file_entry.size,
                source_file_modified_time=file_info_result.file_entry.modified_time,
                preview_file_name=preview_file_name,
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

        # SUCCESS PATH: Build result message
        result_message = f"Successfully generated preview of {source_path}. Preview at {destination_preview_file_path}"
        if metadata_path is not None:
            result_message += f". Metadata at {metadata_path}"

        return GeneratePreviewResultSuccess(result_details=result_message)

    def on_handle_get_preview_for_artifact_request(  # noqa: PLR0911
        self, request: GetPreviewForArtifactRequest
    ) -> GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure:
        """Handle get preview for artifact request.

        Args:
            request: Contains macro_path and generate_preview_if_necessary flag

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

        # Calculate metadata path
        source_path_obj = Path(source_path)
        destination_dir = source_path_obj.parent / "nodes_previews"
        metadata_path = str(destination_dir / f"{source_path_obj.name}.json")

        # FAILURE CASE: Check if metadata file exists
        metadata_info_request = GetFileInfoRequest(path=metadata_path, workspace_only=False)
        metadata_info_result = GriptapeNodes.handle_request(metadata_info_request)

        if not isinstance(metadata_info_result, GetFileInfoResultSuccess) or metadata_info_result.file_entry is None:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Failed due to: metadata file not found at '{metadata_path}'"
            )

        # FAILURE CASE: Read metadata file
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

        # FAILURE CASE: Parse and validate metadata using Pydantic
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

        # FAILURE CASE: Validate preview is fresh (source hasn't changed)
        source_size = file_info_result.file_entry.size
        source_mtime = file_info_result.file_entry.modified_time

        if metadata.source_file_size != source_size or metadata.source_file_modified_time != source_mtime:
            return GetPreviewForArtifactResultFailure(
                result_details=(
                    f"Attempted to get preview for '{source_path}'. "
                    f"Preview metadata exists but is stale (source file modified since preview generation). "
                    f"Please regenerate the preview."
                )
            )

        # Construct preview path from metadata
        preview_file_path = str(destination_dir / metadata.preview_file_name)

        # FAILURE CASE: Verify preview file actually exists
        preview_info_request = GetFileInfoRequest(path=preview_file_path, workspace_only=False)
        preview_info_result = GriptapeNodes.handle_request(preview_info_request)

        if not isinstance(preview_info_result, GetFileInfoResultSuccess) or preview_info_result.file_entry is None:
            return GetPreviewForArtifactResultFailure(
                result_details=f"Attempted to get preview for '{source_path}'. Metadata indicates preview at '{preview_file_path}' but file not found"
            )

        # SUCCESS PATH: Return absolute path to preview
        return GetPreviewForArtifactResultSuccess(
            result_details=f"Found preview for '{source_path}' at '{preview_file_path}'",
            path_to_preview=preview_file_path,
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

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._registry.get_or_create_provider_instance(provider_class)
        except Exception as e:
            return GetArtifactProviderDetailsResultFailure(
                result_details=f"Attempted to get artifact provider details for '{request.friendly_name}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # SUCCESS PATH: Return provider details with registered generators
        return GetArtifactProviderDetailsResultSuccess(
            result_details="Successfully retrieved artifact provider details",
            friendly_name=provider_class.get_friendly_name(),
            supported_formats=provider_class.get_supported_formats(),
            preview_formats=provider_class.get_preview_formats(),
            registered_preview_generators=provider_instance.get_registered_preview_generators(),
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
        except Exception as e:
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider {provider_class.__name__}. Failed due to: {e}"
            )

        # SUCCESS PATH: Provider registered
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

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._registry.get_or_create_provider_instance(provider_class)
        except Exception as e:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # FAILURE CASE: Generator registration failed
        try:
            provider_instance.register_preview_generator(request.preview_generator_class)
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

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._registry.get_or_create_provider_instance(provider_class)
        except Exception as e:
            return ListPreviewGeneratorsResultFailure(
                result_details=f"Attempted to list preview generators for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # SUCCESS PATH: Return generator list
        return ListPreviewGeneratorsResultSuccess(
            result_details="Successfully listed preview generators",
            preview_generator_names=provider_instance.get_registered_preview_generators(),
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

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._registry.get_or_create_provider_instance(provider_class)
        except Exception as e:
            return GetPreviewGeneratorDetailsResultFailure(
                result_details=f"Attempted to get preview generator details for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # FAILURE CASE: Generator not found
        generator_class = provider_instance._get_preview_generator_by_name(request.preview_generator_friendly_name)
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
