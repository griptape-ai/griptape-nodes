"""Manager for artifact operations."""

import logging

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
    ListArtifactProvidersRequest,
    ListArtifactProvidersResultFailure,
    ListArtifactProvidersResultSuccess,
    RegisterArtifactProviderRequest,
    RegisterArtifactProviderResultFailure,
    RegisterArtifactProviderResultSuccess,
)
from griptape_nodes.retained_mode.managers.default_artifact_providers import (
    BaseArtifactProvider,
    ImageArtifactProvider,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


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

        # The list of classes we have registered
        self._provider_classes: list[type[BaseArtifactProvider]] = []

        # INSTANTIATIONS of these classes (lazy instantiated to limit headless execution overhead)
        self._provider_instances: dict[type[BaseArtifactProvider], BaseArtifactProvider] = {}

        # Map of source file type to provider class
        self._file_format_to_provider_class: dict[str, list[type[BaseArtifactProvider]]] = {}

        # Map of friendly name to provider class
        self._friendly_name_to_provider_class: dict[str, type[BaseArtifactProvider]] = {}

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

        # Register default providers (order matters: Image, Video, Audio)
        failures = []
        for provider_class in [ImageArtifactProvider]:
            request = RegisterArtifactProviderRequest(provider_class=provider_class)
            result = self.on_handle_register_artifact_provider_request(request)

            if result.failed():
                provider_name = provider_class.__name__
                failures.append(f"{provider_name}: {result.result_details}")

        if failures:
            failure_details = "; ".join(failures)
            error_message = (
                f"Attempted to register default artifact providers during initialization. "
                f"Failed due to: {failure_details}"
            )
            raise RuntimeError(error_message)

    def on_handle_generate_preview_request(
        self, _request: GeneratePreviewRequest
    ) -> GeneratePreviewResultSuccess | GeneratePreviewResultFailure:
        """Handle generate preview request."""
        return GeneratePreviewResultFailure(result_details="Not implemented yet")

    def on_handle_get_preview_for_artifact_request(
        self, _request: GetPreviewForArtifactRequest
    ) -> GetPreviewForArtifactResultSuccess | GetPreviewForArtifactResultFailure:
        """Handle get preview for artifact request."""
        return GetPreviewForArtifactResultFailure(result_details="Not implemented yet")

    def on_handle_list_artifact_providers_request(
        self, _request: ListArtifactProvidersRequest
    ) -> ListArtifactProvidersResultSuccess | ListArtifactProvidersResultFailure:
        """Handle list artifact providers request."""
        friendly_names = [provider_class.get_friendly_name() for provider_class in self._provider_classes]

        return ListArtifactProvidersResultSuccess(
            result_details="Successfully listed artifact providers", friendly_names=friendly_names
        )

    def on_handle_get_artifact_provider_details_request(
        self, request: GetArtifactProviderDetailsRequest
    ) -> GetArtifactProviderDetailsResultSuccess | GetArtifactProviderDetailsResultFailure:
        """Handle get artifact provider details request."""
        # FAILURE CASE: Provider not found
        provider_class = self._get_provider_class_by_friendly_name(request.friendly_name)
        if provider_class is None:
            return GetArtifactProviderDetailsResultFailure(
                result_details=f"Attempted to get artifact provider details for '{request.friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # SUCCESS PATH: Return provider details
        return GetArtifactProviderDetailsResultSuccess(
            result_details="Successfully retrieved artifact provider details",
            friendly_name=provider_class.get_friendly_name(),
            supported_formats=provider_class.get_supported_formats(),
            preview_formats=provider_class.get_preview_formats(),
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
        provider_name = provider_class.__name__

        # FAILURE CASE: Try to access class methods
        try:
            friendly_name = provider_class.get_friendly_name()
            supported_formats = provider_class.get_supported_formats()
        except Exception as e:
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider {provider_name}. "
                f"Failed due to: class method access error - {e}"
            )

        # FAILURE CASE: Check for duplicate friendly name
        friendly_name_lower = friendly_name.lower()
        if friendly_name_lower in self._friendly_name_to_provider_class:
            existing_provider_class = self._friendly_name_to_provider_class[friendly_name_lower]
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider '{friendly_name}' ({provider_name}). "
                f"Failed due to: duplicate friendly name with existing provider ({existing_provider_class.__name__})"
            )

        # SUCCESS PATH: Register provider class
        self._provider_classes.append(provider_class)

        for file_format in supported_formats:
            if file_format not in self._file_format_to_provider_class:
                self._file_format_to_provider_class[file_format] = []
            self._file_format_to_provider_class[file_format].append(provider_class)

        self._friendly_name_to_provider_class[friendly_name_lower] = provider_class

        return RegisterArtifactProviderResultSuccess(result_details="Artifact provider registered successfully")

    def _get_provider_class_by_friendly_name(self, friendly_name: str) -> type[BaseArtifactProvider] | None:
        """Get provider class by friendly name (case-insensitive).

        Args:
            friendly_name: The friendly name to search for

        Returns:
            The provider class if found, None otherwise
        """
        return self._friendly_name_to_provider_class.get(friendly_name.lower())

    def _get_or_create_provider_instance(self, provider_class: type[BaseArtifactProvider]) -> BaseArtifactProvider:
        """Get or create singleton instance of provider class.

        Args:
            provider_class: The provider class to instantiate

        Returns:
            Cached singleton instance of the provider

        Raises:
            Exception: If provider instantiation fails
        """
        if provider_class not in self._provider_instances:
            # Not instantiated yet; lazily instantiate (or at least attempt to)
            try:
                self._provider_instances[provider_class] = provider_class()
            except Exception as e:
                logger.error("Failed to instantiate provider %s: %s", provider_class.__name__, e)
                raise
        return self._provider_instances[provider_class]
