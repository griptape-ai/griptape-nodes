from pathlib import Path
from unittest.mock import patch

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
