from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from griptape_nodes.servers.static import _serve_external_file


class TestServeExternalFile:
    """Test _serve_external_file() path reconstruction."""

    @pytest.mark.asyncio
    async def test_unix_path_reconstruction(self, tmp_path: Path) -> None:
        """Unix-style paths (no drive letter) should get a leading slash prepended."""
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"fake png")

        # Strip the leading slash, as the URL router would
        file_path_in_url = str(test_file).removeprefix("/")

        with patch("griptape_nodes.servers.static.STATIC_SERVER_ENABLED", True):
            response = await _serve_external_file(file_path_in_url)

        assert Path(response.path) == test_file

    @pytest.mark.asyncio
    async def test_absolute_path_not_prepended_with_slash(self) -> None:
        """Paths that are already absolute should not get a leading slash prepended."""
        # On Windows, Path("C:/Users/foo/image.png") is already absolute.
        # Prepending "/" would produce "\C:\Users\..." which is invalid.
        # We simulate this by patching Path.is_absolute to return True.
        already_absolute_path = "C:/Users/foo/image.png"

        with (
            patch("griptape_nodes.servers.static.STATIC_SERVER_ENABLED", True),
            patch("griptape_nodes.servers.static.Path") as mock_path_cls,
            patch("griptape_nodes.servers.static.anyio.Path") as mock_anyio_path,
            patch("griptape_nodes.servers.static.FileResponse") as mock_response,
        ):
            mock_candidate = mock_path_cls.return_value
            mock_candidate.is_absolute.return_value = True
            mock_anyio_instance = AsyncMock()
            mock_anyio_instance.exists.return_value = True
            mock_anyio_instance.is_file.return_value = True
            mock_anyio_path.return_value = mock_anyio_instance

            await _serve_external_file(already_absolute_path)

            # Path() should have been called with the raw path, not with "/" prepended
            mock_path_cls.assert_called_once_with(already_absolute_path)
            mock_response.assert_called_once_with(mock_candidate)
