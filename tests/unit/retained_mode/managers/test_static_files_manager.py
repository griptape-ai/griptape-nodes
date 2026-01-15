import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.common.project_templates.situation import SituationFilePolicy, SituationPolicy, SituationTemplate
from griptape_nodes.retained_mode.events.os_events import ExistingFilePolicy
from griptape_nodes.retained_mode.events.project_events import (
    GetPathForMacroResultFailure,
    GetPathForMacroResultSuccess,
    GetSituationResultFailure,
    GetSituationResultSuccess,
    MacroPath,
    PathResolutionFailureReason,
)
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


class TestStaticFilesManagerExtractFileVariables:
    """Test StaticFilesManager._extract_file_variables() method."""

    @pytest.fixture
    def manager(self, mock_config_manager: Mock, mock_secrets_manager: Mock) -> StaticFilesManager:
        """Create StaticFilesManager for testing."""
        with patch("griptape_nodes.retained_mode.managers.static_files_manager.LocalStorageDriver"):
            return StaticFilesManager(
                config_manager=mock_config_manager, secrets_manager=mock_secrets_manager, event_manager=None
            )

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

    def test_extract_file_variables_simple_extension(self, manager: StaticFilesManager) -> None:
        """Test extracting variables from filename with simple extension."""
        result = manager._extract_file_variables("output.png")

        assert result["file_name_base"] == "output"
        assert result["file_extension"] == "png"

    def test_extract_file_variables_multiple_dots(self, manager: StaticFilesManager) -> None:
        """Test extracting variables from filename with multiple dots."""
        result = manager._extract_file_variables("my.file.name.png")

        assert result["file_name_base"] == "my.file.name"
        assert result["file_extension"] == "png"

    def test_extract_file_variables_no_extension(self, manager: StaticFilesManager) -> None:
        """Test extracting variables from filename with no extension."""
        result = manager._extract_file_variables("README")

        assert result["file_name_base"] == "README"
        assert result["file_extension"] == ""

    def test_extract_file_variables_hidden_file(self, manager: StaticFilesManager) -> None:
        """Test extracting variables from hidden file (Path.stem behavior).

        Note: Path(".gitignore").stem returns ".gitignore" and Path(".gitignore").suffix returns "".
        This is standard Python pathlib behavior for hidden files.
        """
        result = manager._extract_file_variables(".gitignore")

        assert result["file_name_base"] == ".gitignore"
        assert result["file_extension"] == ""

    def test_extract_file_variables_various_extensions(self, manager: StaticFilesManager) -> None:
        """Test extracting variables from filenames with various extensions."""
        test_cases = [
            ("image.jpg", {"file_name_base": "image", "file_extension": "jpg"}),
            ("doc.pdf", {"file_name_base": "doc", "file_extension": "pdf"}),
            ("video.mp4", {"file_name_base": "video", "file_extension": "mp4"}),
        ]

        for filename, expected in test_cases:
            result = manager._extract_file_variables(filename)
            assert result == expected, f"Failed for {filename}"


