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
