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
        """Test default situation is 'save_file' and resolves to appropriate policy."""
        from pathlib import Path

        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.CREATE_NEW),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITHOUT situation_name parameter (tests default)
            result = mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME)

            # Verify the default situation "save_file" was used
            mock_resolve.assert_called_once_with(situation_name="save_file", file_name=TEST_FILE_NAME, variables=None)

            # Verify the resolved policy was passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.CREATE_NEW

            # Verify successful return
            assert result == mock_download_url

    def test_save_static_file_explicit_overwrite_policy(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test custom situation that resolves to OVERWRITE policy."""
        from pathlib import Path

        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.OVERWRITE),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file WITH custom situation that has OVERWRITE policy
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, situation_name="custom_overwrite_situation"
            )

            # Verify the custom situation was used
            mock_resolve.assert_called_once_with(
                situation_name="custom_overwrite_situation", file_name=TEST_FILE_NAME, variables=None
            )

            # Verify the OVERWRITE policy was passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.OVERWRITE

            # Verify successful return
            assert result == mock_download_url

    def test_save_static_file_fail_policy_success(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test situation with FAIL policy when file doesn't exist (success case)."""
        from pathlib import Path

        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.FAIL),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file with situation that has FAIL policy
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, situation_name="custom_fail_situation"
            )

            # Verify the custom situation was used
            mock_resolve.assert_called_once_with(
                situation_name="custom_fail_situation", file_name=TEST_FILE_NAME, variables=None
            )

            # Verify the FAIL policy was passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.FAIL

            # Verify successful return (file didn't exist so FAIL policy succeeded)
            assert result == mock_download_url

    def test_save_static_file_fail_policy_raises_file_exists_error(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test situation with FAIL policy when file exists (failure case)."""
        from pathlib import Path

        # Mock storage driver to raise FileExistsError (simulating file exists)
        mock_static_files_manager.storage_driver.create_signed_upload_url.side_effect = FileExistsError(
            f"File {TEST_FILE_NAME} already exists"
        )

        with patch.object(
            mock_static_files_manager,
            "_resolve_path_via_situation",
            return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.FAIL),
        ) as mock_resolve:
            # Call save_static_file with FAIL policy situation should raise FileExistsError
            with pytest.raises(FileExistsError, match=f"File {TEST_FILE_NAME} already exists"):
                mock_static_files_manager.save_static_file(
                    TEST_FILE_DATA, TEST_FILE_NAME, situation_name="custom_fail_situation"
                )

            # Verify the situation was resolved
            mock_resolve.assert_called_once_with(
                situation_name="custom_fail_situation", file_name=TEST_FILE_NAME, variables=None
            )

            # Verify the FAIL policy was passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.FAIL

    def test_save_static_file_create_new_policy(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test situation with CREATE_NEW policy."""
        from pathlib import Path

        # Setup mocks - storage driver handles unique filename generation
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = (
            f"http://test.com/download/{TEST_ALTERNATIVE_NAME}"
        )

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.CREATE_NEW),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file with situation that has CREATE_NEW policy
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, situation_name="custom_create_new_situation"
            )

            # Verify the custom situation was used
            mock_resolve.assert_called_once_with(
                situation_name="custom_create_new_situation", file_name=TEST_FILE_NAME, variables=None
            )

            # Verify the CREATE_NEW policy was passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert args[0][1] == ExistingFilePolicy.CREATE_NEW

            # Verify successful return with potentially modified filename
            assert TEST_ALTERNATIVE_NAME in result

    def test_save_static_file_storage_driver_exception_propagation(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that storage driver exceptions are propagated."""
        from pathlib import Path

        # Mock storage driver to raise a generic exception
        mock_static_files_manager.storage_driver.create_signed_upload_url.side_effect = RuntimeError(
            "Storage driver connection failed"
        )

        with patch.object(
            mock_static_files_manager,
            "_resolve_path_via_situation",
            return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.OVERWRITE),
        ) as mock_resolve:
            # Call save_static_file should propagate exception
            with pytest.raises(RuntimeError, match="Storage driver connection failed"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME)

            # Verify situation was resolved
            mock_resolve.assert_called_once()

            # Verify storage driver was called before exception
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()

    def test_save_static_file_http_upload_failure(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test HTTP upload failure handling."""
        from pathlib import Path

        # Setup mocks
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.OVERWRITE),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Mock httpx.request to raise HTTPStatusError
            mock_response = Mock()
            mock_response.json.return_value = {"error": "Upload failed"}
            mock_error = httpx.HTTPStatusError("Upload failed", request=Mock(), response=mock_response)
            mock_request.side_effect = mock_error

            # Call save_static_file should raise ValueError
            with pytest.raises(ValueError, match="Upload failed"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME)

            # Verify situation was resolved
            mock_resolve.assert_called_once_with(situation_name="save_file", file_name=TEST_FILE_NAME, variables=None)

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
        """Test end-to-end success path with situation-based API."""
        from pathlib import Path

        # Setup mocks for complete success flow
        mock_static_files_manager.storage_driver.create_signed_upload_url.return_value = mock_upload_response
        mock_static_files_manager.storage_driver.create_signed_download_url.return_value = mock_download_url

        with (
            patch.object(
                mock_static_files_manager,
                "_resolve_path_via_situation",
                return_value=(Path("staticfiles/test_image.jpg"), ExistingFilePolicy.CREATE_NEW),
            ) as mock_resolve,
            patch("griptape_nodes.retained_mode.managers.static_files_manager.httpx.request") as mock_request,
        ):
            # Setup successful HTTP response
            mock_response = Mock()
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            # Call save_static_file with custom situation for full flow test
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, situation_name="custom_situation", variables={"node_name": "TestNode"}
            )

            # Verify complete workflow
            # 1. Situation resolved with correct parameters
            mock_resolve.assert_called_once_with(
                situation_name="custom_situation", file_name=TEST_FILE_NAME, variables={"node_name": "TestNode"}
            )

            # 2. Policy passed to storage driver
            mock_static_files_manager.storage_driver.create_signed_upload_url.assert_called_once()
            upload_args = mock_static_files_manager.storage_driver.create_signed_upload_url.call_args
            assert upload_args[0][1] == ExistingFilePolicy.CREATE_NEW

            # 3. HTTP request made with correct parameters
            mock_request.assert_called_once()
            request_args = mock_request.call_args
            assert request_args[0] == (mock_upload_response["method"], mock_upload_response["url"])
            assert request_args[1]["content"] == TEST_FILE_DATA
            assert request_args[1]["headers"] == mock_upload_response["headers"]

            # 4. Download URL generated after successful upload
            mock_static_files_manager.storage_driver.create_signed_download_url.assert_called_once()

            # 5. Correct URL returned
            assert result == mock_download_url
