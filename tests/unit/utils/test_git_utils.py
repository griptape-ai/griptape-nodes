"""Tests for git_utils module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from griptape_nodes.utils.git_utils import (
    GitUrlComponents,
    clone_subdirectory,
    is_git_url,
    parse_git_url,
    sanitize_repo_name,
)


class TestGitUrlComponents:
    """Test GitUrlComponents dataclass."""

    def test_git_url_components_creation(self) -> None:
        """Test GitUrlComponents can be created with all fields."""
        components = GitUrlComponents(
            base_url="https://github.com/user/repo",
            branch="main",
            subdir="src/lib",
            url_type="directory",
            detected_from_url=True,
            filename="config.json",
        )

        assert components.base_url == "https://github.com/user/repo"
        assert components.branch == "main"
        assert components.subdir == "src/lib"
        assert components.url_type == "directory"
        assert components.detected_from_url is True
        assert components.filename == "config.json"

    def test_git_url_components_optional_fields(self) -> None:
        """Test GitUrlComponents with optional fields as None."""
        components = GitUrlComponents(
            base_url="https://github.com/user/repo",
            branch="main",
            subdir=None,
            url_type="repo",
            detected_from_url=False,
        )

        assert components.subdir is None
        assert components.filename is None


class TestParseGitUrl:
    """Test parse_git_url function."""

    def test_parse_github_directory_url(self) -> None:
        """Test parsing GitHub directory URL."""
        url = "https://github.com/user/repo/tree/main/src/lib"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src/lib"
        assert result.url_type == "directory"
        assert result.detected_from_url is True
        assert result.filename is None

    def test_parse_github_directory_url_no_subdir(self) -> None:
        """Test parsing GitHub directory URL without subdirectory."""
        url = "https://github.com/user/repo/tree/main"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "repo"
        assert result.detected_from_url is True

    def test_parse_github_file_url(self) -> None:
        """Test parsing GitHub file URL."""
        url = "https://github.com/user/repo/blob/main/src/config.json"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src"
        assert result.url_type == "file"
        assert result.detected_from_url is True
        assert result.filename == "config.json"

    def test_parse_github_file_url_root(self) -> None:
        """Test parsing GitHub file URL in root directory."""
        url = "https://github.com/user/repo/blob/main/config.json"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "file"
        assert result.detected_from_url is True
        assert result.filename == "config.json"

    def test_parse_gitlab_directory_url(self) -> None:
        """Test parsing GitLab directory URL."""
        url = "https://gitlab.com/user/repo/-/tree/develop/src/lib"
        result = parse_git_url(url)

        assert result.base_url == "https://gitlab.com/user/repo"
        assert result.branch == "develop"
        assert result.subdir == "src/lib"
        assert result.url_type == "directory"
        assert result.detected_from_url is True

    def test_parse_gitlab_file_url(self) -> None:
        """Test parsing GitLab file URL."""
        url = "https://gitlab.com/user/repo/-/blob/main/src/config.json"
        result = parse_git_url(url)

        assert result.base_url == "https://gitlab.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src"
        assert result.url_type == "file"
        assert result.detected_from_url is True
        assert result.filename == "config.json"

    def test_parse_bitbucket_directory_url(self) -> None:
        """Test parsing Bitbucket directory URL."""
        url = "https://bitbucket.org/user/repo/src/main/src/lib"
        result = parse_git_url(url)

        assert result.base_url == "https://bitbucket.org/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src/lib"
        assert result.url_type == "directory"
        assert result.detected_from_url is True

    def test_parse_bitbucket_json_file_url(self) -> None:
        """Test parsing Bitbucket JSON file URL (special case)."""
        url = "https://bitbucket.org/user/repo/src/main/config.json"
        result = parse_git_url(url)

        assert result.base_url == "https://bitbucket.org/user/repo"
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "file"
        assert result.detected_from_url is True
        assert result.filename == "config.json"

    def test_parse_plain_repository_url(self) -> None:
        """Test parsing plain repository URL without branch/path."""
        url = "https://github.com/user/repo"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "repo"
        assert result.detected_from_url is False

    def test_parse_plain_repository_url_with_git_suffix(self) -> None:
        """Test parsing plain repository URL with .git suffix."""
        url = "https://github.com/user/repo.git"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo.git"
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "repo"
        assert result.detected_from_url is False

    def test_parse_url_with_encoded_characters(self) -> None:
        """Test parsing URL with encoded characters."""
        url = "https://github.com/user/repo/tree/main/src%20with%20spaces"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src with spaces"
        assert result.url_type == "directory"
        assert result.detected_from_url is True

    def test_parse_url_with_trailing_slash(self) -> None:
        """Test parsing URL with trailing slash."""
        url = "https://github.com/user/repo/tree/main/src/lib/"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "src/lib"
        assert result.url_type == "directory"
        assert result.detected_from_url is True

    def test_parse_complex_branch_name(self) -> None:
        """Test parsing URL with complex branch name."""
        url = "https://github.com/user/repo/tree/feature-branch/src"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "feature-branch"
        assert result.subdir == "src"
        assert result.url_type == "directory"
        assert result.detected_from_url is True


class TestIsGitUrl:
    """Test is_git_url function."""

    def test_github_https_url(self) -> None:
        """Test GitHub HTTPS URL detection."""
        assert is_git_url("https://github.com/user/repo") is True

    def test_gitlab_https_url(self) -> None:
        """Test GitLab HTTPS URL detection."""
        assert is_git_url("https://gitlab.com/user/repo") is True

    def test_bitbucket_https_url(self) -> None:
        """Test Bitbucket HTTPS URL detection."""
        assert is_git_url("https://bitbucket.org/user/repo") is True

    def test_ssh_git_url(self) -> None:
        """Test SSH Git URL detection."""
        assert is_git_url("git@github.com:user/repo.git") is True

    def test_ssh_protocol_url(self) -> None:
        """Test SSH protocol URL detection."""
        assert is_git_url("ssh://git@github.com/user/repo.git") is True

    def test_git_extension_url(self) -> None:
        """Test URL with .git extension detection."""
        assert is_git_url("https://example.com/repo.git") is True

    def test_github_in_url(self) -> None:
        """Test URL containing github.com detection."""
        assert is_git_url("https://api.github.com/repos/user/repo") is True

    def test_gitlab_in_url(self) -> None:
        """Test URL containing gitlab.com detection."""
        assert is_git_url("https://custom.gitlab.com/user/repo") is True

    def test_bitbucket_in_url(self) -> None:
        """Test URL containing bitbucket.org detection."""
        assert is_git_url("https://api.bitbucket.org/user/repo") is True

    def test_non_git_url(self) -> None:
        """Test non-Git URL detection."""
        assert is_git_url("https://example.com/file.txt") is False

    def test_local_file_path(self) -> None:
        """Test local file path detection."""
        assert is_git_url("/path/to/local/file") is False

    def test_empty_string(self) -> None:
        """Test empty string detection."""
        assert is_git_url("") is False

    def test_relative_path(self) -> None:
        """Test relative path detection."""
        assert is_git_url("./relative/path") is False


class TestSanitizeRepoName:
    """Test sanitize_repo_name function."""

    def test_simple_repo_name(self) -> None:
        """Test sanitizing simple repository name."""
        url = "https://github.com/user/simple-repo"
        result = sanitize_repo_name(url)
        assert result == "simple-repo"

    def test_repo_name_with_git_suffix(self) -> None:
        """Test sanitizing repository name with .git suffix."""
        url = "https://github.com/user/repo.git"
        result = sanitize_repo_name(url)
        assert result == "repo"

    def test_repo_name_with_special_characters(self) -> None:
        """Test sanitizing repository name with special characters."""
        url = "https://github.com/user/repo@special#chars!"
        result = sanitize_repo_name(url)
        assert result == "repo_special_chars_"

    def test_repo_name_with_spaces(self) -> None:
        """Test sanitizing repository name with spaces."""
        url = "https://github.com/user/repo with spaces"
        result = sanitize_repo_name(url)
        assert result == "repo_with_spaces"

    def test_repo_name_preserves_valid_characters(self) -> None:
        """Test that valid characters (alphanumeric, underscore, hyphen) are preserved."""
        url = "https://github.com/user/Valid_Repo-Name123"
        result = sanitize_repo_name(url)
        assert result == "Valid_Repo-Name123"

    def test_repo_name_from_complex_path(self) -> None:
        """Test extracting repo name from complex URL path."""
        url = "https://custom-git-server.com/organization/group/repo-name"
        result = sanitize_repo_name(url)
        assert result == "repo-name"

    def test_repo_name_empty_after_sanitization(self) -> None:
        """Test handling repo name that becomes empty after sanitization."""
        url = "https://github.com/user/!!!"
        result = sanitize_repo_name(url)
        assert result == "___"

    def test_ssh_url_sanitization(self) -> None:
        """Test sanitizing SSH URL."""
        url = "git@github.com:user/repo.git"
        result = sanitize_repo_name(url)
        assert result == "repo"


class TestCloneSubdirectory:
    """Test clone_subdirectory function."""

    @patch("griptape_nodes.utils.git_utils.git.Repo")
    def test_clone_subdirectory_basic(self, mock_repo_class: Mock) -> None:
        """Test basic subdirectory cloning functionality."""
        # Set up mocks
        mock_repo = Mock()
        mock_origin = Mock()
        mock_config_writer = Mock()
        mock_ref = Mock()
        mock_head = Mock()

        mock_repo_class.init.return_value = mock_repo
        mock_repo.create_remote.return_value = mock_origin
        # Properly mock the context manager
        mock_repo.config_writer.return_value = mock_config_writer
        mock_config_writer.__enter__ = Mock(return_value=mock_config_writer)
        mock_config_writer.__exit__ = Mock(return_value=None)
        mock_origin.refs = {"main": mock_ref}
        mock_repo.create_head.return_value = mock_head
        mock_repo.heads = {"main": mock_head}

        with tempfile.TemporaryDirectory() as temp_dir:
            clone_path = Path(temp_dir) / "repo"
            git_url = "https://github.com/user/repo"
            branch = "main"
            subdir = "src/lib"

            clone_subdirectory(git_url, clone_path, branch, subdir)

            # Verify repo initialization
            mock_repo_class.init.assert_called_once_with(clone_path)

            # Verify remote creation
            mock_repo.create_remote.assert_called_once_with("origin", git_url)

            # Verify sparse checkout configuration
            mock_config_writer.set_value.assert_called_once_with("core", "sparseCheckout", "true")

            # Verify fetch and checkout
            mock_origin.fetch.assert_called_once_with(branch)
            mock_repo.create_head.assert_called_once_with(branch, mock_ref)
            mock_head.checkout.assert_called_once()

            # Verify sparse-checkout file was created
            checkout_file = clone_path / ".git" / "info" / "sparse-checkout"
            assert checkout_file.exists()
            content = checkout_file.read_text(encoding="utf-8")
            assert content.strip() == f"{subdir}/"

    @patch("griptape_nodes.utils.git_utils.git.Repo")
    def test_clone_subdirectory_creates_directories(self, mock_repo_class: Mock) -> None:
        """Test that clone_subdirectory creates necessary directories."""
        # Set up minimal mocks
        mock_repo = Mock()
        mock_origin = Mock()
        mock_config_writer = Mock()
        mock_ref = Mock()
        mock_head = Mock()

        mock_repo_class.init.return_value = mock_repo
        mock_repo.create_remote.return_value = mock_origin
        # Properly mock the context manager
        mock_repo.config_writer.return_value = mock_config_writer
        mock_config_writer.__enter__ = Mock(return_value=mock_config_writer)
        mock_config_writer.__exit__ = Mock(return_value=None)
        mock_origin.refs = {"develop": mock_ref}
        mock_repo.create_head.return_value = mock_head
        mock_repo.heads = {"develop": mock_head}

        with tempfile.TemporaryDirectory() as temp_dir:
            clone_path = Path(temp_dir) / "deep" / "nested" / "repo"
            git_url = "https://gitlab.com/user/repo"
            branch = "develop"
            subdir = "docs"

            clone_subdirectory(git_url, clone_path, branch, subdir)

            # Verify that the .git/info directory structure was created
            git_info_dir = clone_path / ".git" / "info"
            assert git_info_dir.exists()
            assert git_info_dir.is_dir()

            # Verify sparse-checkout file content
            checkout_file = git_info_dir / "sparse-checkout"
            assert checkout_file.exists()
            content = checkout_file.read_text(encoding="utf-8")
            assert content.strip() == "docs/"

    @patch("griptape_nodes.utils.git_utils.git.Repo")
    def test_clone_subdirectory_git_error_propagation(self, mock_repo_class: Mock) -> None:
        """Test that Git errors are properly propagated."""
        from git import GitCommandError

        # Set up mock to raise GitCommandError on fetch
        mock_repo = Mock()
        mock_origin = Mock()
        mock_config_writer = Mock()

        mock_repo_class.init.return_value = mock_repo
        mock_repo.create_remote.return_value = mock_origin
        # Properly mock the context manager
        mock_repo.config_writer.return_value = mock_config_writer
        mock_config_writer.__enter__ = Mock(return_value=mock_config_writer)
        mock_config_writer.__exit__ = Mock(return_value=None)
        mock_origin.fetch.side_effect = GitCommandError("fetch", "git fetch failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            clone_path = Path(temp_dir) / "repo"
            git_url = "https://github.com/user/nonexistent-repo"
            branch = "main"
            subdir = "src"

            with pytest.raises(GitCommandError, match="git fetch failed"):
                clone_subdirectory(git_url, clone_path, branch, subdir)

    @patch("griptape_nodes.utils.git_utils.git.Repo")
    def test_clone_subdirectory_with_special_characters(self, mock_repo_class: Mock) -> None:
        """Test cloning subdirectory with special characters in path."""
        # Set up mocks
        mock_repo = Mock()
        mock_origin = Mock()
        mock_config_writer = Mock()
        mock_ref = Mock()
        mock_head = Mock()

        mock_repo_class.init.return_value = mock_repo
        mock_repo.create_remote.return_value = mock_origin
        # Properly mock the context manager
        mock_repo.config_writer.return_value = mock_config_writer
        mock_config_writer.__enter__ = Mock(return_value=mock_config_writer)
        mock_config_writer.__exit__ = Mock(return_value=None)
        mock_origin.refs = {"main": mock_ref}
        mock_repo.create_head.return_value = mock_head
        mock_repo.heads = {"main": mock_head}

        with tempfile.TemporaryDirectory() as temp_dir:
            clone_path = Path(temp_dir) / "repo"
            git_url = "https://github.com/user/repo"
            branch = "main"
            subdir = "src with spaces/special-chars"

            clone_subdirectory(git_url, clone_path, branch, subdir)

            # Verify sparse-checkout file content handles special characters
            checkout_file = clone_path / ".git" / "info" / "sparse-checkout"
            content = checkout_file.read_text(encoding="utf-8")
            assert content.strip() == "src with spaces/special-chars/"


class TestPrivateHelperFunctions:
    """Test private helper functions through public interface."""

    def test_handle_file_url_through_parse_git_url(self) -> None:
        """Test _handle_file_url functionality through parse_git_url."""
        # Test with nested file path
        url = "https://github.com/user/repo/blob/main/deep/nested/path/config.json"
        result = parse_git_url(url)

        assert result.base_url == "https://github.com/user/repo"
        assert result.branch == "main"
        assert result.subdir == "deep/nested/path"
        assert result.filename == "config.json"
        assert result.url_type == "file"

    def test_handle_file_url_single_level_through_parse_git_url(self) -> None:
        """Test _handle_file_url with single-level path through parse_git_url."""
        url = "https://github.com/user/repo/blob/main/src/file.py"
        result = parse_git_url(url)

        assert result.subdir == "src"
        assert result.filename == "file.py"

    def test_handle_file_url_root_level_through_parse_git_url(self) -> None:
        """Test _handle_file_url with root-level file through parse_git_url."""
        url = "https://github.com/user/repo/blob/main/README.md"
        result = parse_git_url(url)

        assert result.subdir is None
        assert result.filename == "README.md"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_git_url_with_empty_string(self) -> None:
        """Test parsing empty string URL."""
        result = parse_git_url("")

        assert result.base_url == ""
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "repo"
        assert result.detected_from_url is False

    def test_parse_git_url_with_whitespace(self) -> None:
        """Test parsing URL with only whitespace."""
        result = parse_git_url("   ")

        assert result.base_url == "   "  # Whitespace is preserved (only rstrip("/"))
        assert result.branch == "main"
        assert result.subdir is None
        assert result.url_type == "repo"
        assert result.detected_from_url is False

    def test_sanitize_repo_name_with_empty_string(self) -> None:
        """Test sanitizing empty string URL."""
        result = sanitize_repo_name("")
        assert result == ""

    def test_sanitize_repo_name_with_only_slashes(self) -> None:
        """Test sanitizing URL with only slashes."""
        result = sanitize_repo_name("///")
        assert result == ""

    def test_is_git_url_with_none_like_values(self) -> None:
        """Test is_git_url with various falsy values."""
        # Note: These would cause AttributeError in real usage, but testing the logic
        assert is_git_url("") is False

    def test_parse_malformed_git_urls(self) -> None:
        """Test parsing malformed Git URLs."""
        malformed_urls = [
            "https://github.com/",
            "https://github.com/user",
            "https://github.com/user/",
            "github.com/user/repo",  # Missing protocol
        ]

        for url in malformed_urls:
            result = parse_git_url(url)
            # Should fall back to repo type with main branch
            assert result.branch == "main"
            assert result.url_type == "repo"
            assert result.detected_from_url is False

    def test_complex_integration_scenario(self) -> None:
        """Test a complex integration scenario with all functions."""
        url = "https://github.com/user/my-special-repo/tree/feature-branch/src/lib"

        # Test that it's detected as a Git URL
        assert is_git_url(url) is True

        # Test parsing
        parsed = parse_git_url(url)
        assert parsed.base_url == "https://github.com/user/my-special-repo"
        assert parsed.branch == "feature-branch"
        assert parsed.subdir == "src/lib"
        assert parsed.detected_from_url is True

        # Test sanitization
        sanitized = sanitize_repo_name(parsed.base_url)
        assert sanitized == "my-special-repo"
