"""Manages user information from Griptape Cloud.

Handles fetching and caching user information (email, organization) from the Griptape Cloud API
to display in the engine and editor.
"""

from __future__ import annotations

import logging
import os
from functools import cached_property
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager

logger = logging.getLogger("griptape_nodes")


class UserManager:
    """Manages user information from Griptape Cloud."""

    def __init__(self, secrets_manager: SecretsManager) -> None:
        """Initialize the UserManager.

        Args:
            secrets_manager: The SecretsManager instance to use for API key retrieval.
        """
        self._secrets_manager = secrets_manager

    @cached_property
    def user_email(self) -> str | None:
        """Get the user's email from Griptape Cloud.

        This property is cached after the first access.

        Returns:
            str | None: The user's email or None if not available/not logged in.
        """
        try:
            api_key = self._secrets_manager.get_secret("GT_CLOUD_API_KEY")
            if not api_key:
                logger.debug("No GT_CLOUD_API_KEY found, skipping user email fetch")
                return None

            base_url = os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
            url = f"{base_url}/api/users"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = httpx.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

            data = response.json()
            users = data.get("users", [])
            if users and len(users) > 0:
                email = users[0].get("email")
                logger.debug("Fetched user email: %s", email)
                return email

            logger.debug("No users found in API response")

        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch user email (HTTP %s): %s", e.response.status_code, e)
        except httpx.RequestError as e:
            logger.warning("Failed to fetch user email (request error): %s", e)
        except Exception as e:
            logger.warning("Failed to fetch user email (unexpected error): %s", e)

        return None

    @cached_property
    def user_organization(self) -> str | None:
        """Get the user's organization name from Griptape Cloud.

        This property is cached after the first access.

        Returns:
            str | None: The organization name or None if not available/not logged in.
        """
        try:
            api_key = self._secrets_manager.get_secret("GT_CLOUD_API_KEY")
            if not api_key:
                logger.debug("No GT_CLOUD_API_KEY found, skipping user organization fetch")
                return None

            base_url = os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
            url = f"{base_url}/api/organizations"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = httpx.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

            data = response.json()
            organizations = data.get("organizations", [])
            if organizations and len(organizations) > 0:
                org_name = organizations[0].get("name")
                logger.debug("Fetched user organization: %s", org_name)
                return org_name

            logger.debug("No organizations found in API response")

        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch user organization (HTTP %s): %s", e.response.status_code, e)
        except httpx.RequestError as e:
            logger.warning("Failed to fetch user organization (request error): %s", e)
        except Exception as e:
            logger.warning("Failed to fetch user organization (unexpected error): %s", e)

        return None
