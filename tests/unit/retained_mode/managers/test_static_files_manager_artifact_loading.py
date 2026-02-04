import base64
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

# pyright: reportAttributeAccessIssue=false

# Test data constants
TEST_IMAGE_BYTES = b"fake image data"
TEST_BASE64_STRING = base64.b64encode(TEST_IMAGE_BYTES).decode("utf-8")
TEST_DATA_URI = f"data:image/png;base64,{TEST_BASE64_STRING}"
TEST_URL = "https://example.com/image.png"
TEST_FILE_PATH = "/Users/test/image.png"


class MockArtifact:
    """Mock artifact object with value attribute."""

    def __init__(self, value: str | bytes):
        self.value = value


class MockImageArtifact:
    """Mock ImageArtifact with base64 attribute."""

    def __init__(self, base64_str: str):
        self.base64 = base64_str


class TestLoadArtifactBytes:
    """Test StaticFilesManager.load_artifact_bytes() static method."""

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_bytes(self) -> None:
        """Test loading from raw bytes input."""
        result = await StaticFilesManager.load_artifact_bytes(TEST_IMAGE_BYTES)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_string_url(self) -> None:
        """Test loading from HTTP URL string."""
        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock the async context manager
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await StaticFilesManager.load_artifact_bytes(TEST_URL)

            assert result == TEST_IMAGE_BYTES
            mock_client.get.assert_called_once_with(TEST_URL, timeout=120.0)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_data_uri(self) -> None:
        """Test loading from data URI."""
        result = await StaticFilesManager.load_artifact_bytes(TEST_DATA_URI)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_data_uri_no_comma(self) -> None:
        """Test loading from data URI without comma separator."""
        data_uri_no_comma = f"data:{TEST_BASE64_STRING}"
        result = await StaticFilesManager.load_artifact_bytes(data_uri_no_comma)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_raw_base64(self) -> None:
        """Test loading from raw base64 string (no data URI prefix)."""
        result = await StaticFilesManager.load_artifact_bytes(TEST_BASE64_STRING)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_artifact_object(self) -> None:
        """Test loading from artifact object with .value attribute."""
        artifact = MockArtifact(value=TEST_BASE64_STRING)
        result = await StaticFilesManager.load_artifact_bytes(artifact)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_image_artifact_with_base64(self) -> None:
        """Test loading from ImageArtifact with .base64 attribute."""
        artifact = MockImageArtifact(base64_str=TEST_BASE64_STRING)
        result = await StaticFilesManager.load_artifact_bytes(artifact)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_dict(self) -> None:
        """Test loading from dictionary format {"type": "...", "value": "..."}."""
        artifact_dict = {"type": "image", "value": TEST_BASE64_STRING}
        result = await StaticFilesManager.load_artifact_bytes(artifact_dict)
        assert result == TEST_IMAGE_BYTES

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_with_custom_timeout(self) -> None:
        """Test loading with custom timeout parameter."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await StaticFilesManager.load_artifact_bytes(TEST_URL, timeout=60.0)

            assert result == TEST_IMAGE_BYTES
            mock_client.get.assert_called_once_with(TEST_URL, timeout=60.0)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_with_custom_context_name(self) -> None:
        """Test that custom context_name appears in error messages."""
        with pytest.raises(ValueError, match=r"my_node\.image: Cannot load None artifact"):
            await StaticFilesManager.load_artifact_bytes(None, context_name="my_node.image")

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_none(self) -> None:
        """Test that None input raises ValueError."""
        with pytest.raises(ValueError, match="Cannot load None artifact"):
            await StaticFilesManager.load_artifact_bytes(None)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot extract value from artifact"):
            await StaticFilesManager.load_artifact_bytes("")

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_whitespace_string(self) -> None:
        """Test that whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot extract value from artifact"):
            await StaticFilesManager.load_artifact_bytes("   ")

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_invalid_base64(self) -> None:
        """Test that invalid base64 raises ValueError."""
        with pytest.raises(ValueError, match="Value is not a URL, path, or valid base64"):
            await StaticFilesManager.load_artifact_bytes("not-valid-base64!!!")

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_invalid_data_uri_base64(self) -> None:
        """Test that data URI with invalid base64 raises ValueError."""
        invalid_data_uri = "data:image/png;base64,not-valid-base64!!!"
        with pytest.raises(ValueError, match="Invalid base64 data in data URI"):
            await StaticFilesManager.load_artifact_bytes(invalid_data_uri)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_http_error(self) -> None:
        """Test that HTTP errors are raised as httpx.HTTPError."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPStatusError("404 Not Found", request=Mock(), response=Mock())
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPError, match="Download failed"):
                await StaticFilesManager.load_artifact_bytes(TEST_URL)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_raises_on_timeout(self) -> None:
        """Test that timeout raises httpx.TimeoutException."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Request timed out")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.TimeoutException, match="Download timed out after 120s"):
                await StaticFilesManager.load_artifact_bytes(TEST_URL)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_dict_with_empty_value(self) -> None:
        """Test that dict with empty value raises ValueError."""
        artifact_dict = {"type": "image", "value": ""}
        with pytest.raises(ValueError, match="Cannot extract value from artifact"):
            await StaticFilesManager.load_artifact_bytes(artifact_dict)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_artifact_with_none_value(self) -> None:
        """Test that artifact with None value raises ValueError."""
        artifact = MockArtifact(value=None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Cannot extract value from artifact"):
            await StaticFilesManager.load_artifact_bytes(artifact)

    @pytest.mark.asyncio
    async def test_load_artifact_bytes_from_unsupported_type(self) -> None:
        """Test that unsupported type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot extract value from artifact of type int"):
            await StaticFilesManager.load_artifact_bytes(12345)


class TestLoadAsBase64DataUri:
    """Test StaticFilesManager.load_as_base64_data_uri() static method."""

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_bytes(self) -> None:
        """Test converting bytes to data URI."""
        result = await StaticFilesManager.load_as_base64_data_uri(TEST_IMAGE_BYTES)
        assert result == TEST_DATA_URI

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_existing_data_uri(self) -> None:
        """Test that existing data URI is returned as-is."""
        result = await StaticFilesManager.load_as_base64_data_uri(TEST_DATA_URI)
        assert result == TEST_DATA_URI

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_url(self) -> None:
        """Test downloading from URL and converting to data URI."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await StaticFilesManager.load_as_base64_data_uri(TEST_URL)

            assert result == TEST_DATA_URI
            mock_client.get.assert_called_once_with(TEST_URL, timeout=120.0)

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_raw_base64(self) -> None:
        """Test converting raw base64 string to data URI."""
        result = await StaticFilesManager.load_as_base64_data_uri(TEST_BASE64_STRING)
        assert result == TEST_DATA_URI

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_with_custom_media_type(self) -> None:
        """Test converting with custom media type."""
        result = await StaticFilesManager.load_as_base64_data_uri(TEST_IMAGE_BYTES, media_type="image/jpeg")
        expected = f"data:image/jpeg;base64,{TEST_BASE64_STRING}"
        assert result == expected

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_with_custom_timeout(self) -> None:
        """Test loading with custom timeout parameter."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await StaticFilesManager.load_as_base64_data_uri(TEST_URL, timeout=60.0)

            assert result == TEST_DATA_URI
            mock_client.get.assert_called_once_with(TEST_URL, timeout=60.0)

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_with_custom_context_name(self) -> None:
        """Test that custom context_name appears in error messages."""
        with pytest.raises(ValueError, match=r"my_node\.video: Cannot load None artifact"):
            await StaticFilesManager.load_as_base64_data_uri(None, context_name="my_node.video")

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_raises_on_none(self) -> None:
        """Test that None input raises ValueError."""
        with pytest.raises(ValueError, match="Cannot load None artifact"):
            await StaticFilesManager.load_as_base64_data_uri(None)

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_raises_on_empty_string(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot extract value from artifact"):
            await StaticFilesManager.load_as_base64_data_uri("")

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_raises_on_http_error(self) -> None:
        """Test that HTTP errors are raised as httpx.HTTPError."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPStatusError("404 Not Found", request=Mock(), response=Mock())
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPError, match="Download failed"):
                await StaticFilesManager.load_as_base64_data_uri(TEST_URL)

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_raises_on_timeout(self) -> None:
        """Test that timeout raises httpx.TimeoutException."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Request timed out")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.TimeoutException, match="Download timed out after 120s"):
                await StaticFilesManager.load_as_base64_data_uri(TEST_URL)

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_artifact_object(self) -> None:
        """Test loading from artifact object with .value attribute."""
        artifact = MockArtifact(value=TEST_BASE64_STRING)
        result = await StaticFilesManager.load_as_base64_data_uri(artifact)
        assert result == TEST_DATA_URI

    @pytest.mark.asyncio
    async def test_load_as_base64_data_uri_from_dict(self) -> None:
        """Test loading from dictionary format."""
        artifact_dict = {"type": "image", "value": TEST_BASE64_STRING}
        result = await StaticFilesManager.load_as_base64_data_uri(artifact_dict)
        assert result == TEST_DATA_URI


class TestDownloadAndSave:
    """Test StaticFilesManager.download_and_save() instance method."""

    @pytest.fixture
    def mock_config_manager(self) -> Mock:
        """Mock ConfigManager for StaticFilesManager initialization."""
        mock_config = Mock()
        mock_config.get_config_value.return_value = "local"
        return mock_config

    @pytest.fixture
    def mock_secrets_manager(self) -> Mock:
        """Mock SecretsManager for StaticFilesManager initialization."""
        return Mock()

    @pytest.fixture
    def mock_static_files_manager(self, mock_config_manager: Mock, mock_secrets_manager: Mock) -> StaticFilesManager:
        """Create StaticFilesManager instance with mocked dependencies."""
        with patch("griptape_nodes.retained_mode.managers.static_files_manager.LocalStorageDriver"):
            manager = StaticFilesManager(
                config_manager=mock_config_manager, secrets_manager=mock_secrets_manager, event_manager=None
            )
            # Mock the storage driver methods
            manager.storage_driver = Mock()  # type: ignore[assignment]
            return manager

    @pytest.mark.asyncio
    async def test_download_and_save_returns_path_string(self, mock_static_files_manager: StaticFilesManager) -> None:
        """Test downloading and saving without artifact_type returns path string."""
        expected_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_path

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
                result = await mock_static_files_manager.download_and_save(TEST_URL, "test_image.jpg")

                assert result == expected_path
                # Verify save_static_file was called with use_direct_save=True
                mock_static_files_manager.storage_driver.save_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_and_save_returns_artifact(self, mock_static_files_manager: StaticFilesManager) -> None:
        """Test downloading and saving with artifact_type returns artifact object."""
        expected_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_path

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
                result = await mock_static_files_manager.download_and_save(
                    TEST_URL, "test_image.jpg", artifact_type=MockArtifact
                )

                assert isinstance(result, MockArtifact)
                assert result.value == expected_path

    @pytest.mark.asyncio
    async def test_download_and_save_with_custom_timeout(self, mock_static_files_manager: StaticFilesManager) -> None:
        """Test downloading with custom timeout parameter."""
        expected_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_path

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
                result = await mock_static_files_manager.download_and_save(TEST_URL, "test_image.jpg", timeout=60.0)

                assert result == expected_path
                mock_client.get.assert_called_once_with(TEST_URL, timeout=60.0)

    @pytest.mark.asyncio
    async def test_download_and_save_with_existing_file_policy(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test downloading with custom existing_file_policy."""
        expected_path = "/mock/workspace/staticfiles/test_image_1.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_path

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
                result = await mock_static_files_manager.download_and_save(
                    TEST_URL, "test_image.jpg", existing_file_policy=ExistingFilePolicy.CREATE_NEW
                )

                assert result == expected_path
                # Verify CREATE_NEW policy was passed to storage driver
                call_args = mock_static_files_manager.storage_driver.save_file.call_args
                assert call_args[0][2] == ExistingFilePolicy.CREATE_NEW

    @pytest.mark.asyncio
    async def test_download_and_save_raises_on_download_failure(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that download failure raises RuntimeError."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPStatusError("404 Not Found", request=Mock(), response=Mock())
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to download"):
                await mock_static_files_manager.download_and_save(TEST_URL, "test_image.jpg")

    @pytest.mark.asyncio
    async def test_download_and_save_raises_on_save_failure(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that save failure raises RuntimeError."""
        mock_static_files_manager.storage_driver.save_file.side_effect = RuntimeError("Storage driver failed")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with (
                patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
                pytest.raises(RuntimeError, match="Failed to save"),
            ):
                await mock_static_files_manager.download_and_save(TEST_URL, "test_image.jpg")

    @pytest.mark.asyncio
    async def test_download_and_save_raises_on_file_exists_with_fail_policy(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that FileExistsError is raised when using FAIL policy on existing file."""
        mock_static_files_manager.storage_driver.save_file.side_effect = FileExistsError("File already exists")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = TEST_IMAGE_BYTES
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with (
                patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
                pytest.raises(RuntimeError, match="Failed to save"),
            ):
                await mock_static_files_manager.download_and_save(
                    TEST_URL, "test_image.jpg", existing_file_policy=ExistingFilePolicy.FAIL
                )
