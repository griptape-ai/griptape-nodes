"""Tests for enhanced WriteFileRequest functionality.

Tests cover:
- CREATE_NEW with WARNING-level ResultDetails when falling back to indexed filename
- CREATE_NEW first-try success without fallback warning
- Blanket exception handling for unexpected errors
- Match/case error message formatting for parent directory failures
- On-demand candidate generation (doesn't pre-generate all MAX_INDEXED_CANDIDATES)
"""

import logging
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from griptape_nodes.common.macro_parser import ParsedMacro
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    FileIOFailureReason,
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestCreateNewWarningLevelResultDetails:
    """Test CREATE_NEW policy with WARNING-level ResultDetails on fallback."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_create_new_fallback_warning_level(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW returns WARNING-level ResultDetails when falling back to indexed path."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"

        # Create the originally requested file so CREATE_NEW must fall back
        file_path.write_text("Original file")

        request = WriteFileRequest(
            file_path=str(file_path),
            content="New content",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        result = os_manager.on_write_file_request(request)

        # Should succeed but with indexed filename
        assert isinstance(result, WriteFileResultSuccess)
        assert result.final_file_path != str(file_path)  # Different from requested
        assert (temp_dir / "test_1.txt").exists()

        # Check ResultDetails is WARNING level
        assert isinstance(result.result_details, ResultDetails)
        assert len(result.result_details.result_details) == 1
        detail = result.result_details.result_details[0]
        assert detail.level == logging.WARNING
        assert "indexed path" in detail.message.lower()
        assert "already existed" in detail.message.lower()
        assert str(file_path) in detail.message or "test.txt" in detail.message

    def test_create_new_first_try_no_warning(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW returns normal success (not WARNING) when first-try succeeds."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "newfile.txt"

        # Don't create the file - let CREATE_NEW succeed on first try
        request = WriteFileRequest(
            file_path=str(file_path),
            content="Content",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        result = os_manager.on_write_file_request(request)

        # Should succeed with requested filename
        assert isinstance(result, WriteFileResultSuccess)
        assert Path(result.final_file_path).resolve() == file_path.resolve()

        # result_details should be DEBUG level (not WARNING)
        assert isinstance(result.result_details, ResultDetails)
        assert len(result.result_details.result_details) == 1
        detail = result.result_details.result_details[0]
        assert detail.level == logging.DEBUG  # Normal success is DEBUG, not WARNING
        assert "successfully" in detail.message.lower()

    def test_create_new_fallback_multiple_times(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW generates multiple WARNING messages for multiple fallbacks."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "output.txt"

        # Create original file
        file_path.write_text("Original")

        # First fallback - should get test_1.txt with WARNING
        request1 = WriteFileRequest(
            file_path=str(file_path),
            content="Content 1",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result1 = os_manager.on_write_file_request(request1)
        assert isinstance(result1, WriteFileResultSuccess)
        assert isinstance(result1.result_details, ResultDetails)
        assert result1.result_details.result_details[0].level == logging.WARNING

        # Second fallback - should get test_2.txt with WARNING
        request2 = WriteFileRequest(
            file_path=str(file_path),
            content="Content 2",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )
        result2 = os_manager.on_write_file_request(request2)
        assert isinstance(result2, WriteFileResultSuccess)
        assert isinstance(result2.result_details, ResultDetails)
        assert result2.result_details.result_details[0].level == logging.WARNING


class TestBlanketExceptionHandling:
    """Test blanket exception handlers catch unexpected errors."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_blanket_exception_on_path_resolution(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test blanket exception handler for unexpected error during path resolution."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content")

        # Mock _resolve_file_path to raise unexpected exception (not ValueError/RuntimeError)
        with patch.object(os_manager, "_resolve_file_path", side_effect=TypeError("Unexpected type error")):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR
        assert isinstance(result.result_details, ResultDetails)
        assert "unexpected error" in result.result_details.result_details[0].message.lower()

    def test_blanket_exception_on_write_operation(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test blanket exception handler for unexpected error during write."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content")

        # Mock _write_with_portalocker to raise unexpected exception (not FileExistsError or LockException)
        with patch.object(os_manager, "_write_with_portalocker", side_effect=OSError("Unexpected I/O error")):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR
        assert isinstance(result.result_details, ResultDetails)
        assert "unexpected error" in result.result_details.result_details[0].message.lower()

    def test_blanket_exception_on_macro_resolution_in_candidate_loop(
        self, griptape_nodes: GriptapeNodes, temp_dir: Path
    ) -> None:
        """Test blanket exception handler for unexpected error during CREATE_NEW macro resolution."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "output.txt"

        # Create original file to trigger CREATE_NEW fallback
        file_path.write_text("Original")

        request = WriteFileRequest(
            file_path=str(file_path),
            content="Content",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        # Mock ParsedMacro.resolve to raise unexpected exception during candidate generation

        def mock_resolve(_self: ParsedMacro, *_args: object, **_kwargs: object) -> str:
            # Raise unexpected exception on first call (during candidate generation)
            msg = "Unexpected type error in macro resolution"
            raise TypeError(msg)

        with patch.object(ParsedMacro, "resolve", mock_resolve):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR
        assert isinstance(result.result_details, ResultDetails)
        assert "unexpected error" in result.result_details.result_details[0].message.lower()


class TestParentDirectoryMatchCase:
    """Test match/case error messages for parent directory failures."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_parent_directory_permission_denied_message(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test match/case generates correct message for PERMISSION_DENIED."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "subdir" / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=True)

        # Mock _ensure_parent_directory_ready to return PERMISSION_DENIED
        with patch.object(
            os_manager, "_ensure_parent_directory_ready", return_value=FileIOFailureReason.PERMISSION_DENIED
        ):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.PERMISSION_DENIED
        assert isinstance(result.result_details, ResultDetails)
        message = result.result_details.result_details[0].message
        assert "permission denied" in message.lower()
        assert "parent directory" in message.lower()

    def test_parent_directory_no_create_message(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test match/case generates correct message for POLICY_NO_CREATE_PARENT_DIRS."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "nonexistent" / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=False)

        result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.POLICY_NO_CREATE_PARENT_DIRS
        assert isinstance(result.result_details, ResultDetails)
        message = result.result_details.result_details[0].message
        # Message includes "parent directory does not exist" or similar phrasing
        assert "parent directory" in message.lower()
        assert "not exist" in message.lower() or "does not exist" in message.lower()

    def test_parent_directory_generic_io_error_message(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test match/case default case generates generic error message."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "subdir" / "test.txt"

        request = WriteFileRequest(file_path=str(file_path), content="Content", create_parents=True)

        # Mock _ensure_parent_directory_ready to return IO_ERROR (not permission or policy)
        with patch.object(os_manager, "_ensure_parent_directory_ready", return_value=FileIOFailureReason.IO_ERROR):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason == FileIOFailureReason.IO_ERROR
        assert isinstance(result.result_details, ResultDetails)
        message = result.result_details.result_details[0].message
        assert "error creating parent directory" in message.lower()


class TestOnDemandCandidateGeneration:
    """Test that CREATE_NEW generates candidates on-demand, not all upfront."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(autouse=True)
    def setup_workspace(self, temp_dir: Path, griptape_nodes: GriptapeNodes) -> Generator[None, None, None]:
        """Automatically set workspace to temp_dir for all tests."""
        original_workspace = griptape_nodes.ConfigManager().workspace_path
        griptape_nodes.ConfigManager().workspace_path = temp_dir
        yield
        griptape_nodes.ConfigManager().workspace_path = original_workspace

    def test_on_demand_generation_early_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW only resolves macros until it finds available filename."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "output.txt"

        # CREATE_NEW always tries the first-try path first (without index)
        # So create files output.txt, output_1.txt, output_2.txt, output_3.txt, output_4.txt
        # Leave output_5.txt available
        file_path.write_text("Original")  # output.txt
        for i in range(1, 5):
            (temp_dir / f"output_{i}.txt").write_text(f"File {i}")

        request = WriteFileRequest(
            file_path=str(file_path),
            content="File 5",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        # Track how many times macro resolution is called
        resolve_call_count = 0
        original_resolve = ParsedMacro.resolve

        def counting_resolve(self: ParsedMacro, *args: object, **kwargs: object) -> str:  # type: ignore[misc]
            nonlocal resolve_call_count
            resolve_call_count += 1
            return original_resolve(self, *args, **kwargs)  # type: ignore[arg-type]

        with patch.object(ParsedMacro, "resolve", counting_resolve):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)
        assert (temp_dir / "output_5.txt").exists()

        # Should only resolve macros for candidates we actually need to try, not all 1000
        # (May include scanning calls, but definitely not 1000)
        max_expected_resolutions = 100
        min_expected_resolutions = 1
        assert resolve_call_count < max_expected_resolutions, (
            f"Expected < {max_expected_resolutions} macro resolutions, got {resolve_call_count}"
        )
        assert resolve_call_count >= min_expected_resolutions, (
            f"Expected >= {min_expected_resolutions} macro resolution, got {resolve_call_count}"
        )

    def test_on_demand_generation_stops_on_success(self, griptape_nodes: GriptapeNodes, temp_dir: Path) -> None:
        """Test CREATE_NEW stops generating candidates immediately after successful write."""
        os_manager = griptape_nodes.OSManager()
        file_path = temp_dir / "test.txt"

        # Create original file to trigger fallback
        file_path.write_text("Original")

        request = WriteFileRequest(
            file_path=str(file_path),
            content="New content",
            existing_file_policy=ExistingFilePolicy.CREATE_NEW,
        )

        # Track _write_with_portalocker calls
        write_attempts = []
        original_write = os_manager._write_with_portalocker

        def tracking_write(*args: object, **kwargs: object) -> int:  # type: ignore[misc]
            write_attempts.append(args[0] if args else None)  # Track the path
            return original_write(*args, **kwargs)  # type: ignore[arg-type]

        with patch.object(os_manager, "_write_with_portalocker", tracking_write):
            result = os_manager.on_write_file_request(request)

        assert isinstance(result, WriteFileResultSuccess)

        # Should only have 2 write attempts: original path (fails), then test_1.txt (succeeds)
        expected_attempts = 2
        assert len(write_attempts) == expected_attempts, (
            f"Expected {expected_attempts} write attempts, got {len(write_attempts)}"
        )
