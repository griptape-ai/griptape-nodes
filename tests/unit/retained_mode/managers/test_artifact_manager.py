import pytest

from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.artifact_events import (
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
