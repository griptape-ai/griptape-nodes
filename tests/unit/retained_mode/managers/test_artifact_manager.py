import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from PIL import Image

from griptape_nodes.common.macro_parser import ParsedMacro
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
    ListArtifactProvidersResultSuccess,
    RegisterArtifactProviderRequest,
    RegisterArtifactProviderResultFailure,
    RegisterArtifactProviderResultSuccess,
)
from griptape_nodes.retained_mode.events.project_events import MacroPath
from griptape_nodes.retained_mode.managers.artifact_manager import ArtifactManager, PreviewMetadata
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


class TestGeneratePreview:
    """Tests for preview generation functionality."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_image_path(self, temp_dir: Path) -> Path:
        """Create a real test image file for preview generation.

        Returns:
            Path to a 100x100 JPEG test image with known properties
        """
        image_path = temp_dir / "test_source.jpg"

        # Create a simple test image (100x100 red square)
        img = Image.new("RGB", (100, 100), color="red")
        img.save(str(image_path), format="JPEG")

        return image_path

    @pytest.fixture
    def test_macro_path(self, test_image_path: Path) -> MacroPath:
        """Create MacroPath for test image."""
        parsed_macro = ParsedMacro(str(test_image_path))
        return MacroPath(parsed_macro=parsed_macro, variables={})

    @pytest.fixture
    def artifact_manager(self) -> ArtifactManager:
        """Create ArtifactManager instance with ImageArtifactProvider registered."""
        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor
        return manager

    @pytest.mark.asyncio
    async def test_generate_preview_without_metadata_success(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test generating preview without metadata."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=False,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Verify preview file exists
        preview_dir = test_image_path.parent / "nodes_previews"
        preview_path = preview_dir / f"{test_image_path.name}.png"
        assert preview_path.exists()

        # Verify preview dimensions
        with Image.open(str(preview_path)) as preview_img:
            assert preview_img.width <= 50  # noqa: PLR2004
            assert preview_img.height <= 50  # noqa: PLR2004

        # Verify no metadata file
        metadata_path = Path(str(preview_path) + ".json")
        assert not metadata_path.exists()

    @pytest.mark.asyncio
    async def test_generate_preview_with_metadata_success(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test generating preview with metadata."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=True,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Verify preview file exists
        preview_dir = test_image_path.parent / "nodes_previews"
        preview_path = preview_dir / f"{test_image_path.name}.png"
        assert preview_path.exists()

        # Verify metadata file exists (named after source file, not preview)
        metadata_path = preview_dir / f"{test_image_path.name}.json"
        assert metadata_path.exists()

        # Verify metadata contents
        with metadata_path.open() as f:
            metadata_dict = json.load(f)

        assert "version" in metadata_dict
        assert "source_macro_path" in metadata_dict
        assert "source_file_size" in metadata_dict
        assert "source_file_modified_time" in metadata_dict
        assert "preview_file_name" in metadata_dict

        # Verify metadata values match source file
        source_stat = test_image_path.stat()
        assert metadata_dict["source_file_size"] == source_stat.st_size
        assert metadata_dict["source_file_modified_time"] == source_stat.st_mtime
        assert metadata_dict["preview_file_name"] == f"{test_image_path.name}.png"
        assert metadata_dict["version"] == PreviewMetadata.LATEST_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_generate_preview_source_file_not_found(
        self, artifact_manager: ArtifactManager, temp_dir: Path
    ) -> None:
        """Test generating preview for non-existent file."""
        nonexistent_path = temp_dir / "nonexistent.jpg"
        parsed_macro = ParsedMacro(str(nonexistent_path))
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        request = GeneratePreviewRequest(
            macro_path=macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=False,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultFailure)
        assert "file not found" in str(result.result_details).lower()

    @pytest.mark.asyncio
    async def test_generate_preview_unsupported_format(self, artifact_manager: ArtifactManager, temp_dir: Path) -> None:
        """Test generating preview for unsupported format."""
        # Create a .txt file
        txt_path = temp_dir / "test.txt"
        txt_path.write_text("This is not an image")

        parsed_macro = ParsedMacro(str(txt_path))
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        request = GeneratePreviewRequest(
            macro_path=macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=False,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultFailure)
        assert "provider" in str(result.result_details).lower() or "format" in str(result.result_details).lower()

    @pytest.mark.asyncio
    async def test_generate_preview_custom_dimensions(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test generating preview with custom dimensions."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=False,
            preview_generator_parameters={"max_width": 30, "max_height": 40},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Verify preview dimensions respect constraints
        preview_dir = test_image_path.parent / "nodes_previews"
        preview_path = preview_dir / f"{test_image_path.name}.png"

        with Image.open(str(preview_path)) as preview_img:
            assert preview_img.width <= 30  # noqa: PLR2004
            assert preview_img.height <= 40  # noqa: PLR2004
            # Verify aspect ratio preserved (source is 100x100, so should be square)
            assert preview_img.width == preview_img.height

    @pytest.mark.asyncio
    async def test_generate_preview_specific_format(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test generating preview with specific format."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format="webp",
            generate_preview_metadata_json=True,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Verify preview file has correct extension
        preview_dir = test_image_path.parent / "nodes_previews"
        preview_path = preview_dir / f"{test_image_path.name}.webp"
        assert preview_path.exists()

        # Verify metadata has correct extension (named after source file)
        metadata_path = preview_dir / f"{test_image_path.name}.json"
        with metadata_path.open() as f:
            metadata_dict = json.load(f)
        assert metadata_dict["preview_file_name"] == f"{test_image_path.name}.webp"

    @pytest.mark.asyncio
    async def test_generate_preview_specific_generator(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test generating preview with specific generator."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            preview_generator_name="Standard Thumbnail Generation",
            generate_preview_metadata_json=False,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Verify preview was created
        preview_dir = test_image_path.parent / "nodes_previews"
        preview_path = preview_dir / f"{test_image_path.name}.png"
        assert preview_path.exists()

    @pytest.mark.asyncio
    async def test_generate_preview_metadata_serialization_preserves_structure(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> None:
        """Test that metadata can be deserialized back to PreviewMetadata."""
        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=True,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = await artifact_manager.on_handle_generate_preview_request(request)

        assert isinstance(result, GeneratePreviewResultSuccess)

        # Read metadata and deserialize with Pydantic
        preview_dir = test_image_path.parent / "nodes_previews"
        # Metadata is named after source file, not preview
        metadata_path = preview_dir / f"{test_image_path.name}.json"

        with metadata_path.open() as f:
            metadata_dict = json.load(f)

        # Verify can deserialize to PreviewMetadata using Pydantic
        metadata = PreviewMetadata.model_validate(metadata_dict)

        assert metadata.version == PreviewMetadata.LATEST_SCHEMA_VERSION
        assert metadata.source_macro_path == str(test_image_path)
        assert metadata.source_file_size > 0
        assert metadata.source_file_modified_time > 0
        assert metadata.preview_file_name == f"{test_image_path.name}.png"


class TestGetPreviewForArtifact:
    """Tests for preview retrieval functionality."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_image_path(self, temp_dir: Path) -> Path:
        """Create a real test image file."""
        image_path = temp_dir / "test_source.jpg"

        # Create a simple test image (100x100 red square)
        img = Image.new("RGB", (100, 100), color="red")
        img.save(str(image_path), format="JPEG")

        return image_path

    @pytest.fixture
    def test_macro_path(self, test_image_path: Path) -> MacroPath:
        """Create MacroPath for test image."""
        parsed_macro = ParsedMacro(str(test_image_path))
        return MacroPath(parsed_macro=parsed_macro, variables={})

    @pytest.fixture
    def artifact_manager(self) -> ArtifactManager:
        """Create ArtifactManager with ImageArtifactProvider registered."""
        manager = ArtifactManager()
        # ImageArtifactProvider is already registered in constructor
        return manager

    @pytest.fixture
    def generated_preview_with_metadata(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath, test_image_path: Path
    ) -> Path:
        """Generate a preview with metadata for testing retrieval."""
        import asyncio

        request = GeneratePreviewRequest(
            macro_path=test_macro_path,
            artifact_provider_name="Image",
            format=None,
            generate_preview_metadata_json=True,
            preview_generator_parameters={"max_width": 50, "max_height": 50},
        )

        result = asyncio.run(artifact_manager.on_handle_generate_preview_request(request))
        assert isinstance(result, GeneratePreviewResultSuccess)

        preview_dir = test_image_path.parent / "nodes_previews"
        return preview_dir / f"{test_image_path.name}.png"

    @pytest.mark.usefixtures("generated_preview_with_metadata")
    def test_get_preview_success(self, artifact_manager: ArtifactManager, test_macro_path: MacroPath) -> None:
        """Test retrieving existing preview."""
        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=True,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultSuccess)
        assert result.path_to_preview is not None
        assert Path(result.path_to_preview).exists()
        assert Path(result.path_to_preview).is_absolute()

    def test_get_preview_source_file_not_found(self, artifact_manager: ArtifactManager, temp_dir: Path) -> None:
        """Test getting preview for non-existent source file."""
        nonexistent_path = temp_dir / "nonexistent.jpg"
        parsed_macro = ParsedMacro(str(nonexistent_path))
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        request = GetPreviewForArtifactRequest(
            macro_path=macro_path,
            generate_preview_if_necessary=True,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "source file not found" in str(result.result_details).lower()

    def test_get_preview_metadata_not_found(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath
    ) -> None:
        """Test getting preview when metadata doesn't exist."""
        # Don't generate preview or metadata
        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "metadata file not found" in str(result.result_details).lower()

    @pytest.mark.usefixtures("generated_preview_with_metadata")
    def test_get_preview_metadata_malformed_json(
        self,
        artifact_manager: ArtifactManager,
        test_macro_path: MacroPath,
        test_image_path: Path,
    ) -> None:
        """Test getting preview when metadata JSON is malformed."""
        # Corrupt the metadata file (named after source file, not preview)
        preview_dir = test_image_path.parent / "nodes_previews"
        metadata_path = preview_dir / f"{test_image_path.name}.json"
        metadata_path.write_text("{ invalid json }")

        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "malformed" in str(result.result_details).lower() or "json" in str(result.result_details).lower()

    @pytest.mark.usefixtures("generated_preview_with_metadata")
    def test_get_preview_metadata_invalid_schema(
        self,
        artifact_manager: ArtifactManager,
        test_macro_path: MacroPath,
        test_image_path: Path,
    ) -> None:
        """Test getting preview when metadata has missing required field."""
        # Write metadata with missing field (named after source file)
        preview_dir = test_image_path.parent / "nodes_previews"
        metadata_path = preview_dir / f"{test_image_path.name}.json"
        incomplete_metadata = {
            "version": "0.1.0",
            "source_macro_path": str(test_image_path),
            # Missing: source_file_size, source_file_modified_time, preview_file_name
        }
        metadata_path.write_text(json.dumps(incomplete_metadata))

        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "invalid metadata" in str(result.result_details).lower()

    @pytest.mark.usefixtures("generated_preview_with_metadata")
    def test_get_preview_stale_source_modified(
        self,
        artifact_manager: ArtifactManager,
        test_macro_path: MacroPath,
        test_image_path: Path,
    ) -> None:
        """Test getting preview when source file was modified."""
        # Modify source file by writing more data
        with test_image_path.open("ab") as f:
            f.write(b"extra data to change size")

        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "stale" in str(result.result_details).lower() or "modified" in str(result.result_details).lower()

    @pytest.mark.usefixtures("generated_preview_with_metadata")
    def test_get_preview_stale_source_touched(
        self,
        artifact_manager: ArtifactManager,
        test_macro_path: MacroPath,
        test_image_path: Path,
    ) -> None:
        """Test getting preview when source file mtime was updated."""
        # Touch the file to update mtime
        import time

        future_time = time.time() + 100
        os.utime(test_image_path, (future_time, future_time))

        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "stale" in str(result.result_details).lower() or "modified" in str(result.result_details).lower()

    def test_get_preview_preview_file_missing(
        self,
        artifact_manager: ArtifactManager,
        test_macro_path: MacroPath,
        generated_preview_with_metadata: Path,
    ) -> None:
        """Test getting preview when preview file is deleted but metadata exists."""
        # Delete the preview file but keep metadata
        generated_preview_with_metadata.unlink()

        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)

        assert isinstance(result, GetPreviewForArtifactResultFailure)
        assert "file not found" in str(result.result_details).lower()

    def test_get_preview_generate_if_necessary_flag(
        self, artifact_manager: ArtifactManager, test_macro_path: MacroPath
    ) -> None:
        """Test that generate_preview_if_necessary flag is accepted."""
        # Test with flag set to False
        request = GetPreviewForArtifactRequest(
            macro_path=test_macro_path,
            generate_preview_if_necessary=False,
        )

        # Should not raise error (but will fail since no preview exists)
        result = artifact_manager.on_handle_get_preview_for_artifact_request(request)
        assert isinstance(result, GetPreviewForArtifactResultFailure)
