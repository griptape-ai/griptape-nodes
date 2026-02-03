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
        """Test that initialization creates empty provider collections and registers defaults."""
        manager = ArtifactManager()

        assert isinstance(manager._provider_classes, list)
        assert len(manager._provider_classes) == 1
        assert isinstance(manager._file_format_to_provider_class, dict)
        assert len(manager._file_format_to_provider_class) > 0
        assert isinstance(manager._provider_instances, dict)
        assert len(manager._provider_instances) == 0

    def test_register_new_provider_success(self) -> None:
        """Test successful registration of a new provider."""

        class TestProvider(BaseArtifactProvider):
            @classmethod
            def get_friendly_name(cls) -> str:
                return "Test"

            @classmethod
            def get_supported_formats(cls) -> set[str]:
                return {"test", "tst"}

            @classmethod
            def get_preview_formats(cls) -> set[str]:
                return {"jpg"}

        manager = ArtifactManager()
        initial_count = len(manager._provider_classes)

        request = RegisterArtifactProviderRequest(provider_class=TestProvider)
        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultSuccess)
        assert len(manager._provider_classes) == initial_count + 1
        assert "test" in manager._file_format_to_provider_class
        assert "tst" in manager._file_format_to_provider_class

    def test_register_provider_adds_to_providers_list(self) -> None:
        """Test that registered provider class is added to _provider_classes list."""
        manager = ArtifactManager()

        request = RegisterArtifactProviderRequest(provider_class=ImageArtifactProvider)
        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultFailure)
        assert "duplicate friendly name" in str(result.result_details)

    def test_register_provider_maps_all_supported_formats(self) -> None:
        """Test that all supported formats are mapped to provider class."""
        manager = ArtifactManager()

        # ImageArtifactProvider is already registered in constructor
        image_formats = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif"}
        for file_format in image_formats:
            assert file_format in manager._file_format_to_provider_class
            assert len(manager._file_format_to_provider_class[file_format]) == 1
            assert manager._file_format_to_provider_class[file_format][0] is ImageArtifactProvider

    def test_initialization_registers_default_providers(self) -> None:
        """Test that ArtifactManager initialization registers default providers."""
        manager = ArtifactManager()

        assert len(manager._provider_classes) == 1
        assert "jpg" in manager._file_format_to_provider_class

    def test_multiple_providers_can_handle_same_format(self) -> None:
        """Test that multiple provider classes can be registered for the same format."""

        class AlternateImageProvider(BaseArtifactProvider):
            @classmethod
            def get_friendly_name(cls) -> str:
                return "AlternateImage"

            @classmethod
            def get_supported_formats(cls) -> set[str]:
                return {"jpg", "png"}

            @classmethod
            def get_preview_formats(cls) -> set[str]:
                return {"webp"}

        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor
        request = RegisterArtifactProviderRequest(provider_class=AlternateImageProvider)

        manager.on_handle_register_artifact_provider_request(request)

        expected_provider_count = 2
        assert len(manager._provider_classes) == expected_provider_count
        assert len(manager._file_format_to_provider_class["jpg"]) == expected_provider_count
        assert len(manager._file_format_to_provider_class["png"]) == expected_provider_count

    def test_duplicate_friendly_name_fails_registration(self) -> None:
        """Test that registering a provider class with duplicate friendly name fails."""

        class DuplicateImageProvider(BaseArtifactProvider):
            @classmethod
            def get_friendly_name(cls) -> str:
                return "Image"

            @classmethod
            def get_supported_formats(cls) -> set[str]:
                return {"bmp"}

            @classmethod
            def get_preview_formats(cls) -> set[str]:
                return {"jpg"}

        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor
        request = RegisterArtifactProviderRequest(provider_class=DuplicateImageProvider)

        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultFailure)
        assert "duplicate friendly name" in str(result.result_details)
        assert "Image" in str(result.result_details)

    def test_duplicate_friendly_name_case_insensitive(self) -> None:
        """Test that friendly name duplicate detection is case-insensitive."""

        class LowercaseImageProvider(BaseArtifactProvider):
            @classmethod
            def get_friendly_name(cls) -> str:
                return "image"

            @classmethod
            def get_supported_formats(cls) -> set[str]:
                return {"bmp"}

            @classmethod
            def get_preview_formats(cls) -> set[str]:
                return {"jpg"}

        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor
        request = RegisterArtifactProviderRequest(provider_class=LowercaseImageProvider)

        result = manager.on_handle_register_artifact_provider_request(request)

        assert isinstance(result, RegisterArtifactProviderResultFailure)
        assert "duplicate friendly name" in str(result.result_details)

    def test_get_provider_class_by_friendly_name_case_insensitive(self) -> None:
        """Test that _get_provider_class_by_friendly_name is case-insensitive."""
        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor

        provider_class_lower = manager._get_provider_class_by_friendly_name("image")
        provider_class_title = manager._get_provider_class_by_friendly_name("Image")
        provider_class_upper = manager._get_provider_class_by_friendly_name("IMAGE")
        provider_class_missing = manager._get_provider_class_by_friendly_name("Video")

        assert provider_class_lower is not None
        assert provider_class_title is not None
        assert provider_class_upper is not None
        assert provider_class_lower is provider_class_title
        assert provider_class_title is provider_class_upper
        assert provider_class_lower is ImageArtifactProvider
        assert provider_class_missing is None

    def test_lazy_instantiation_creates_singleton(self) -> None:
        """Test that _get_or_create_provider_instance creates and caches singleton."""
        manager = ArtifactManager()

        assert len(manager._provider_instances) == 0

        instance1 = manager._get_or_create_provider_instance(ImageArtifactProvider)
        assert isinstance(instance1, ImageArtifactProvider)
        assert len(manager._provider_instances) == 1

        instance2 = manager._get_or_create_provider_instance(ImageArtifactProvider)
        assert instance2 is instance1
        assert len(manager._provider_instances) == 1

    def test_list_artifact_providers_returns_friendly_names(self) -> None:
        """Test that ListArtifactProvidersRequest returns list of friendly names."""
        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor

        list_request = ListArtifactProvidersRequest()
        result = manager.on_handle_list_artifact_providers_request(list_request)

        assert isinstance(result, ListArtifactProvidersResultSuccess)
        assert len(result.friendly_names) == 1
        assert "Image" in result.friendly_names

    def test_get_artifact_provider_details_success(self) -> None:
        """Test that GetArtifactProviderDetailsRequest returns provider details."""
        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor

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
