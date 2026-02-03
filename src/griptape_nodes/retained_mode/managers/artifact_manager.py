"""Manager for artifact operations."""

import logging

from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
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
        self._providers: set[BaseArtifactProvider] = set()
        self._file_format_to_provider: dict[str, list[BaseArtifactProvider]] = {}
        self._friendly_name_to_provider: dict[str, BaseArtifactProvider] = {}

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
            event_manager.add_listener_to_app_event(AppInitializationComplete, self.on_app_initialization_complete)

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
        friendly_names = [provider.friendly_name for provider in self._providers]

        return ListArtifactProvidersResultSuccess(
            result_details="Successfully listed artifact providers", friendly_names=friendly_names
        )

    def on_handle_get_artifact_provider_details_request(
        self, request: GetArtifactProviderDetailsRequest
    ) -> GetArtifactProviderDetailsResultSuccess | GetArtifactProviderDetailsResultFailure:
        """Handle get artifact provider details request."""
        # FAILURE CASE: Provider not found
        provider = self._get_provider_by_friendly_name(request.friendly_name)
        if provider is None:
            return GetArtifactProviderDetailsResultFailure(
                result_details=f"Attempted to get artifact provider details for '{request.friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # SUCCESS PATH: Return provider details
        return GetArtifactProviderDetailsResultSuccess(
            result_details="Successfully retrieved artifact provider details",
            friendly_name=provider.friendly_name,
            supported_formats=provider.supported_formats,
            preview_formats=provider.preview_formats,
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
        provider_name = request.provider_class.__name__

        # FAILURE CASE: Try to instantiate provider
        try:
            provider = request.provider_class()
        except Exception as e:
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider {provider_name}. "
                f"Failed due to: instantiation error - {e}"
            )

        # FAILURE CASE: Check for duplicate friendly name
        friendly_name_lower = provider.friendly_name.lower()
        if friendly_name_lower in self._friendly_name_to_provider:
            return RegisterArtifactProviderResultFailure(
                result_details=f"Attempted to register artifact provider {provider_name}. "
                f"Failed due to: duplicate friendly name '{provider.friendly_name}'"
            )

        # SUCCESS PATH: Register provider for each supported format
        self._providers.add(provider)

        for file_format in provider.supported_formats:
            if file_format not in self._file_format_to_provider:
                self._file_format_to_provider[file_format] = []
            self._file_format_to_provider[file_format].append(provider)

        self._friendly_name_to_provider[friendly_name_lower] = provider

        return RegisterArtifactProviderResultSuccess(result_details="Artifact provider registered successfully")

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        """Handle app initialization complete event.

        Registers default artifact providers (Image).

        Args:
            _payload: The app initialization complete event payload
        """
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
                f"Attempted to register default artifact providers during app initialization. "
                f"Failed due to: {failure_details}"
            )
            raise RuntimeError(error_message)

    def _get_provider_by_friendly_name(self, friendly_name: str) -> BaseArtifactProvider | None:
        """Get provider by friendly name (case-insensitive).

        Args:
            friendly_name: The friendly name to search for

        Returns:
            The provider if found, None otherwise
        """
        return self._friendly_name_to_provider.get(friendly_name.lower())
