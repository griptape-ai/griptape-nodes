from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.servers.static import _serve_external_file


class TestServeExternalFile:
    """Test _serve_external_file() path reconstruction."""

    @pytest.mark.anyio
    async def test_unix_path_reconstruction(self, tmp_path: Path) -> None:
        """Unix-style paths (no drive letter) should get a leading slash prepended."""
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"fake png")

        # Strip the leading slash, as the URL router would
        file_path_in_url = str(test_file).removeprefix("/")

        with patch("griptape_nodes.servers.static.STATIC_SERVER_ENABLED", True):
            response = await _serve_external_file(file_path_in_url)

        assert Path(response.path) == test_file

    @pytest.mark.anyio
    async def test_windows_drive_letter_path_reconstruction(self) -> None:
        """Windows-style paths with drive letters (e.g., C:/...) should NOT get a leading slash prepended."""
        # Simulate a Windows path coming through the URL: "C:/Users/foo/image.png"
        # We can't create an actual Windows path on macOS/Linux, but we can test the path reconstruction logic.
        # The key assertion is that the function doesn't prepend "/" to a drive-letter path.
        windows_style_path = "C:/Users/foo/image.png"

        with (
            patch("griptape_nodes.servers.static.STATIC_SERVER_ENABLED", True),
            patch("griptape_nodes.servers.static.anyio.Path") as mock_anyio_path,
            patch("griptape_nodes.servers.static.FileResponse") as mock_response,
        ):
            mock_path_instance = AsyncMock()
            mock_path_instance.exists.return_value = True
            mock_path_instance.is_file.return_value = True
            mock_anyio_path.return_value = mock_path_instance

            await _serve_external_file(windows_style_path)

            # The path passed to FileResponse should be C:/Users/foo/image.png, NOT /C:/Users/foo/image.png
            call_args = mock_response.call_args[0][0]
            assert str(call_args) != "/C:/Users/foo/image.png"
            assert "C:" in str(call_args)
