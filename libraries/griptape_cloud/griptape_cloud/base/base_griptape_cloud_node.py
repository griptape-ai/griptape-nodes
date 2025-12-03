import logging
import os
from urllib.parse import urljoin

from griptape_cloud_client.client import AuthenticatedClient

from griptape_cloud.mixins.griptape_cloud_api_mixin import GriptapeCloudApiMixin
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

DEFAULT_GRIPTAPE_CLOUD_URL = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
DEFAULT_GRIPTAPE_CLOUD_ENDPOINT = urljoin(base=DEFAULT_GRIPTAPE_CLOUD_URL, url="/api/")
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"

logger = logging.getLogger("griptape_nodes")


class BaseGriptapeCloudNode(BaseNode, GriptapeCloudApiMixin):
    def __init__(self, name: str | None = None, **kwargs) -> None:
        # Handle name as either positional or keyword argument
        if name is not None:
            kwargs["name"] = name
        super().__init__(**kwargs)
        self.base_url = DEFAULT_GRIPTAPE_CLOUD_ENDPOINT
        self.gtc_client = AuthenticatedClient(
            base_url=self.base_url,
            token=self._get_gt_cloud_api_key(),
            verify_ssl=False,
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = []

        try:
            self._get_gt_cloud_api_key()
        except Exception as e:
            exceptions.append(e)

        return exceptions if exceptions else None

    def _get_gt_cloud_api_key(self) -> str:
        if (api_key := GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)) is None:
            msg = f"{API_KEY_ENV_VAR} not found by Griptape Secrets Manager"
            raise KeyError(msg)
        return api_key
