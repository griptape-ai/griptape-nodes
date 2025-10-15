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

from griptape_nodes.retained_mode.events.app_events import OrganizationInfo, UserInfo

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
    def user(self) -> UserInfo | None:
        """Get the user's information from Griptape Cloud.

        This property is cached after the first access.

        Returns:
            UserInfo | None: The user information or None if not available/not logged in.
        """
        try:
            api_key = self._secrets_manager.get_secret("GT_CLOUD_API_KEY")
            if not api_key:
                logger.debug("No GT_CLOUD_API_KEY found, skipping user fetch")
                return None

            base_url = os.environ.get("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
            url = f"{base_url}/api/users"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = httpx.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

            data = response.json()
            users = data.get("users", [])
            if users and len(users) > 0:
                user = users[0]
                user_id = user.get("user_id")
                email = user.get("email")
                name = user.get("name")
                if user_id and email:
                    logger.debug("Fetched user: %s (ID: %s)", email, user_id)
                    return UserInfo(id=user_id, email=email, name=name)

            logger.debug("No users found in API response")

        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch user (HTTP %s): %s", e.response.status_code, e)
        except httpx.RequestError as e:
            logger.warning("Failed to fetch user (request error): %s", e)
        except Exception as e:
            logger.warning("Failed to fetch user (unexpected error): %s", e)

        return None

    @cached_property
    def user_organization(self) -> OrganizationInfo | None:
        """Get the user's organization information from Griptape Cloud.

        This property is cached after the first access.

        Returns:
            OrganizationInfo | None: The organization information or None if not available/not logged in.
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
                org = organizations[0]
                org_id = org.get("organization_id")
                org_name = org.get("name")
                if org_id and org_name:
                    logger.debug("Fetched user organization: %s (ID: %s)", org_name, org_id)
                    return OrganizationInfo(id=org_id, name=org_name)

            logger.debug("No organizations found in API response")

        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch user organization (HTTP %s): %s", e.response.status_code, e)
        except httpx.RequestError as e:
            logger.warning("Failed to fetch user organization (request error): %s", e)
        except Exception as e:
            logger.warning("Failed to fetch user organization (unexpected error): %s", e)

        return None
