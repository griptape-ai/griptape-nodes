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

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._get_or_create_provider_instance(provider_class)
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
        provider_class = self._get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._get_or_create_provider_instance(provider_class)
        except Exception as e:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider instantiation error - {e}"
            )

        # FAILURE CASE: Generator registration failed
        result = provider_instance.register_preview_generator(request.preview_generator_class)
        if not result.success:
            return RegisterPreviewGeneratorResultFailure(
                result_details=f"Attempted to register preview generator with provider '{request.provider_friendly_name}'. "
                f"Failed due to: {result.message}"
            )

        # SUCCESS PATH: Generator registered
        return RegisterPreviewGeneratorResultSuccess(result_details=result.message)

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
        provider_class = self._get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return ListPreviewGeneratorsResultFailure(
                result_details=f"Attempted to list preview generators for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._get_or_create_provider_instance(provider_class)
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
        provider_class = self._get_provider_class_by_friendly_name(request.provider_friendly_name)
        if provider_class is None:
            return GetPreviewGeneratorDetailsResultFailure(
                result_details=f"Attempted to get preview generator details for provider '{request.provider_friendly_name}'. "
                f"Failed due to: provider not found"
            )

        # FAILURE CASE: Provider instantiation failed
        try:
            provider_instance = self._get_or_create_provider_instance(provider_class)
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
