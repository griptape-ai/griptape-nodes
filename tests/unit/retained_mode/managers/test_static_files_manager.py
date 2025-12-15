import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

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
        """Test line 202: Verify default behavior unchanged (backward compatibility)."""
        # Mock save_file to return a file path
        expected_file_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_file_path

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITHOUT policy parameter (tests line 202 default)
            result = mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME)

            # Verify the default policy (OVERWRITE) was passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            assert call_args[0][1] == TEST_FILE_DATA  # Second positional argument
            assert call_args[0][2] == ExistingFilePolicy.OVERWRITE  # Third positional argument

            # Verify successful return
            assert result == expected_file_path

    def test_save_static_file_explicit_overwrite_policy(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test line 230: Explicitly pass OVERWRITE policy."""
        # Mock save_file to return a file path
        expected_file_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_file_path

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITH explicit OVERWRITE policy (tests line 230)
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE
            )

            # Verify the OVERWRITE policy was passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            assert call_args[0][1] == TEST_FILE_DATA  # Second positional argument
            assert call_args[0][2] == ExistingFilePolicy.OVERWRITE  # Third positional argument

            # Verify successful return
            assert result == expected_file_path

    def test_save_static_file_fail_policy_success(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test line 230: Pass FAIL policy when file doesn't exist (success case)."""
        # Mock save_file to return a file path
        expected_file_path = "/mock/workspace/staticfiles/test_image.jpg"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_file_path

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITH FAIL policy (tests line 230)
            result = mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.FAIL)

            # Verify the FAIL policy was passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            assert call_args[0][1] == TEST_FILE_DATA  # Second positional argument
            assert call_args[0][2] == ExistingFilePolicy.FAIL  # Third positional argument

            # Verify successful return (file didn't exist so FAIL policy succeeded)
            assert result == expected_file_path

    def test_save_static_file_fail_policy_raises_file_exists_error(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test line 230: Pass FAIL policy when file exists (failure case)."""
        # Mock storage driver to raise FileExistsError (simulating file exists)
        mock_static_files_manager.storage_driver.save_file.side_effect = FileExistsError(
            f"File {TEST_FILE_NAME} already exists"
        )

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITH FAIL policy should raise FileExistsError (line 232)
            with pytest.raises(FileExistsError, match=f"File {TEST_FILE_NAME} already exists"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.FAIL)

            # Verify the FAIL policy was passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            assert call_args[0][1] == TEST_FILE_DATA  # Second positional argument
            assert call_args[0][2] == ExistingFilePolicy.FAIL  # Third positional argument

    def test_save_static_file_create_new_policy(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test line 230: Pass CREATE_NEW policy."""
        # Mock save_file to return alternative filename (storage driver handles unique filename generation)
        expected_file_path = f"/mock/workspace/staticfiles/{TEST_ALTERNATIVE_NAME}"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_file_path

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file WITH CREATE_NEW policy (tests line 230)
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.CREATE_NEW
            )

            # Verify the CREATE_NEW policy was passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            assert call_args[0][1] == TEST_FILE_DATA  # Second positional argument
            assert call_args[0][2] == ExistingFilePolicy.CREATE_NEW  # Third positional argument

            # Verify successful return with potentially modified filename
            assert TEST_ALTERNATIVE_NAME in result

    def test_save_static_file_storage_driver_exception_propagation(
        self, mock_static_files_manager: StaticFilesManager
    ) -> None:
        """Test that storage driver exceptions are propagated as RuntimeError (line 236-237)."""
        # Mock storage driver to raise a generic exception
        mock_static_files_manager.storage_driver.save_file.side_effect = RuntimeError(
            "Storage driver connection failed"
        )

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file should propagate exception as RuntimeError (line 237)
            with pytest.raises(RuntimeError, match="Failed to save static file"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE)

            # Verify storage driver was called before exception
            mock_static_files_manager.storage_driver.save_file.assert_called_once()

    def test_save_static_file_http_upload_failure(
        self, mock_static_files_manager: StaticFilesManager, mock_upload_response: dict[str, Any]
    ) -> None:
        """Test generic exception handling (non-FileExistsError exceptions wrapped in RuntimeError)."""
        # Mock storage driver to raise a generic exception (simulating upload failure)
        mock_static_files_manager.storage_driver.save_file.side_effect = ValueError("Upload failed")

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file should wrap generic exception in RuntimeError (line 237)
            with pytest.raises(RuntimeError, match="Failed to save static file"):
                mock_static_files_manager.save_static_file(TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.OVERWRITE)

            # Verify storage driver was called
            mock_static_files_manager.storage_driver.save_file.assert_called_once()

    def test_save_static_file_complete_success_flow(
        self,
        mock_static_files_manager: StaticFilesManager,
        mock_upload_response: dict[str, Any],
        mock_download_url: str,
    ) -> None:
        """Test end-to-end success path with new policy parameter."""
        # Mock save_file to return a file path with alternative filename
        expected_file_path = f"/mock/workspace/staticfiles/{TEST_ALTERNATIVE_NAME}"
        mock_static_files_manager.storage_driver.save_file.return_value = expected_file_path

        with patch.object(mock_static_files_manager, "_get_static_files_directory", return_value="staticfiles"):
            # Call save_static_file with CREATE_NEW policy for full flow test
            result = mock_static_files_manager.save_static_file(
                TEST_FILE_DATA, TEST_FILE_NAME, ExistingFilePolicy.CREATE_NEW
            )

            # Verify complete workflow
            # 1. Policy passed to storage driver (line 230)
            mock_static_files_manager.storage_driver.save_file.assert_called_once()
            call_args = mock_static_files_manager.storage_driver.save_file.call_args
            # Verify first positional argument is the file path
            assert "staticfiles" in str(call_args[0][0])
            assert TEST_FILE_NAME in str(call_args[0][0])
            # Verify second positional argument is the file data
            assert call_args[0][1] == TEST_FILE_DATA
            # Verify third positional argument is the policy
            assert call_args[0][2] == ExistingFilePolicy.CREATE_NEW

            # 2. Correct file path returned
            assert result == expected_file_path
            assert TEST_ALTERNATIVE_NAME in result
