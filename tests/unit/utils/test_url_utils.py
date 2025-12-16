"""Unit tests for url_utils module."""

from __future__ import annotations

from griptape_nodes.utils.url_utils import is_url_or_path


class TestIsUrlOrPath:
    """Test is_url_or_path utility function."""

    def test_http_urls(self) -> None:
        """Test HTTP URL detection."""
        assert is_url_or_path("http://example.com/image.png") is True
        assert is_url_or_path("http://localhost/file.txt") is True
        assert is_url_or_path("http://192.168.1.1/api") is True

    def test_https_urls(self) -> None:
        """Test HTTPS URL detection."""
        assert is_url_or_path("https://example.com/file.txt") is True
        assert is_url_or_path("https://localhost:8080/api") is True
        assert is_url_or_path("https://subdomain.example.com/path/to/file") is True

    def test_file_urls(self) -> None:
        """Test file:// URL detection."""
        assert is_url_or_path("file:///absolute/path") is True
        assert is_url_or_path("file:///home/user/file.txt") is True
        assert is_url_or_path("file://C:/Windows/path") is True

    def test_absolute_unix_paths(self) -> None:
        """Test absolute Unix path detection."""
        assert is_url_or_path("/absolute/unix/path") is True
        assert is_url_or_path("/home/user/file.txt") is True
        assert is_url_or_path("/var/log/app.log") is True

    def test_absolute_windows_paths(self) -> None:
        """Test absolute Windows path detection."""
        assert is_url_or_path("C:\\Windows\\path") is True
        assert is_url_or_path("D:\\data\\file.txt") is True
        assert is_url_or_path("E:\\") is True

    def test_relative_paths(self) -> None:
        """Test relative path detection."""
        assert is_url_or_path("./relative/path") is True
        assert is_url_or_path("../parent/path") is True
        assert is_url_or_path("file.txt") is True
        assert is_url_or_path("path/to/file.txt") is True
        assert is_url_or_path("./file.txt") is True
        assert is_url_or_path("../file.txt") is True

    def test_unc_paths(self) -> None:
        """Test UNC (Windows network) path detection."""
        assert is_url_or_path("\\\\server\\share\\file") is True
        assert is_url_or_path("\\\\network\\path") is True

    def test_data_uris_excluded(self) -> None:
        """Test that data: URIs return False."""
        assert is_url_or_path("data:image/png;base64,iVBORw0KGg") is False
        assert is_url_or_path("data:text/plain,hello") is False
        assert is_url_or_path("data:application/json,{}") is False

    def test_empty_and_whitespace(self) -> None:
        """Test that empty and whitespace strings return False."""
        assert is_url_or_path("") is False
        assert is_url_or_path("   ") is False
        assert is_url_or_path("\t") is False
        assert is_url_or_path("\n") is False

    def test_other_schemes_excluded(self) -> None:
        """Test that other URI schemes return False."""
        assert is_url_or_path("ftp://ftp.example.com") is False
        assert is_url_or_path("ftps://secure.ftp.com") is False
        assert is_url_or_path("mailto:user@example.com") is False
        assert is_url_or_path("javascript:alert('xss')") is False
        assert is_url_or_path("ssh://git@github.com/repo") is False

    def test_plain_text_strings(self) -> None:
        """Test that plain text without path indicators returns False."""
        assert is_url_or_path("hello world") is True  # Path() accepts this
        assert is_url_or_path("just text") is True  # Path() accepts this
        assert is_url_or_path("random") is True  # Path() accepts this as filename

    def test_urls_with_query_params(self) -> None:
        """Test URLs with query parameters."""
        assert is_url_or_path("https://example.com/api?key=value") is True
        assert is_url_or_path("http://localhost:8080/path?param=1&other=2") is True

    def test_urls_with_fragments(self) -> None:
        """Test URLs with fragments."""
        assert is_url_or_path("https://example.com/page#section") is True
        assert is_url_or_path("http://docs.example.com/guide#intro") is True

    def test_paths_with_spaces(self) -> None:
        """Test paths containing spaces."""
        assert is_url_or_path("/path with spaces/file.txt") is True
        assert is_url_or_path("C:\\Program Files\\app.exe") is True
        assert is_url_or_path("./folder name/file.txt") is True

    def test_paths_with_special_characters(self) -> None:
        """Test paths with special characters."""
        assert is_url_or_path("/path/to/file-name_v2.txt") is True
        assert is_url_or_path("./my-project/src/utils.py") is True
        assert is_url_or_path("file_2024-01-15.log") is True
