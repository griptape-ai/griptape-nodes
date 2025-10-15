import os
from unittest.mock import Mock, patch

import httpx

from griptape_nodes.retained_mode.managers.user_manager import UserManager

# Expected timeout value from UserManager
EXPECTED_TIMEOUT = 5.0


class TestUserManager:
    """Test UserManager functionality for fetching and caching user email."""

    def test_user_email_success(self) -> None:
        """Test successful user email fetch from Griptape Cloud API."""
        # Create mock secrets manager
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        # Create mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "users": [
                {
                    "user_id": "test-uuid",
                    "email": "test@example.com",
                    "name": "Test User",
                }
            ]
        }

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email == "test@example.com"
            mock_secrets_manager.get_secret.assert_called_once_with("GT_CLOUD_API_KEY")

    def test_user_email_cached_property(self) -> None:
        """Test that user_email property is cached and httpx.get is only called once."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": [{"user_id": "test-uuid", "email": "cached@example.com"}]}

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)

            # Access the property twice
            email1 = user_manager.user_email
            email2 = user_manager.user_email

            # Both should return the same value
            assert email1 == "cached@example.com"
            assert email2 == "cached@example.com"

            # httpx.get should only be called once due to caching
            assert mock_get.call_count == 1

    def test_user_email_no_api_key(self) -> None:
        """Test that no HTTP request is made when API key is not available."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = None

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get") as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None
            mock_get.assert_not_called()

    def test_user_email_http_status_error(self) -> None:
        """Test handling of HTTP status errors (401, 403, 500, etc.)."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        # Create mock HTTPStatusError
        mock_request = Mock()
        mock_response = Mock()
        mock_response.status_code = 401
        http_error = httpx.HTTPStatusError("Unauthorized", request=mock_request, response=mock_response)

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=http_error):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None

    def test_user_email_request_error(self) -> None:
        """Test handling of network request errors."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        # Create mock RequestError (network error)
        request_error = httpx.RequestError("Network error")

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=request_error):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None

    def test_user_email_empty_users_list(self) -> None:
        """Test handling of empty users array in API response."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": []}

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None

    def test_user_email_missing_users_key(self) -> None:
        """Test handling of response without 'users' key."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {}

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None

    def test_user_email_custom_base_url(self) -> None:
        """Test that custom GT_CLOUD_BASE_URL environment variable is used."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": [{"user_id": "test-uuid", "email": "test@example.com"}]}

        custom_url = "https://custom.griptape.ai"
        with (
            patch.dict(os.environ, {"GT_CLOUD_BASE_URL": custom_url}),
            patch(
                "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
            ) as mock_get,
        ):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email == "test@example.com"
            # Verify the correct URL was used
            call_args = mock_get.call_args
            assert call_args[0][0] == f"{custom_url}/api/users"

    def test_user_email_default_base_url(self) -> None:
        """Test that default base URL is used when environment variable is not set."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": [{"user_id": "test-uuid", "email": "test@example.com"}]}

        # Ensure GT_CLOUD_BASE_URL is not set
        env_copy = os.environ.copy()
        env_copy.pop("GT_CLOUD_BASE_URL", None)

        with (
            patch.dict(os.environ, env_copy, clear=True),
            patch(
                "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
            ) as mock_get,
        ):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email == "test@example.com"
            # Verify default URL was used
            call_args = mock_get.call_args
            assert call_args[0][0] == "https://cloud.griptape.ai/api/users"

    def test_user_email_unexpected_exception(self) -> None:
        """Test handling of unexpected exceptions during API call."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=Exception("Unexpected error")
        ):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email is None

    def test_user_email_authorization_header(self) -> None:
        """Test that correct Authorization header is sent with API request."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "my-secret-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": [{"user_id": "test-uuid", "email": "test@example.com"}]}

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email == "test@example.com"

            # Verify Authorization header was set correctly
            call_kwargs = mock_get.call_args[1]
            assert "headers" in call_kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret-key"

    def test_user_email_timeout_parameter(self) -> None:
        """Test that request timeout is set appropriately."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"users": [{"user_id": "test-uuid", "email": "test@example.com"}]}

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            assert email == "test@example.com"

            # Verify timeout was set
            call_kwargs = mock_get.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == EXPECTED_TIMEOUT

    def test_user_email_multiple_users_returns_first(self) -> None:
        """Test that when multiple users are returned, the first one's email is used."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "users": [
                {"user_id": "uuid-1", "email": "first@example.com"},
                {"user_id": "uuid-2", "email": "second@example.com"},
            ]
        }

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            email = user_manager.user_email

            # Should return first user's email
            assert email == "first@example.com"

    def test_user_organization_success(self) -> None:
        """Test successful user organization fetch from Griptape Cloud API."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [
                {
                    "organization_id": "test-org-uuid",
                    "name": "Test Organization",
                    "description": "A test organization",
                }
            ]
        }

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name == "Test Organization"
            mock_secrets_manager.get_secret.assert_called_once_with("GT_CLOUD_API_KEY")

    def test_user_organization_cached_property(self) -> None:
        """Test that user_organization property is cached and httpx.get is only called once."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [{"organization_id": "test-org-uuid", "name": "Cached Organization"}]
        }

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)

            # Access the property twice
            org1 = user_manager.user_organization
            org2 = user_manager.user_organization

            # Both should return the same value
            assert org1 == "Cached Organization"
            assert org2 == "Cached Organization"

            # httpx.get should only be called once due to caching
            assert mock_get.call_count == 1

    def test_user_organization_no_api_key(self) -> None:
        """Test that no HTTP request is made when API key is not available."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = None

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get") as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None
            mock_get.assert_not_called()

    def test_user_organization_http_status_error(self) -> None:
        """Test handling of HTTP status errors (401, 403, 500, etc.)."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_request = Mock()
        mock_response = Mock()
        mock_response.status_code = 403
        http_error = httpx.HTTPStatusError("Forbidden", request=mock_request, response=mock_response)

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=http_error):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None

    def test_user_organization_request_error(self) -> None:
        """Test handling of network request errors."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        request_error = httpx.RequestError("Network error")

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=request_error):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None

    def test_user_organization_empty_organizations_list(self) -> None:
        """Test handling of empty organizations array in API response."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {"organizations": []}

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None

    def test_user_organization_missing_organizations_key(self) -> None:
        """Test handling of response without 'organizations' key."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {}

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None

    def test_user_organization_custom_base_url(self) -> None:
        """Test that custom GT_CLOUD_BASE_URL environment variable is used."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [{"organization_id": "test-org-uuid", "name": "Test Organization"}]
        }

        custom_url = "https://custom.griptape.ai"
        with (
            patch.dict(os.environ, {"GT_CLOUD_BASE_URL": custom_url}),
            patch(
                "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
            ) as mock_get,
        ):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name == "Test Organization"
            # Verify the correct URL was used
            call_args = mock_get.call_args
            assert call_args[0][0] == f"{custom_url}/api/organizations"

    def test_user_organization_default_base_url(self) -> None:
        """Test that default base URL is used when environment variable is not set."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [{"organization_id": "test-org-uuid", "name": "Test Organization"}]
        }

        # Ensure GT_CLOUD_BASE_URL is not set
        env_copy = os.environ.copy()
        env_copy.pop("GT_CLOUD_BASE_URL", None)

        with (
            patch.dict(os.environ, env_copy, clear=True),
            patch(
                "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
            ) as mock_get,
        ):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name == "Test Organization"
            # Verify default URL was used
            call_args = mock_get.call_args
            assert call_args[0][0] == "https://cloud.griptape.ai/api/organizations"

    def test_user_organization_unexpected_exception(self) -> None:
        """Test handling of unexpected exceptions during API call."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", side_effect=Exception("Unexpected error")
        ):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name is None

    def test_user_organization_authorization_header(self) -> None:
        """Test that correct Authorization header is sent with API request."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "my-secret-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [{"organization_id": "test-org-uuid", "name": "Test Organization"}]
        }

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name == "Test Organization"

            # Verify Authorization header was set correctly
            call_kwargs = mock_get.call_args[1]
            assert "headers" in call_kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret-key"

    def test_user_organization_timeout_parameter(self) -> None:
        """Test that request timeout is set appropriately."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [{"organization_id": "test-org-uuid", "name": "Test Organization"}]
        }

        with patch(
            "griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response
        ) as mock_get:
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            assert org_name == "Test Organization"

            # Verify timeout was set
            call_kwargs = mock_get.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == EXPECTED_TIMEOUT

    def test_user_organization_multiple_organizations_returns_first(self) -> None:
        """Test that when multiple organizations are returned, the first one's name is used."""
        mock_secrets_manager = Mock()
        mock_secrets_manager.get_secret.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.json.return_value = {
            "organizations": [
                {"organization_id": "org-1", "name": "First Organization"},
                {"organization_id": "org-2", "name": "Second Organization"},
            ]
        }

        with patch("griptape_nodes.retained_mode.managers.user_manager.httpx.get", return_value=mock_response):
            user_manager = UserManager(mock_secrets_manager)
            org_name = user_manager.user_organization

            # Should return first organization's name
            assert org_name == "First Organization"
