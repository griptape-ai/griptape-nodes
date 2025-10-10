import logging
import time
from collections.abc import Generator
from typing import TYPE_CHECKING

from griptape_cloud_client.api.assets.create_asset import sync as create_asset
from griptape_cloud_client.api.assets.create_asset_url import sync as create_asset_url
from griptape_cloud_client.api.assistant_runs.create_assistant_run import sync as create_assistant_run
from griptape_cloud_client.api.assistant_runs.get_assistant_run import sync as get_assistant_run
from griptape_cloud_client.api.assistants.list_assistants import sync as list_assistants
from griptape_cloud_client.api.buckets.create_bucket import sync as create_bucket
from griptape_cloud_client.api.buckets.delete_bucket import sync as delete_bucket
from griptape_cloud_client.api.buckets.get_bucket import sync as get_bucket
from griptape_cloud_client.api.buckets.list_buckets import sync as list_buckets
from griptape_cloud_client.api.buckets.update_bucket import sync as update_bucket
from griptape_cloud_client.api.deployments.get_deployment import sync as get_deployment
from griptape_cloud_client.api.deployments.list_structure_deployments import sync as list_structure_deployments
from griptape_cloud_client.api.events.list_assistant_events import sync as list_assistant_events
from griptape_cloud_client.api.events.list_events import sync as list_events
from griptape_cloud_client.api.structure_runs.create_structure_run import sync as create_structure_run
from griptape_cloud_client.api.structure_runs.get_structure_run import sync as get_structure_run
from griptape_cloud_client.api.structures.list_structures import sync as list_structures
from griptape_cloud_client.models.assert_url_operation import AssertUrlOperation
from griptape_cloud_client.models.assistant_event_detail import AssistantEventDetail
from griptape_cloud_client.models.create_asset_request_content import CreateAssetRequestContent
from griptape_cloud_client.models.create_asset_response_content import (
    CreateAssetResponseContent,
)
from griptape_cloud_client.models.create_asset_url_request_content import CreateAssetUrlRequestContent
from griptape_cloud_client.models.create_asset_url_response_content import CreateAssetUrlResponseContent
from griptape_cloud_client.models.create_assistant_run_request_content import (
    CreateAssistantRunRequestContent,
)
from griptape_cloud_client.models.create_assistant_run_response_content import (
    CreateAssistantRunResponseContent,
)
from griptape_cloud_client.models.create_bucket_request_content import CreateBucketRequestContent
from griptape_cloud_client.models.create_bucket_response_content import CreateBucketResponseContent
from griptape_cloud_client.models.create_structure_run_request_content import (
    CreateStructureRunRequestContent,
)
from griptape_cloud_client.models.create_structure_run_response_content import (
    CreateStructureRunResponseContent,
)
from griptape_cloud_client.models.deployment_status import DeploymentStatus
from griptape_cloud_client.models.event_detail import EventDetail
from griptape_cloud_client.models.get_assistant_run_response_content import (
    GetAssistantRunResponseContent,
)
from griptape_cloud_client.models.get_bucket_response_content import GetBucketResponseContent
from griptape_cloud_client.models.get_deployment_response_content import GetDeploymentResponseContent
from griptape_cloud_client.models.get_structure_run_response_content import (
    GetStructureRunResponseContent,
)
from griptape_cloud_client.models.list_assistant_events_response_content import (
    ListAssistantEventsResponseContent,
)
from griptape_cloud_client.models.list_assistants_response_content import ListAssistantsResponseContent
from griptape_cloud_client.models.list_buckets_response_content import ListBucketsResponseContent
from griptape_cloud_client.models.list_events_response_content import ListEventsResponseContent
from griptape_cloud_client.models.list_structure_deployments_response_content import (
    ListStructureDeploymentsResponseContent,
)
from griptape_cloud_client.models.list_structures_response_content import (
    ListStructuresResponseContent,
)
from griptape_cloud_client.models.structure_deployment_detail import StructureDeploymentDetail
from griptape_cloud_client.models.structure_run_status import StructureRunStatus
from griptape_cloud_client.models.update_bucket_request_content import UpdateBucketRequestContent
from griptape_cloud_client.models.update_bucket_response_content import UpdateBucketResponseContent
from griptape_cloud_client.types import UNSET

if TYPE_CHECKING:
    from griptape_cloud_client.client import AuthenticatedClient

logger = logging.getLogger(__name__)


