import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest

from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

# pyright: reportAttributeAccessIssue=false

# Test data constants
TEST_FILE_DATA = b"test image content"
TEST_FILE_NAME = "test_image.jpg"
TEST_ALTERNATIVE_NAME = "test_image_1.jpg"


class TestStaticFilesManagerSaveStaticFile:
    """Test StaticFilesManager.save_static_file() method with ExistingFilePolicy support."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_config_manager(self) -> Mock:
        """Mock ConfigManager for StaticFilesManager initialization."""
        mock_config = Mock()
        mock_config.get_config_value.return_value = "local"
        mock_config.workspace_path = Path("/mock/workspace")
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

    @pytest.fixture
    def mock_upload_response(self) -> dict[str, Any]:
        """Standard mock response for create_signed_upload_url."""
        return {
            "url": "http://test.com/upload",
            "headers": {"Authorization": "Bearer token"},
            "method": "PUT",
            "file_path": "staticfiles/test_image.jpg",
        }

    @pytest.fixture
    def mock_download_url(self) -> str:
        """Standard mock response for create_signed_download_url."""
        return "http://test.com/download/test_file.jpg"

    def test_save_static_file_default_policy_is_overwrite(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test line 187: Verify default behavior unchanged (backward compatibility)."""
        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITHOUT policy parameter (tests line 187 default)
            result = mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME)

            # Verify the default policy (OVERWRITE) was passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.OVERWRITE  # Second positional argument

            # Verify successful return
            assert result == mock_download_url

    def test_save_static_file_explicit_overwrite_policy(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test line 212: Explicitly pass OVERWRITE policy."""
        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITH explicit OVERWRITE policy (tests line 212)
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE
            )

            # Verify the OVERWRITE policy was passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.OVERWRITE  # Second positional argument

            # Verify successful return
            assert result == mock_download_url

    def test_save_static_file_fail_policy_success(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test line 212: Pass FAIL policy when file doesn't exist (success case)."""
        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITH FAIL policy (tests line 212)
            result = mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.FAIL)

            # Verify the FAIL policy was passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.FAIL  # Second positional argument

            # Verify successful return (file didn't exist so FAIL policy succeeded)
            assert result == mock_download_url

    def test_save_static_file_fail_policy_raises_file_exists_error(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test line 212: Pass FAIL policy when file exists (failure case)."""
        # Mock storage driver to raise FileExistsError (simulating file exists)
        mock_static_files_manager.storage_driver.create_signed_upload_url.side_effect = FileExistsError(
            f"File {TEST_FILE_NAME} already exists"
        )

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITH FAIL policy should raise FileExistsError
            with pytest.raises(FileExistsError, match=f"File {TEST_FILE_NAME} already exists"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.FAIL)

            # Verify the FAIL policy was passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.FAIL  # Second positional argument

    def test_save_static_file_create_new_policy(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test line 212: Pass CREATE_NEW policy."""
        # Setup mocks - storage driver handles unique filename generation
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = (
            f"http://test.com/download/{TEST_ALTERNATIVE_NAME}"
        )

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITH CREATE_NEW policy (tests line 212)
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.CREATE_NEW
            )

            # Verify the CREATE_NEW policy was passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.CREATE_NEW  # Second positional argument

            # Verify successful return with potentially modified filename
            assert TEST_ALTERNATIVE_NAME in result

    def test_save_static_file_storage_driver_exception_propagation(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that storage driver exceptions are propagated as ValueError."""
        # Mock storage driver to raise a generic exception
        mock_static_files_manager.storage_driver.create_signed_upload_url.side_effect = RuntimeError(
            "Storage driver connection failed"
        )

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file should propagate exception as ValueError
            with pytest.raises(RuntimeError, match="Storage driver connection failed"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE)

            # Verify storage driver was called before exception
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()

    def test_save_static_file_http_upload_failure(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test HTTP upload failure handling."""
        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Mock httpx.request to raise HTTPStatusError
            mock_response = Mock()
            mock_response.json.return_value = {"error": "Upload failed"}
            mock_error = httpx.HTTPStatusError("Upload failed", request=Mock(), response=mock_response)
            mock_request.side_effect = mock_error

            # Call save_static_file should raise ValueError (existing behavior)
            with pytest.raises(ValueError, match="Upload failed"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE)

            # Verify storage driver was called successfully before HTTP failure
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            # Verify HTTP request was attempted
            mock_request.assert_called_once()

    def test_save_static_file_complete_success_flow(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test end-to-end success path with new policy parameter."""
        # Setup mocks for complete success flow
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"),
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file with CREATE_NEW policy for full flow test
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.CREATE_NEW
            )

            # Verify complete workflow
            # 1. Policy passed to storage driver (line 212)
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            upload_args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert upload_args[0][1] == ExistingFilePolicy.CREATE_NEW  # Second positional argument

            # 2. HTTP request made with correct parameters
            mock_request.assert_called_once()
            request_args = mock_request.call_args
            assert request_args[0] == (mock_upload_response["method"], mock_upload_response["url"])
            assert request_args[1]["content"] == TEST_FILE_DATA
            assert request_args[1]["headers"] == mock_upload_response["headers"]

            # 3. Download URL generated after successful upload
            mock_static_files_manager.storage_driver.create_signed_download_url.assert_called_once()

            # 4. Correct URL returned
            assert result == mock_download_url