class TestStaticFilesManagerMapSituationPolicyToFilePolicy:
    """Test StaticFilesManager._map_situation_policy_to_file_policy() method."""

    @pytest.fixture
    def manager(self, mock_config_manager: Mock, mock_secrets_manager: Mock) -> StaticFilesManager:
        """Create StaticFilesManager for testing."""
        with patch("griptape_nodes.retained_mode.managers.static_files_manager.LocalStorageDriver"):
            return StaticFilesManager(
                config_manager=mock_config_manager, secrets_manager=mock_secrets_manager, event_manager=None
            )

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

    def test_map_policy_create_new_success(self, manager: StaticFilesManager) -> None:
        """Test mapping CREATE_NEW policy succeeds."""
        result = manager._map_situation_policy_to_file_policy(SituationFilePolicy.CREATE_NEW)

        assert result == ExistingFilePolicy.CREATE_NEW

    def test_map_policy_overwrite_success(self, manager: StaticFilesManager) -> None:
        """Test mapping OVERWRITE policy succeeds."""
        result = manager._map_situation_policy_to_file_policy(SituationFilePolicy.OVERWRITE)

        assert result == ExistingFilePolicy.OVERWRITE

    def test_map_policy_fail_success(self, manager: StaticFilesManager) -> None:
        """Test mapping FAIL policy succeeds."""
        result = manager._map_situation_policy_to_file_policy(SituationFilePolicy.FAIL)

        assert result == ExistingFilePolicy.FAIL

    def test_map_policy_prompt_raises_value_error(self, manager: StaticFilesManager) -> None:
        """Test mapping PROMPT policy raises ValueError."""
        with pytest.raises(ValueError, match="Cannot map PROMPT policy"):
            manager._map_situation_policy_to_file_policy(SituationFilePolicy.PROMPT)

    def test_map_policy_unknown_raises_value_error(self, manager: StaticFilesManager) -> None:
        """Test mapping unknown policy raises ValueError."""
        mock_policy = Mock()
        mock_policy.name = "UNKNOWN_POLICY"

        with pytest.raises(ValueError, match="Unknown situation policy"):
            manager._map_situation_policy_to_file_policy(mock_policy)