class GriptapeCloudApiMixin:
    """Mixin class providing shared Griptape Cloud API functionality."""

    gtc_client: "AuthenticatedClient"

    def _get_deployment(self, deployment_id: str) -> GetDeploymentResponseContent:
        try:
            response = get_deployment(
                deployment_id=deployment_id,
                client=self.gtc_client,
            )
            if isinstance(response, GetDeploymentResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error getting deployment: %s", e)
            raise

    def _list_structure_deployments(
        self, structure_id: str, status: list[DeploymentStatus] | None = None
    ) -> ListStructureDeploymentsResponseContent:
        try:
            status_query = status or UNSET
            response = list_structure_deployments(
                structure_id=structure_id, client=self.gtc_client, status=status_query
            )
            if isinstance(response, ListStructureDeploymentsResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error getting deployment: %s", e)
            raise

    def _wait_for_structure_deployment(self, deployment_id: str, timeout: float = 60.0) -> GetDeploymentResponseContent:
        try:
            start_time = time.time()
            while True:
                response = self._get_deployment(deployment_id=deployment_id)
                if isinstance(response, GetDeploymentResponseContent):
                    # Check if deployment is in a terminal state
                    if response.status in [DeploymentStatus.ERROR, DeploymentStatus.FAILED, DeploymentStatus.SUCCEEDED]:
                        return response

                    # Check timeout
                    if time.time() - start_time > timeout:
                        msg = f"Timeout waiting for deployment {deployment_id} to reach terminal state"
                        logger.error(msg)
                        raise TimeoutError(msg)  # noqa: TRY301

                    # Wait before next check
                    time.sleep(1.0)
                else:
                    msg = f"Unexpected response type: {type(response)}"
                    logger.error(msg)
                    raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error waiting for structure deployment: %s", e)
            raise

    def _wait_for_latest_structure_deployment(
        self, structure_id: str, timeout: float = 300.0
    ) -> GetDeploymentResponseContent:
        try:
            response = self._list_structure_deployments(structure_id=structure_id)
            if isinstance(response, ListStructureDeploymentsResponseContent):
                # Wait for the latest deployment to complete
                latest_deployment = max(response.deployments, key=lambda d: d.created_at, default=None)
                if latest_deployment:
                    return self._wait_for_structure_deployment(latest_deployment.deployment_id, timeout=timeout)
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error waiting for latest structure deployment: %s", e)
            raise

    def _list_buckets(self) -> ListBucketsResponseContent:
        try:
            response = list_buckets(
                client=self.gtc_client,
                page=1,
                page_size=100,
            )
            if isinstance(response, ListBucketsResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error listing buckets: %s", e)
            raise

    def _get_bucket(self, bucket_id: str) -> GetBucketResponseContent:
        try:
            response = get_bucket(bucket_id=bucket_id, client=self.gtc_client)
            if isinstance(response, GetBucketResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error getting bucket: %s", e)
            raise

    def _create_bucket(self, name: str) -> CreateBucketResponseContent:
        try:
            response = create_bucket(
                body=CreateBucketRequestContent(name=name),
                client=self.gtc_client,
            )
            if isinstance(response, CreateBucketResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error creating bucket: %s", e)
            raise

    def _update_bucket(self, bucket_id: str, name: str) -> UpdateBucketResponseContent:
        try:
            response = update_bucket(
                bucket_id=bucket_id,
                body=UpdateBucketRequestContent(name=name),
                client=self.gtc_client,
            )
            if isinstance(response, UpdateBucketResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error updating bucket: %s", e)
            raise

    def _delete_bucket(self, bucket_id: str) -> None:
        try:
            delete_bucket(bucket_id=bucket_id, client=self.gtc_client)
        except Exception as e:
            logger.error("Error deleting bucket: %s", e)
            raise

    def _list_assistants(self) -> ListAssistantsResponseContent:
        try:
            response = list_assistants(
                client=self.gtc_client,
                page=1,
                page_size=100,
            )
            if isinstance(response, ListAssistantsResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error listing assistants: %s", e)
            raise

    def _get_assistant_run(self, assistant_run_id: str) -> GetAssistantRunResponseContent:
        try:
            response = get_assistant_run(assistant_run_id=assistant_run_id, client=self.gtc_client)
            if isinstance(response, GetAssistantRunResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error getting assistant run: %s", e)
            raise

    def _create_assistant_run(self, assistant_id: str, args: list[str]) -> CreateAssistantRunResponseContent:
        try:
            response = create_assistant_run(
                assistant_id=assistant_id,
                body=CreateAssistantRunRequestContent(
                    args=args,
                ),
                client=self.gtc_client,
            )
            if isinstance(response, CreateAssistantRunResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error creating assistant run: %s", e)
            raise

    def _list_assistant_run_events(
        self, assistant_run_id: str, offset: float | None = None
    ) -> ListAssistantEventsResponseContent:
        try:
            response = list_assistant_events(
                assistant_run_id=assistant_run_id,
                offset=str(offset) if offset is not None else UNSET,
                client=self.gtc_client,
            )
            if isinstance(response, ListAssistantEventsResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error listing events: %s", e)
            raise

    def _poll_assistant_run_events(self, assistant_run_id: str) -> Generator[list[AssistantEventDetail], None, None]:
        run_completed = False
        offset: float | None = None

        while not run_completed:
            list_events_response = self._list_assistant_run_events(assistant_run_id=assistant_run_id, offset=offset)
            offset = list_events_response.next_offset
            for event in list_events_response.events:
                if event.type_ == "FinishStructureRunEvent" and event.origin == "ASSISTANT":
                    run_completed = True
            yield list_events_response.events
            time.sleep(0.5)

    def _create_asset(
        self,
        asset_name: str,
        bucket_id: str,
    ) -> CreateAssetResponseContent:
        try:
            response = create_asset(
                bucket_id=bucket_id,
                client=self.gtc_client,
                body=CreateAssetRequestContent(
                    name=asset_name,
                ),
            )
            if isinstance(response, CreateAssetResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error creating asset: %s", e)
            raise

    def _create_asset_url(
        self, asset_name: str, bucket_id: str, operation: AssertUrlOperation = AssertUrlOperation.GET
    ) -> CreateAssetUrlResponseContent:
        try:
            response = create_asset_url(
                bucket_id=bucket_id,
                name=asset_name,
                client=self.gtc_client,
                body=CreateAssetUrlRequestContent(
                    operation=operation,
                ),
            )
            if isinstance(response, CreateAssetUrlResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error creating asset URL: %s", e)
            raise

    def _list_structures(self) -> ListStructuresResponseContent:
        try:
            response = list_structures(
                client=self.gtc_client,
                page=1,
                page_size=100,
            )
            if isinstance(response, ListStructuresResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error listing structures: %s", e)
            raise

    def _create_structure_run(self, structure_id: str, args: list[str]) -> CreateStructureRunResponseContent:
        try:
            response = create_structure_run(
                structure_id=structure_id,
                body=CreateStructureRunRequestContent(
                    args=args,
                ),
                client=self.gtc_client,
            )
            if isinstance(response, CreateStructureRunResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error creating structure run: %s", e)
            raise

    def _get_structure_run(self, structure_run_id: str) -> GetStructureRunResponseContent:
        try:
            response = get_structure_run(structure_run_id=structure_run_id, client=self.gtc_client)
            if isinstance(response, GetStructureRunResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error getting structure run: %s", e)
            raise

    def _get_structure_run_bad_statuses(self) -> list[str]:
        return [StructureRunStatus.FAILED, StructureRunStatus.CANCELLED, StructureRunStatus.ERROR]

    def _list_structure_run_events(
        self, structure_run_id: str, offset: float | None = None
    ) -> ListEventsResponseContent:
        try:
            response = list_events(
                structure_run_id=structure_run_id,
                offset=str(offset) if offset is not None else UNSET,
                client=self.gtc_client,
            )
            if isinstance(response, ListEventsResponseContent):
                return response
            msg = f"Unexpected response type: {type(response)}"
            logger.error(msg)
            raise TypeError(msg)  # noqa: TRY301
        except Exception as e:
            logger.error("Error listing events: %s", e)
            raise

    def _poll_structure_run_events(self, structure_run_id: str) -> Generator[list[EventDetail], None, None]:
        run_completed = False
        offset: float | None = None

        while not run_completed:
            list_events_response = self._list_structure_run_events(structure_run_id=structure_run_id, offset=offset)
            offset = list_events_response.next_offset
            for event in list_events_response.events:
                if event.type_ == "StructureRunCompleted" and event.origin == "SYSTEM":
                    run_completed = True
            yield list_events_response.events
            time.sleep(0.5)

    def _is_deployment_ready(self, deployment: GetDeploymentResponseContent | StructureDeploymentDetail) -> bool:
        return deployment.status in [
            DeploymentStatus.SUCCEEDED,
        ]
