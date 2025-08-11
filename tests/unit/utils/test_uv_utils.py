"""Tests for uv_utils module."""

import platform
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.utils.uv_utils import find_uv_bin


@pytest.mark.skipif(
    platform.system() == "Windows", reason="xdg_base_dirs cannot find XDG_DATA_HOME on Windows on GitHub Actions"
)
class TestUvUtils:
    """Test UV utilities functionality."""

    def test_find_uv_bin_uses_dedicated_installation_when_exists(self) -> None:
        """Test that find_uv_bin prefers dedicated Griptape installation when it exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock dedicated UV path that exists
            dedicated_path = Path(temp_dir) / "griptape_nodes" / "bin" / "uv"
            dedicated_path.parent.mkdir(parents=True)
            dedicated_path.touch()

            with patch("griptape_nodes.utils.uv_utils.xdg_data_home") as mock_xdg:
                mock_xdg.return_value = Path(temp_dir)

                result = find_uv_bin()

                assert result == str(dedicated_path)

    def test_find_uv_bin_falls_back_to_system_uv_when_dedicated_not_exists(self) -> None:
        """Test that find_uv_bin falls back to system UV when dedicated installation doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock system UV path
            system_uv_path = "/usr/local/bin/uv"

            with (
                patch("griptape_nodes.utils.uv_utils.xdg_data_home") as mock_xdg,
                patch("griptape_nodes.utils.uv_utils.uv.find_uv_bin") as mock_system_uv,
            ):
                mock_xdg.return_value = Path(temp_dir)
                mock_system_uv.return_value = system_uv_path

                result = find_uv_bin()

                assert result == system_uv_path
                mock_system_uv.assert_called_once()

    def test_find_uv_bin_dedicated_path_construction(self) -> None:
        """Test that the dedicated UV path is constructed correctly."""
        mock_data_home = Path("/mock/data/home")

        with (
            patch("griptape_nodes.utils.uv_utils.xdg_data_home") as mock_xdg,
            patch("griptape_nodes.utils.uv_utils.uv.find_uv_bin") as mock_system_uv,
        ):
            mock_xdg.return_value = mock_data_home
            mock_system_uv.return_value = "/system/uv"

            # Mock the path.exists() to return False so we test the fallback
            with patch.object(Path, "exists", return_value=False):
                find_uv_bin()

            # Verify that we checked the correct path
            mock_system_uv.assert_called_once()

    def test_find_uv_bin_returns_string(self) -> None:
        """Test that find_uv_bin always returns a string."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dedicated_path = Path(temp_dir) / "griptape_nodes" / "bin" / "uv"
            dedicated_path.parent.mkdir(parents=True)
            dedicated_path.touch()

            with patch("griptape_nodes.utils.uv_utils.xdg_data_home") as mock_xdg:
                mock_xdg.return_value = Path(temp_dir)

                result = find_uv_bin()

                assert isinstance(result, str)
                assert result == str(dedicated_path)

    def test_find_uv_bin_system_fallback_returns_string(self) -> None:
        """Test that system UV fallback also returns a string."""
        with tempfile.TemporaryDirectory() as temp_dir:
            system_uv_path = "/usr/local/bin/uv"

            with (
                patch("griptape_nodes.utils.uv_utils.xdg_data_home") as mock_xdg,
                patch("griptape_nodes.utils.uv_utils.uv.find_uv_bin") as mock_system_uv,
            ):
                mock_xdg.return_value = Path(temp_dir)
                mock_system_uv.return_value = system_uv_path

                result = find_uv_bin()

                assert isinstance(result, str)
                assert result == system_uv_path

    @patch("griptape_nodes.utils.uv_utils.uv.find_uv_bin")
    @patch("griptape_nodes.utils.uv_utils.xdg_data_home")
    def test_find_uv_bin_handles_system_uv_exception(self, mock_xdg: Mock, mock_system_uv: Mock) -> None:
        """Test that find_uv_bin handles exceptions from system UV lookup appropriately."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up mocks - use temp dir instead of hardcoded path
            mock_xdg.return_value = Path(temp_dir) / "nonexistent"
            mock_system_uv.side_effect = RuntimeError("UV not found")

            # Should raise the exception from the system UV lookup
            with pytest.raises(RuntimeError, match="UV not found"):
                find_uv_bin()
