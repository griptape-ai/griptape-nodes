import pytest

from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.artifact_events import (
    GetArtifactProviderDetailsRequest,
    GetArtifactProviderDetailsResultFailure,
    GetArtifactProviderDetailsResultSuccess,
    ListArtifactProvidersRequest,
    ListArtifactProvidersResultSuccess,
    RegisterArtifactProviderRequest,
    RegisterArtifactProviderResultFailure,
    RegisterArtifactProviderResultSuccess,
)
from griptape_nodes.retained_mode.managers.artifact_manager import ArtifactManager
from griptape_nodes.retained_mode.managers.default_artifact_providers import (
    BaseArtifactProvider,
    ImageArtifactProvider,
)


class TestArtifactManager:
    """Test ArtifactManager functionality."""

    def test_init_creates_empty_providers(self) -> None:
        """Test that initialization creates empty provider collections."""
        manager = ArtifactManager()

        assert isinstance(manager._providers, set)
        assert len(manager._providers) == 0
        assert isinstance(manager._file_format_to_provider, dict)
        assert len(manager._file_format_to_provider) == 0

    def test_register_image_provider_success(self) -> None:
        """Test successful registration of ImageArtifactProvider."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)

        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultSuccess)
        assert len(manager._providers) == 1
        assert "jpg" in manager._file_format_to_provider
        assert "png" in manager._file_format_to_provider

    def test_register_provider_adds_to_providers_set(self) -> None:
        """Test that registered provider is added to _providers set."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)

        manager.on_handle_register_artifact_provider_request(request)

        assert len(manager._providers) == 1
        provider = next(iter(manager._providers))
        assert isinstance(provider, ImageArtifactProvider)

    def test_register_provider_maps_all_supported_formats(self) -> None:
        """Test that all supported formats are mapped to provider."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)

        manager.on_handle_register_artifact_provider_request(request)

        image_formats = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif"}
        for file_format in image_formats:
            assert file_format in manager._file_format_to_provider
            assert len(manager._file_format_to_provider[file_format]) == 1
            assert isinstance(manager._file_format_to_provider[file_format][0], ImageArtifactProvider)

    def test_register_provider_failure_returns_failure_result(self) -> None:
        """Test that registration failure returns RegisterArtifactProviderResultFailure."""

        class BrokenProvider(BaseArtifactProvider):
            def __init__(self) -> None:
                msg = "Intentional failure"
                raise ValueError(msg)

            @property
            def friendly_name(self) -> str:
                return "Broken"

            @property
            def supported_formats(self) -> set[str]:
                return {"broken"}

            @property
            def preview_formats(self) -> set[str]:
                return {"broken"}

        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=BrokenProvider)

        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultFailure)
        assert "BrokenProvider" in str(result.result_details)
        assert "instantiation error" in str(result.result_details)

    def test_app_initialization_registers_default_providers(self) -> None:
        """Test that AppInitializationComplete registers default providers."""
        manager = ArtifactManager()
        event = AppInitializationComplete()

        manager.on_app_initialization_complete(event)

        assert len(manager._providers) == 1
        assert "jpg" in manager._file_format_to_provider

    def test_app_initialization_with_failure_raises_runtime_error(self) -> None:
        """Test that provider registration failure raises RuntimeError."""

        class BrokenProvider(BaseArtifactProvider):
            def __init__(self) -> None:
                msg = "Intentional failure"
                raise ValueError(msg)

            @property
            def friendly_name(self) -> str:
                return "Broken"

            @property
            def supported_formats(self) -> set[str]:
                return {"broken"}

            @property
            def preview_formats(self) -> set[str]:
                return {"broken"}

        def trigger_registration_failure() -> None:
            manager = ArtifactManager()
            request = RegisterArtifactProviderRequest(provider_class=BrokenProvider)
            result = manager.on_handle_register_artifact_provider_request(request)
            if result.failed():
                failures = [f"BrokenProvider: {result.result_details}"]
                failure_details = "; ".join(failures)
                error_message = (
                    "Attempted to register default artifact providers during app initialization. "
                    f"Failed due to: {failure_details}"
                )
                raise RuntimeError(error_message)

        with pytest.raises(RuntimeError) as exc_info:
            trigger_registration_failure()

        assert "BrokenProvider" in str(exc_info.value)
        assert "instantiation error" in str(exc_info.value)

    def test_multiple_providers_can_handle_same_format(self) -> None:
        """Test that multiple providers can be registered for the same format."""

        class AlternateImageProvider(BaseArtifactProvider):
            @property
            def friendly_name(self) -> str:
                return "AlternateImage"

            @property
            def supported_formats(self) -> set[str]:
                return {"jpg", "png"}

            @property
            def preview_formats(self) -> set[str]:
                return {"webp"}

        manager = ArtifactManager()
        request1 = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        request2 = RegisterArtifactProviderRequest(provider_class=AlternateImageProvider)

        manager.on_handle_register_artifact_provider_request(request1)
        manager.on_handle_register_artifact_provider_request(request2)

        expected_provider_count = 2
        assert len(manager._providers) == expected_provider_count
        assert len(manager._file_format_to_provider["jpg"]) == expected_provider_count
        assert len(manager._file_format_to_provider["png"]) == expected_provider_count

    def test_duplicate_friendly_name_fails_registration(self) -> None:
        """Test that registering a provider with duplicate friendly name fails."""

        class DuplicateImageProvider(BaseArtifactProvider):
            @property
            def friendly_name(self) -> str:
                return "Image"

            @property
            def supported_formats(self) -> set[str]:
                return {"bmp"}

            @property
            def preview_formats(self) -> set[str]:
                return {"jpg"}

        manager = ArtifactManager()
        request1 = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        request2 = RegisterArtifactProviderRequest(provider_class=DuplicateImageProvider)

        result1 = manager.on_handle_register_artifact_provider_request(request1)
        result2 = manager.on_handle_register_artifact_provider_request(request2)

        assert isinstance(result1, RegisterArtifactProviderResultSuccess)
        assert isinstance(result2, RegisterArtifactProviderResultFailure)
        assert "duplicate friendly name" in str(result2.result_details)
        assert "Image" in str(result2.result_details)

    def test_duplicate_friendly_name_case_insensitive(self) -> None:
        """Test that friendly name duplicate detection is case-insensitive."""

        class LowercaseImageProvider(BaseArtifactProvider):
            @property
            def friendly_name(self) -> str:
                return "image"

            @property
            def supported_formats(self) -> set[str]:
                return {"bmp"}

            @property
            def preview_formats(self) -> set[str]:
                return {"jpg"}

        manager = ArtifactManager()
        request1 = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        request2 = RegisterArtifactProviderRequest(provider_class=LowercaseImageProvider)

        manager.on_handle_register_artifact_provider_request(request1)
        result2 = manager.on_handle_register_artifact_provider_request(request2)

        assert isinstance(result2, RegisterArtifactProviderResultFailure)
        assert "duplicate friendly name" in str(result2.result_details)

    def test_get_provider_by_friendly_name_case_insensitive(self) -> None:
        """Test that _get_provider_by_friendly_name is case-insensitive."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        manager.on_handle_register_artifact_provider_request(request)

        provider_lower = manager._get_provider_by_friendly_name("image")
        provider_title = manager._get_provider_by_friendly_name("Image")
        provider_upper = manager._get_provider_by_friendly_name("IMAGE")
        provider_missing = manager._get_provider_by_friendly_name("Video")

        assert provider_lower is not None
        assert provider_title is not None
        assert provider_upper is not None
        assert provider_lower is provider_title
        assert provider_title is provider_upper
        assert isinstance(provider_lower, ImageArtifactProvider)
        assert provider_missing is None

    def test_list_artifact_providers_returns_friendly_names(self) -> None:
        """Test that ListArtifactProvidersRequest returns list of friendly names."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        manager.on_handle_register_artifact_provider_request(request)

        list_request = ListArtifactProvidersRequest()
        result = manager.on_handle_list_artifact_providers_request(list_request)

        assert isinstance(result, ListArtifactProvidersResultSuccess)
        assert len(result.friendly_names) == 1
        assert "Image" in result.friendly_names

    def test_get_artifact_provider_details_success(self) -> None:
        """Test that GetArtifactProviderDetailsRequest returns provider details."""
        manager = ArtifactManager()
        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        manager.on_handle_register_artifact_provider_request(request)

        details_request = GetArtifactProviderDetailsRequest(friendly_name="image")
        result = manager.on_handle_get_artifact_provider_details_request(details_request)

        assert isinstance(result, GetArtifactProviderDetailsResultSuccess)
        assert result.friendly_name == "Image"
        assert "jpg" in result.supported_formats
        assert "png" in result.supported_formats
        assert "webp" in result.preview_formats

    def test_get_artifact_provider_details_not_found(self) -> None:
        """Test that GetArtifactProviderDetailsRequest fails when provider not found."""
        manager = ArtifactManager()

        details_request = GetArtifactProviderDetailsRequest(friendly_name="Video")
        result = manager.on_handle_get_artifact_provider_details_request(details_request)

        assert isinstance(result, GetArtifactProviderDetailsResultFailure)
        assert "provider not found" in str(result.result_details)
        assert "Video" in str(result.result_details)
