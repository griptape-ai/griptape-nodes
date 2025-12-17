import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.drivers.storage.griptape_cloud_storage_driver import GriptapeCloudStorageDriver
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy

# pyright: reportAttributeAccessIssue=false

# Test data constants
TEST_FILE_PATH = Path("test_file.txt")
TEST_BUCKET_ID = "test-bucket-123"
TEST_API_KEY = "test-api-key"


class TestGriptapeCloudStorageDriverCreateSignedUploadUrl:
    """Test GriptapeCloudStorageDriver.create_signed_upload_url() method with ExistingFilePolicy support."""

    @pytest.fixture
    def cloud_storage_driver(self) -> GriptapeCloudStorageDriver:
        """Create GriptapeCloudStorageDriver instance for testing."""
        return GriptapeCloudStorageDriver(
            workspace_directory=Path("/workspace"),
            bucket_id=TEST_BUCKET_ID,
            api_key=TEST_API_KEY,
        )

    def test_create_signed_upload_url_warns_when_policy_not_overwrite(
        self, cloud_storage_driver: GriptapeCloudStorageDriver, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that create_signed_upload_url logs warning when policy is not OVERWRITE."""
        with (
            patch.object(cloud_storage_driver, "_create_asset"),
            patch("griptape_nodes.drivers.storage.griptape_cloud_storage_driver.httpx.post") as mock_post,
        ):
            # Setup mocks
            mock_post_response = Mock()
            mock_post_response.raise_for_status.return_value = None
            mock_post_response.json.return_value = {"url": "http://test.com/upload"}
            mock_post.return_value = mock_post_response

            # Clear any existing log records and set level
            caplog.clear()
            caplog.set_level(logging.WARNING)

            # Call create_signed_upload_url with FAIL policy (not OVERWRITE)
            cloud_storage_driver.create_signed_upload_url(TEST_FILE_PATH, ExistingFilePolicy.FAIL)

            # Verify warning was logged
            assert len(caplog.records) == 1
            warning_record = caplog.records[0]
            assert warning_record.levelno == logging.WARNING
            assert "Griptape Cloud storage only supports OVERWRITE policy" in warning_record.message
            assert "fail" in warning_record.message  # Policy value
            assert str(TEST_FILE_PATH) in warning_record.message  # File path

    def test_create_signed_upload_url_warns_when_policy_create_new(
        self, cloud_storage_driver: GriptapeCloudStorageDriver, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that create_signed_upload_url logs warning when policy is CREATE_NEW."""
        with (
            patch.object(cloud_storage_driver, "_create_asset"),
            patch("griptape_nodes.drivers.storage.griptape_cloud_storage_driver.httpx.post") as mock_post,
        ):
            # Setup mocks
            mock_post_response = Mock()
            mock_post_response.raise_for_status.return_value = None
            mock_post_response.json.return_value = {"url": "http://test.com/upload"}
            mock_post.return_value = mock_post_response

            # Clear any existing log records and set level
            caplog.clear()
            caplog.set_level(logging.WARNING)

            # Call create_signed_upload_url with CREATE_NEW policy (not OVERWRITE)
            cloud_storage_driver.create_signed_upload_url(TEST_FILE_PATH, ExistingFilePolicy.CREATE_NEW)

            # Verify warning was logged
            assert len(caplog.records) == 1
            warning_record = caplog.records[0]
            assert warning_record.levelno == logging.WARNING
            assert "Griptape Cloud storage only supports OVERWRITE policy" in warning_record.message
            assert "create_new" in warning_record.message  # Policy value
            assert str(TEST_FILE_PATH) in warning_record.message  # File path

    def test_create_signed_upload_url_no_warning_when_policy_overwrite(
        self, cloud_storage_driver: GriptapeCloudStorageDriver, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that create_signed_upload_url does NOT log warning when policy is OVERWRITE."""
        with (
            patch.object(cloud_storage_driver, "_create_asset"),
            patch("griptape_nodes.drivers.storage.griptape_cloud_storage_driver.httpx.post") as mock_post,
        ):
            # Setup mocks
            mock_post_response = Mock()
            mock_post_response.raise_for_status.return_value = None
            mock_post_response.json.return_value = {"url": "http://test.com/upload"}
            mock_post.return_value = mock_post_response

            # Clear any existing log records and set level
            caplog.clear()
            caplog.set_level(logging.WARNING)

            # Call create_signed_upload_url with OVERWRITE policy (supported)
            cloud_storage_driver.create_signed_upload_url(TEST_FILE_PATH, ExistingFilePolicy.OVERWRITE)

            # Verify NO warning was logged
            assert len(caplog.records) == 0

    def test_create_signed_upload_url_no_warning_with_default_policy(
        self, cloud_storage_driver: GriptapeCloudStorageDriver, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that create_signed_upload_url does NOT log warning with default OVERWRITE policy."""
        with (
            patch.object(cloud_storage_driver, "_create_asset"),
            patch("griptape_nodes.drivers.storage.griptape_cloud_storage_driver.httpx.post") as mock_post,
        ):
            # Setup mocks
            mock_post_response = Mock()
            mock_post_response.raise_for_status.return_value = None
            mock_post_response.json.return_value = {"url": "http://test.com/upload"}
            mock_post.return_value = mock_post_response

            # Clear any existing log records and set level
            caplog.clear()
            caplog.set_level(logging.WARNING)

            # Call create_signed_upload_url WITHOUT policy parameter (defaults to OVERWRITE)
            cloud_storage_driver.create_signed_upload_url(TEST_FILE_PATH)

            # Verify NO warning was logged
            assert len(caplog.records) == 0


class TestGriptapeCloudStorageDriverParseCloudAssetPath:
    """Test GriptapeCloudStorageDriver._parse_cloud_asset_path() domain validation."""

    @pytest.fixture
    def cloud_storage_driver(self) -> GriptapeCloudStorageDriver:
        """Create GriptapeCloudStorageDriver instance for testing."""
        return GriptapeCloudStorageDriver(
            workspace_directory=Path("/workspace"),
            bucket_id="test-bucket-123",
            api_key="test-api-key",
            base_url="https://cloud.griptape.ai",
        )

    def test_parse_full_url_with_matching_domain(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Valid full URL with matching domain should extract path correctly."""
        full_url = "https://cloud.griptape.ai/buckets/9ff5bda9-8f55-409f-a1dd-d1aba54fa233/assets/days_of_christmas.zip"
        result = cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert result == Path("days_of_christmas.zip")

    def test_parse_full_url_with_mismatched_domain(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Full URL with different domain should raise ValueError."""
        full_url = "https://evil-domain.com/buckets/test-bucket/assets/file.txt"
        with pytest.raises(ValueError, match="Invalid cloud asset URL") as exc_info:
            cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert "evil-domain.com" in str(exc_info.value)
        assert "cloud.griptape.ai" in str(exc_info.value)

    def test_parse_full_url_case_insensitive_domain(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Domain comparison should be case-insensitive."""
        full_url = "https://CLOUD.GRIPTAPE.AI/buckets/test-bucket/assets/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert result == Path("file.txt")

    def test_parse_full_url_with_http_scheme(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """http:// URLs should work if domain matches."""
        # Update base_url to use http for this test
        cloud_storage_driver.base_url = "http://cloud.griptape.ai"
        full_url = "http://cloud.griptape.ai/buckets/test-bucket/assets/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert result == Path("file.txt")

    def test_parse_path_only_no_domain(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Path-only format (no domain) should work as before."""
        path_only = "/buckets/test-bucket/assets/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(path_only)
        assert result == Path("file.txt")

    def test_parse_workspace_relative_path(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Workspace-relative paths should pass through unchanged."""
        workspace_path = "simple/path/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(Path(workspace_path))
        assert result == Path(workspace_path)

    def test_parse_url_with_port_in_domain(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """URLs with ports should be handled correctly."""
        # Update base_url to include port
        cloud_storage_driver.base_url = "https://cloud.griptape.ai:8443"
        full_url = "https://cloud.griptape.ai:8443/buckets/test-bucket/assets/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert result == Path("file.txt")

    def test_parse_url_with_port_mismatch(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """URLs with different ports should raise ValueError."""
        cloud_storage_driver.base_url = "https://cloud.griptape.ai:8443"
        full_url = "https://cloud.griptape.ai:9000/buckets/test-bucket/assets/file.txt"
        with pytest.raises(ValueError, match="Invalid cloud asset URL"):
            cloud_storage_driver._parse_cloud_asset_path(full_url)

    def test_error_message_content(
        self, cloud_storage_driver: GriptapeCloudStorageDriver, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify error message includes all necessary context."""
        caplog.clear()
        caplog.set_level(logging.ERROR)

        full_url = "https://wrong-domain.com/buckets/test-bucket/assets/file.txt"
        with pytest.raises(ValueError, match="Invalid cloud asset URL") as exc_info:
            cloud_storage_driver._parse_cloud_asset_path(full_url)

        error_message = str(exc_info.value)
        assert "Invalid cloud asset URL" in error_message
        assert "wrong-domain.com" in error_message
        assert "https://cloud.griptape.ai" in error_message
        assert "cloud.griptape.ai" in error_message

        # Verify error was also logged
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR
        assert "Invalid cloud asset URL" in caplog.records[0].message

    def test_parse_full_url_with_nested_path(self, cloud_storage_driver: GriptapeCloudStorageDriver) -> None:
        """Full URL with nested path after assets should extract correctly."""
        full_url = "https://cloud.griptape.ai/buckets/test-bucket/assets/nested/path/to/file.txt"
        result = cloud_storage_driver._parse_cloud_asset_path(full_url)
        assert result == Path("nested/path/to/file.txt")