class TestStaticFilesManagerResolveMacroPath:
    """Test StaticFilesManager._resolve_macro_path() method."""

    @pytest.fixture
    def manager(self, mock_config_manager: Mock, mock_secrets_manager: Mock) -> StaticFilesManager:
        """Create StaticFilesManager for testing."""
        with patch("griptape_nodes.retained_mode.managers.static_files_manager.LocalStorageDriver"):
            return StaticFilesManager(
                config_manager=mock_config_manager, secrets_manager=mock_secrets_manager, event_manager=None
            )

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

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_macro_path_success(self, mock_griptape_nodes: Mock, manager: StaticFilesManager) -> None:
        """Test successful macro path resolution."""
        mock_result = GetPathForMacroResultSuccess(
            resolved_path=Path("/workspace/output.png"),
            absolute_path=Path("/workspace/output.png"),
            result_details="Success",
        )
        mock_griptape_nodes.handle_request.return_value = mock_result

        parsed_macro = ParsedMacro("{workflow_dir}/output.png")
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        result = manager._resolve_macro_path(macro_path)

        assert result == Path("/workspace/output.png")
        mock_griptape_nodes.handle_request.assert_called_once()

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_macro_path_result_failed_raises_value_error(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that failed result raises ValueError."""
        mock_result = GetPathForMacroResultFailure(
            failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR, result_details="Test failure"
        )
        mock_griptape_nodes.handle_request.return_value = mock_result

        parsed_macro = ParsedMacro("{workflow_dir}/output.png")
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        with pytest.raises(ValueError, match="Failed to resolve macro path"):
            manager._resolve_macro_path(macro_path)

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_macro_path_wrong_result_type_raises_type_error(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that wrong result type raises TypeError."""
        mock_result = Mock()
        mock_result.failed.return_value = False
        mock_griptape_nodes.handle_request.return_value = mock_result

        parsed_macro = ParsedMacro("{workflow_dir}/output.png")
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        with pytest.raises(TypeError, match="Unexpected result type"):
            manager._resolve_macro_path(macro_path)

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_macro_path_empty_path_raises_value_error(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that empty path raises ValueError."""
        mock_result = Mock(spec=GetPathForMacroResultSuccess)
        mock_result.failed.return_value = False
        mock_result.absolute_path = None
        mock_griptape_nodes.handle_request.return_value = mock_result

        parsed_macro = ParsedMacro("{workflow_dir}/output.png")
        macro_path = MacroPath(parsed_macro=parsed_macro, variables={})

        with pytest.raises(ValueError, match="Macro resolved to empty path"):
            manager._resolve_macro_path(macro_path)


class TestStaticFilesManagerResolvePathViaSituation:
    """Test StaticFilesManager._resolve_path_via_situation() method."""

    @pytest.fixture
    def manager(self, mock_config_manager: Mock, mock_secrets_manager: Mock) -> StaticFilesManager:
        """Create StaticFilesManager for testing."""
        with patch("griptape_nodes.retained_mode.managers.static_files_manager.LocalStorageDriver"):
            return StaticFilesManager(
                config_manager=mock_config_manager, secrets_manager=mock_secrets_manager, event_manager=None
            )

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

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_path_via_situation_success(self, mock_griptape_nodes: Mock, manager: StaticFilesManager) -> None:
        """Test successful situation-based path resolution."""
        situation = SituationTemplate(
            name="save_file",
            description="Save file",
            macro="{workflow_dir}/staticfiles/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.CREATE_NEW, create_dirs=True),
            fallback=None,
        )
        situation_result = GetSituationResultSuccess(situation=situation, result_details="Success")

        path_result = GetPathForMacroResultSuccess(
            resolved_path=Path("/workspace/workflows/staticfiles/output.png"),
            absolute_path=Path("/workspace/workflows/staticfiles/output.png"),
            result_details="Success",
        )

        mock_griptape_nodes.handle_request.side_effect = [situation_result, path_result]

        resolved_path, effective_policy = manager._resolve_path_via_situation(
            situation_name="save_file", file_name="output.png", variables=None
        )

        assert resolved_path == Path("/workspace/workflows/staticfiles/output.png")
        assert effective_policy == ExistingFilePolicy.CREATE_NEW

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_path_via_situation_not_found_fails(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that situation not found raises ValueError."""
        situation_result = GetSituationResultFailure(result_details="Situation not found")
        mock_griptape_nodes.handle_request.return_value = situation_result

        with pytest.raises(ValueError, match="Failed to get situation"):
            manager._resolve_path_via_situation(
                situation_name="missing_situation", file_name="output.png", variables=None
            )

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_path_via_situation_wrong_result_type_fails(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that wrong result type raises TypeError."""
        mock_result = Mock()
        mock_result.failed.return_value = False
        mock_griptape_nodes.handle_request.return_value = mock_result

        with pytest.raises(TypeError, match="Unexpected result type"):
            manager._resolve_path_via_situation(situation_name="save_file", file_name="output.png", variables=None)

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_path_via_situation_prompt_policy_fails(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that PROMPT policy raises ValueError."""
        situation = SituationTemplate(
            name="save_preview",
            description="Save preview",
            macro="{workflow_dir}/previews/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.PROMPT, create_dirs=True),
            fallback=None,
        )
        situation_result = GetSituationResultSuccess(situation=situation, result_details="Success")

        path_result = GetPathForMacroResultSuccess(
            resolved_path=Path("/workspace/previews/output.png"),
            absolute_path=Path("/workspace/previews/output.png"),
            result_details="Success",
        )

        mock_griptape_nodes.handle_request.side_effect = [situation_result, path_result]

        with pytest.raises(ValueError, match="Cannot map PROMPT policy"):
            manager._resolve_path_via_situation(situation_name="save_preview", file_name="output.png", variables=None)

    @patch("griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes")
    def test_resolve_path_via_situation_macro_resolution_fails(
        self, mock_griptape_nodes: Mock, manager: StaticFilesManager
    ) -> None:
        """Test that macro resolution failure raises ValueError."""
        situation = SituationTemplate(
            name="save_file",
            description="Save file",
            macro="{workflow_dir}/staticfiles/{file_name_base}.{file_extension}",
            policy=SituationPolicy(on_collision=SituationFilePolicy.CREATE_NEW, create_dirs=True),
            fallback=None,
        )
        situation_result = GetSituationResultSuccess(situation=situation, result_details="Success")

        path_result = GetPathForMacroResultFailure(
            failure_reason=PathResolutionFailureReason.MACRO_RESOLUTION_ERROR, result_details="Missing variable"
        )

        mock_griptape_nodes.handle_request.side_effect = [situation_result, path_result]

        with pytest.raises(ValueError, match="Failed to resolve macro path"):
            manager._resolve_path_via_situation(situation_name="save_file", file_name="output.png", variables=None)
