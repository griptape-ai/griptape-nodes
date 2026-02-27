from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast
from urllib.parse import urljoin

from dotenv import set_key
from dotenv.main import DotEnv
from griptape_cloud_client.api.assets.create_asset import sync as create_asset
from griptape_cloud_client.api.assets.create_asset_url import sync as create_asset_url
from griptape_cloud_client.api.integrations.create_integration import sync as create_integration
from griptape_cloud_client.api.structures.create_structure import sync as create_structure
from griptape_cloud_client.api.structures.update_structure import sync as update_structure
from griptape_cloud_client.client import AuthenticatedClient
from griptape_cloud_client.models.assert_url_operation import AssertUrlOperation
from griptape_cloud_client.models.create_asset_request_content import CreateAssetRequestContent
from griptape_cloud_client.models.create_asset_response_content import CreateAssetResponseContent
from griptape_cloud_client.models.create_asset_url_request_content import CreateAssetUrlRequestContent
from griptape_cloud_client.models.create_asset_url_response_content import CreateAssetUrlResponseContent
from griptape_cloud_client.models.create_integration_request_content import CreateIntegrationRequestContent
from griptape_cloud_client.models.create_integration_response_content import CreateIntegrationResponseContent
from griptape_cloud_client.models.create_structure_request_content import CreateStructureRequestContent
from griptape_cloud_client.models.create_structure_response_content import CreateStructureResponseContent
from griptape_cloud_client.models.data_lake_structure_code import DataLakeStructureCode
from griptape_cloud_client.models.integration_config_input_union_type_2 import IntegrationConfigInputUnionType2
from griptape_cloud_client.models.integration_type import IntegrationType
from griptape_cloud_client.models.structure_code_type_1 import StructureCodeType1
from griptape_cloud_client.models.update_structure_request_content import UpdateStructureRequestContent
from griptape_cloud_client.models.update_structure_response_content import UpdateStructureResponseContent
from griptape_cloud_client.models.webhook_input import WebhookInput
from httpx import Client

from griptape_cloud.mixins.griptape_cloud_api_mixin import GriptapeCloudApiMixin
from griptape_cloud.publish_workflow import GRIPTAPE_CLOUD_LIBRARY_CONFIG_KEY
from griptape_cloud.publish_workflow.griptape_cloud_start_flow import GriptapeCloudStartFlow
from griptape_cloud.publish_workflow.griptape_cloud_workflow_builder import (
    GriptapeCloudWebhookIntegration,
    GriptapeCloudWorkflowBuilder,
    GriptapeCloudWorkflowBuilderInput,
)
from griptape_nodes.node_library.library_registry import LibraryNameAndVersion, LibraryRegistry
from griptape_nodes.node_library.workflow_registry import Workflow, WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    ResultDetail,
    ResultDetails,
)
from griptape_nodes.retained_mode.events.flow_events import GetTopLevelFlowRequest, GetTopLevelFlowResultSuccess
from griptape_nodes.retained_mode.events.node_events import (
    GetNodeMetadataRequest,
    GetNodeMetadataResultSuccess,
    SetNodeMetadataRequest,
    SetNodeMetadataResultSuccess,
)
from griptape_nodes.retained_mode.events.os_events import (
    CopyFileRequest,
    CopyFileResultSuccess,
    CopyTreeRequest,
    CopyTreeResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    GetParameterValueRequest,
    GetParameterValueResultSuccess,
    SetParameterValueRequest,
    SetParameterValueResultSuccess,
)
from griptape_nodes.retained_mode.events.secrets_events import (
    GetAllSecretValuesRequest,
    GetAllSecretValuesResultSuccess,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    PublishWorkflowProgressEvent,
    PublishWorkflowResultFailure,
    PublishWorkflowResultSuccess,
    SaveWorkflowRequest,
    SaveWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_cloud_client.models.integration_config_union_type_2 import IntegrationConfigUnionType2

    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager


T = TypeVar("T")


logger = logging.getLogger("griptape_cloud_publisher")

GRIPTAPE_SERVICE = "Griptape"


class GriptapeCloudPublisher(GriptapeCloudApiMixin):
    def __init__(
        self,
        workflow_name: str,
        *,
        published_workflow_file_name: str | None = None,
        pickle_control_flow_result: bool = False,
    ) -> None:
        self._workflow_name = workflow_name
        self._published_workflow_file_name = published_workflow_file_name
        self._client = Client()
        self._gtc_client = AuthenticatedClient(
            base_url=self._get_base_url(),
            token=self._get_secret("GT_CLOUD_API_KEY"),
            verify_ssl=False,
        )
        self._gt_cloud_bucket_id: str | None = None
        self.pickle_control_flow_result = pickle_control_flow_result
        self._progress: float = 0.0
        self._webhook_mode: bool = False

    def publish_workflow(self) -> ResultPayload:
        try:
            self._emit_progress_event(additional_progress=10.0, message="Validating workflow before publish...")
            validation_exceptions = self._validate_before_publish()
            if validation_exceptions:
                return PublishWorkflowResultFailure(
                    result_details=self._get_result_details_for_exceptions(validation_exceptions)
                )

            # Get the workflow shape
            self._emit_progress_event(additional_progress=10.0, message="Extracting workflow details...")
            workflow_shape = GriptapeNodes.WorkflowManager().extract_workflow_shape(self._workflow_name)
            logger.info("Workflow shape: %s", workflow_shape)

            self._create_run_input = self._gather_griptape_cloud_start_flow_input(workflow_shape)
            griptape_cloud_start_flow_node = self._get_griptape_cloud_start_flow_node()

            # Package the workflow
            self._emit_progress_event(additional_progress=20.0, message="Packaging workflow...")
            package_path = self._package_workflow(self._workflow_name, griptape_cloud_start_flow_node)
            logger.info("Workflow packaged to path: %s", package_path)

            # Deploy the workflow to Griptape Cloud
            self._emit_progress_event(additional_progress=15.0, message="Deploying workflow to Griptape Cloud...")
            structure = self._deploy_workflow_to_cloud(package_path, griptape_cloud_start_flow_node)
            logger.info(
                "Workflow '%s' published successfully to Structure: %s", self._workflow_name, structure.structure_id
            )

            webhook_integration: GriptapeCloudWebhookIntegration | None = None
            if griptape_cloud_start_flow_node is not None and griptape_cloud_start_flow_node.get_parameter_value(
                "enable_webhook_integration"
            ):
                self._emit_progress_event(additional_progress=2.0, message="Creating webhook integration...")
                webhook_integration = self._create_webhook_integration(structure, griptape_cloud_start_flow_node)

            self._emit_progress_event(additional_progress=2.0, message="Updating workflow metadata...")
            self._update_griptape_cloud_start_flow_metadata(
                structure=structure,
                griptape_cloud_start_flow_node=griptape_cloud_start_flow_node,
                webhook_integration=webhook_integration,
            )

            # Generate an executor workflow that can invoke the published structure
            self._emit_progress_event(additional_progress=20.0, message="Generating executor workflow...")
            executor_workflow_path = self._generate_executor_workflow(structure, workflow_shape, webhook_integration)

            self._emit_progress_event(additional_progress=20.0, message="Successfully published workflow!")

            return PublishWorkflowResultSuccess(
                published_workflow_file_path=str(executor_workflow_path),
                result_details=f"Workflow '{self._workflow_name}' published successfully to Griptape Cloud Structure '{structure.structure_id}'.",
                metadata=self._get_publish_workflow_response_metadata(structure.structure_id),
            )
        except Exception as e:
            details = f"Failed to publish workflow '{self._workflow_name}'. Error: {e}"
            logger.error(details)
            return PublishWorkflowResultFailure(
                result_details=details,
            )

    @classmethod
    def _get_result_details_for_exceptions(cls, exceptions: list[Exception]) -> ResultDetails:
        result_details: list[ResultDetail] = [ResultDetail(message=str(e), level=logging.ERROR) for e in exceptions]
        return ResultDetails(*result_details)

    @classmethod
    def _get_base_url(cls, *, api_url: bool = True) -> str:
        """Retrieves the base URL for the Griptape Cloud service."""
        base_url = os.environ.get("GT_CLOUD_BASE_URL") or "https://cloud.griptape.ai"
        if api_url and not base_url.endswith("/api"):
            base_url = urljoin(base_url, "/api")
        return base_url

    @classmethod
    def _get_config_value(cls, service: str, value: str) -> str:
        """Retrieves a configuration value from the ConfigManager."""
        config_value = GriptapeNodes.ConfigManager().get_config_value(f"{service}.{value}")
        if not config_value:
            details = f"Failed to get configuration value '{value}' for service '{service}'."
            logger.error(details)
            raise ValueError(details)
        return config_value

    @classmethod
    def _get_secret(cls, secret: str) -> str:
        """Retrieves a secret value from the SecretsManager."""
        secret_value = GriptapeNodes.SecretsManager().get_secret(secret)
        if not secret_value:
            details = f"Failed to get secret:'{secret}'."
            logger.error(details)
            raise ValueError(details)
        return secret_value

    @classmethod
    def _copy_file(cls, source_path: str | Path, destination_path: str | Path) -> None:
        """Copies a file from source to destination using OS events for cross-platform compatibility."""
        copy_file_result = GriptapeNodes.handle_request(
            CopyFileRequest(
                source_path=str(source_path),
                destination_path=str(destination_path),
            )
        )
        if not isinstance(copy_file_result, CopyFileResultSuccess):
            details = f"Failed to copy file from '{source_path}' to '{destination_path}'."
            logger.error(details)
            raise TypeError(details)

    @classmethod
    def _normalize_line_endings(cls, file_path: str | Path) -> None:
        """Normalizes line endings to LF for Linux compatibility.

        This is necessary because Windows may have CRLF line endings which cause
        'not found' errors when executing shell scripts on Linux.
        """
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as f:
            content = f.read()
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    @staticmethod
    def _validate_custom_install_script_path(path: str, workflow_name: str) -> None:
        if not Path(path).is_file():
            msg = (
                f"Attempted to package workflow '{workflow_name}'. "
                f"Failed because custom_install_script_path '{path}' does not exist."
            )
            raise FileNotFoundError(msg)

    def _get_publish_workflow_response_metadata(self, structure_id: str) -> dict[str, Any]:
        structure_url = urljoin(
            self._get_base_url(api_url=False),
            f"/structures/{structure_id}",
        )
        return {
            "publish_target_link": structure_url,
            "publish_target_link_description": "Click to view the published workflow as a Structure in Griptape Cloud.",
        }

    def _emit_progress_event(self, additional_progress: float, message: str) -> None:
        self._progress += additional_progress
        self._progress = min(self._progress, 100.0)
        event = ExecutionGriptapeNodeEvent(
            wrapped_event=ExecutionEvent(
                payload=PublishWorkflowProgressEvent(
                    progress=self._progress,
                    message=message,
                )
            )
        )
        GriptapeNodes.EventManager().put_event(event)

    def _validate_webhook_parameter(
        self, node_shape: dict, param_name: str, param_info: dict[str, Any]
    ) -> list[Exception]:
        """Validate a single webhook parameter before publishing."""
        exceptions: list[Exception] = []
        try:
            if param_name not in node_shape:
                details = f"Workflow '{self._workflow_name}' is configured for webhook mode, but 'Start Flow' node does not have a '{param_name}' input."
                logger.error(details)
                exceptions.append(ValueError(details))
            elif param_info.get("type") not in ["dict", "any"]:
                details = f"Workflow '{self._workflow_name}' is configured for webhook mode, but '{param_name}' input of 'Start Flow' node is not of type 'dict' or 'any'."
                logger.error(details)
                exceptions.append(ValueError(details))
        except Exception as e:
            exceptions.append(e)
        return exceptions

    def _validate_before_publish(self) -> list[Exception]:
        """Validate the workflow before publishing."""
        exceptions: list[Exception] = []

        try:
            self._gt_cloud_bucket_id = self._get_config_value(
                GRIPTAPE_CLOUD_LIBRARY_CONFIG_KEY, "GT_CLOUD_PUBLISH_BUCKET_ID"
            )
        except Exception as e:
            exceptions.append(e)

        try:
            self._get_secret("GT_CLOUD_BUCKET_ID")
        except Exception as e:
            exceptions.append(e)

        return exceptions

    def _get_griptape_cloud_start_flow_node(self) -> GriptapeCloudStartFlow | None:
        get_top_level_flow_result = GriptapeNodes.handle_request(GetTopLevelFlowRequest())
        if (
            not isinstance(get_top_level_flow_result, GetTopLevelFlowResultSuccess)
            or get_top_level_flow_result.flow_name is None
        ):
            details = "Unable to retrieve top-level flow."
            raise TypeError(details)

        flow_manager = GriptapeNodes.FlowManager()
        control_flow = flow_manager.get_flow_by_name(get_top_level_flow_result.flow_name)
        nodes = control_flow.nodes

        for node in nodes.values():
            if node.__class__.__name__ == GriptapeCloudStartFlow.__name__:
                return cast("GriptapeCloudStartFlow", node)
        return None

    @classmethod
    def _collect_workflow_download_commands(cls) -> list[str]:
        """Collect huggingface-cli download commands for all HuggingFace model parameters in the workflow."""
        from griptape_nodes.exe_types.param_components.huggingface.huggingface_model_parameter import (
            HuggingFaceModelParameter,
        )

        get_top_level_flow_result = GriptapeNodes.handle_request(GetTopLevelFlowRequest())
        if (
            not isinstance(get_top_level_flow_result, GetTopLevelFlowResultSuccess)
            or get_top_level_flow_result.flow_name is None
        ):
            return []

        flow_manager = GriptapeNodes.FlowManager()
        control_flow = flow_manager.get_flow_by_name(get_top_level_flow_result.flow_name)
        workflow_manager = GriptapeNodes.WorkflowManager()

        commands: list[str] = []
        seen: set[str] = set()
        for node in control_flow.nodes.values():
            hf_params: list[HuggingFaceModelParameter] = []

            def collect_hf_param(_cls: type, obj: Any, _hf_params: list = hf_params) -> None:
                if isinstance(obj, HuggingFaceModelParameter):
                    _hf_params.append(obj)

            workflow_manager._walk_object_tree(node, collect_hf_param)
            for hf_param in hf_params:
                for cmd in hf_param.get_download_commands():
                    if cmd not in seen:
                        seen.add(cmd)
                        commands.append(cmd)
        return commands

    def _update_griptape_cloud_start_flow_metadata(
        self,
        structure: UpdateStructureResponseContent,
        griptape_cloud_start_flow_node: GriptapeCloudStartFlow | None,
        webhook_integration: GriptapeCloudWebhookIntegration | None,
    ) -> None:
        if griptape_cloud_start_flow_node is not None:
            get_node_metadata_request = GetNodeMetadataRequest(node_name=griptape_cloud_start_flow_node.name)
            get_node_metadata_result = GriptapeNodes.handle_request(get_node_metadata_request)

            if not isinstance(get_node_metadata_result, GetNodeMetadataResultSuccess):
                details = "Failed to get Griptape Cloud Start Flow node metadata."
                logger.error(details)
                raise TypeError(details)

            node_metadata = get_node_metadata_result.metadata
            node_metadata["structure_id"] = griptape_cloud_start_flow_node.metadata.get(
                "structure_id", structure.structure_id
            )
            node_metadata["structure_name"] = griptape_cloud_start_flow_node.metadata.get(
                "structure_name", structure.name
            )
            node_metadata["structure_description"] = griptape_cloud_start_flow_node.metadata.get(
                "structure_description", structure.description
            )
            node_metadata["integration_id"] = webhook_integration.integration_id if webhook_integration else None

            set_node_metadata_request = SetNodeMetadataRequest(
                node_name=griptape_cloud_start_flow_node.name,
                metadata=node_metadata,
            )
            set_node_metadata_result = GriptapeNodes.handle_request(set_node_metadata_request)
            if not isinstance(set_node_metadata_result, SetNodeMetadataResultSuccess):
                details = "Failed to set Griptape Cloud Start Flow node metadata."
                logger.error(details)
                raise TypeError(details)

            for param_name in ["structure_id", "structure_name", "structure_description", "integration_id"]:
                set_parameter_value_request = SetParameterValueRequest(
                    node_name=griptape_cloud_start_flow_node.name,
                    parameter_name=param_name,
                    value=node_metadata[param_name],
                )
                set_parameter_value_result = GriptapeNodes.handle_request(set_parameter_value_request)
                if not isinstance(set_parameter_value_result, SetParameterValueResultSuccess):
                    details = f"Failed to set parameter '{param_name}' for Griptape Cloud Start Flow node."
                    logger.error(details)
                    raise TypeError(details)
                griptape_cloud_start_flow_node.show_parameter_by_name(param_name)
                if param_name == "integration_id":
                    griptape_cloud_start_flow_node.show_parameter_by_name("webhook_url")

            workflow = WorkflowRegistry.get_workflow_by_name(self._workflow_name)
            save_workflow_request = SaveWorkflowRequest(file_name=Path(workflow.file_path).stem)
            save_workflow_response = GriptapeNodes.handle_request(save_workflow_request)
            if not isinstance(save_workflow_response, SaveWorkflowResultSuccess):
                details = "Failed to save workflow after updating Griptape Cloud Start Flow metadata."
                logger.error(details)
                raise TypeError(details)

    def _gather_griptape_cloud_start_flow_input(self, workflow_shape: dict[str, Any]) -> dict[str, Any]:
        """Extracts the Griptape Cloud Start Flow input parameters from the workflow."""
        workflow_input: dict[str, Any] = {"Griptape Cloud Start Flow": {}}

        # Gather input parameters from the workflow shape
        for node_name, params in workflow_shape.get("input", {}).items():
            for param_name in params:
                request = GetParameterValueRequest(
                    node_name=node_name,
                    parameter_name=param_name,
                )
                result = GriptapeNodes.handle_request(request)
                if isinstance(result, GetParameterValueResultSuccess):
                    workflow_input["Griptape Cloud Start Flow"][param_name] = result.value

        return workflow_input

    def _upload_file_to_data_lake(self, name: str, value: bytes, bucket_id: str) -> None:
        create_asset_response = create_asset(
            client=self._gtc_client,
            bucket_id=bucket_id,
            body=CreateAssetRequestContent(
                name=name,
            ),
        )
        if not isinstance(create_asset_response, CreateAssetResponseContent):
            msg = f"Unexpected response type when creating asset: {type(create_asset_response)}"
            msg = self.format_error_message_for_response(msg, create_asset_response)
            logger.error(msg)
            raise TypeError(msg)

        create_asset_url_response = create_asset_url(
            client=self._gtc_client,
            bucket_id=bucket_id,
            name=name,
            body=CreateAssetUrlRequestContent(operation=AssertUrlOperation.PUT),
        )
        if not isinstance(create_asset_url_response, CreateAssetUrlResponseContent):
            msg = f"Unexpected response type when creating asset URL: {type(create_asset_url_response)}"
            msg = self.format_error_message_for_response(msg, create_asset_url_response)
            logger.error(msg)
            raise TypeError(msg)
        url = create_asset_url_response.url
        headers = create_asset_url_response.headers
        try:
            response = self._client.put(
                url=url,
                headers=headers.to_dict(),
                content=value,
            )
            response.raise_for_status()
        except Exception:
            msg = "Failed to upload file to data lake"
            logger.exception(msg)
            raise

    def _deploy_workflow_to_cloud(
        self, package_path: str, griptape_cloud_start_flow_node: GriptapeCloudStartFlow | None
    ) -> UpdateStructureResponseContent:
        if self._gt_cloud_bucket_id is None:
            details = "GT_CLOUD_PUBLISH_BUCKET_ID is not set in the configuration."
            logger.error(details)
            raise ValueError(details)

        existing_structure_id: str | None = None
        structure_name: str | None = None
        structure_description: str | None = None
        if griptape_cloud_start_flow_node is not None:
            structure_id_val = griptape_cloud_start_flow_node.get_parameter_value("structure_id")
            if structure_id_val is not None and structure_id_val != "":
                existing_structure_id = str(structure_id_val)
            structure_name = griptape_cloud_start_flow_node.get_parameter_value("structure_name")
            structure_description = griptape_cloud_start_flow_node.get_parameter_value("structure_description")

        if existing_structure_id is None:
            create_structure_response = create_structure(
                client=self._gtc_client,
                body=CreateStructureRequestContent(
                    name=structure_name or self._workflow_name,
                    description=structure_description or f"Published Griptape Nodes workflow '{self._workflow_name}'",
                    structure_config_file="structure_config.yaml",
                ),
            )
            if not isinstance(create_structure_response, CreateStructureResponseContent):
                msg = f"Unexpected response type when creating structure: {type(create_structure_response)}."
                msg = self.format_error_message_for_response(msg, create_structure_response)
                logger.error(msg)
                raise TypeError(msg)
            structure_id = create_structure_response.structure_id
        else:
            structure_id = existing_structure_id

        with Path(package_path).open("rb") as file:
            file_contents = file.read()
            file_name = Path(package_path).name

        asset_name = f"{structure_id}/{file_name}"
        self._upload_file_to_data_lake(name=asset_name, value=file_contents, bucket_id=self._gt_cloud_bucket_id)
        Path(package_path).unlink(missing_ok=True)

        update_structure_request_content = UpdateStructureRequestContent(
            structure_config_file="structure_config.yaml",
            code=StructureCodeType1(
                data_lake=DataLakeStructureCode(
                    bucket_id=self._gt_cloud_bucket_id,
                    asset_path=asset_name,
                ),
            ),
        )
        if structure_name is not None:
            update_structure_request_content.name = structure_name
        if structure_description is not None:
            update_structure_request_content.description = structure_description

        update_structure_response = update_structure(
            client=self._gtc_client,
            structure_id=structure_id,
            body=update_structure_request_content,
        )
        if not isinstance(update_structure_response, UpdateStructureResponseContent):
            msg = f"Unexpected response type when updating structure: {type(update_structure_response)}."
            msg = self.format_error_message_for_response(msg, update_structure_response)
            logger.error(msg)
            raise TypeError(msg)

        return update_structure_response

    def _create_webhook_integration(
        self, structure: UpdateStructureResponseContent, griptape_cloud_start_flow_node: GriptapeCloudStartFlow | None
    ) -> GriptapeCloudWebhookIntegration:
        integration_id: str | None = None
        webhook_url: str | None = None
        if griptape_cloud_start_flow_node is not None:
            integration_id = griptape_cloud_start_flow_node.get_parameter_value("integration_id")
            webhook_url = griptape_cloud_start_flow_node.get_parameter_value("webhook_url")

        if integration_id is not None and integration_id != "":
            return GriptapeCloudWebhookIntegration(
                integration_id=str(integration_id),
                webhook_url=str(webhook_url),
            )

        create_integration_response = create_integration(
            client=self._gtc_client,
            body=CreateIntegrationRequestContent(
                config=IntegrationConfigInputUnionType2(
                    webhook=WebhookInput(
                        disable_api_key_param=False,
                    )
                ),
                name=f"Webhook Integration for {structure.name}",
                type_=IntegrationType.WEBHOOK,
                structure_ids=[structure.structure_id],
            ),
        )
        if not isinstance(create_integration_response, CreateIntegrationResponseContent):
            msg = f"Unexpected response type when creating integration: {type(create_integration_response)}."
            msg = self.format_error_message_for_response(msg, create_integration_response)
            logger.error(msg)
            raise TypeError(msg)

        webhook_config = cast("IntegrationConfigUnionType2", create_integration_response.config).webhook

        return GriptapeCloudWebhookIntegration(
            integration_id=create_integration_response.integration_id,
            webhook_url=webhook_config.integration_endpoint,
        )

    def _copy_libraries_to_path_for_workflow(
        self,
        node_libraries: list[LibraryNameAndVersion],
        destination_path: Path,
        runtime_env_path: Path,
        workflow: Workflow,
    ) -> list[str]:
        """Copies the libraries to the specified path for the workflow, returning the list of library paths.

        This is used to package the workflow for publishing.
        """
        library_paths: list[str] = []

        for library_ref in node_libraries:
            library = GriptapeNodes.LibraryManager().get_library_info_by_library_name(library_ref.library_name)

            if library is None:
                details = f"Attempted to publish workflow '{workflow.metadata.name}', but failed gathering library info for library '{library_ref.library_name}'."
                logger.error(details)
                raise ValueError(details)

            library_data = LibraryRegistry.get_library(library_ref.library_name).get_library_data()

            if library.library_path.endswith(".json"):
                library_path = Path(library.library_path)
                absolute_library_path = library_path.resolve()
                abs_paths = [absolute_library_path]
                for node in library_data.nodes:
                    p = (library_path.parent / Path(node.file_path)).resolve()
                    abs_paths.append(p)
                common_root = Path(os.path.commonpath([str(p) for p in abs_paths]))
                dest = destination_path / common_root.name
                copy_tree_request = CopyTreeRequest(
                    source_path=str(common_root),
                    destination_path=str(dest),
                    ignore_patterns=[".venv", "__pycache__"],
                    dirs_exist_ok=True,
                )
                copy_tree_result = GriptapeNodes.handle_request(copy_tree_request)
                if not isinstance(copy_tree_result, CopyTreeResultSuccess):
                    details = f"Failed to copy library files from '{common_root}' to '{dest}' for library '{library_ref.library_name}'."
                    logger.error(details)
                    raise TypeError(details)
                library_path_relative_to_common_root = absolute_library_path.relative_to(common_root)
                library_paths.append(
                    (runtime_env_path / common_root.name / library_path_relative_to_common_root).as_posix()
                )
            else:
                library_paths.append(library.library_path)

        return library_paths

    def __get_install_source(self) -> tuple[Literal["git", "file", "pypi"], str | None]:
        """Determines the install source of the Griptape Nodes package.

        Returns:
            tuple: A tuple containing the install source and commit ID (if applicable).
        """
        dist = importlib.metadata.distribution("griptape_nodes")
        direct_url_text = dist.read_text("direct_url.json")
        # installing from pypi doesn't have a direct_url.json file
        if direct_url_text is None:
            logger.debug("No direct_url.json file found, assuming pypi install")
            return "pypi", None

        direct_url_info = json.loads(direct_url_text)
        url = direct_url_info.get("url")
        if url.startswith("file://"):
            try:
                pkg_dir = Path(str(dist.locate_file(""))).resolve()
                git_root = next(p for p in (pkg_dir, *pkg_dir.parents) if (p / ".git").is_dir())
                commit = (
                    subprocess.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
                        cwd=git_root,
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
            except (StopIteration, subprocess.CalledProcessError):
                logger.debug("File URL but no git repo → file")
                return "file", None
            else:
                logger.debug("Detected git repo at %s (commit %s)", git_root, commit)
                return "git", commit
        if "vcs_info" in direct_url_info:
            logger.debug("Detected git repo at %s", url)
            return "git", direct_url_info["vcs_info"].get("commit_id")[:7]
        # Fall back to pypi if no other source is found
        logger.debug("Failed to detect install source, assuming pypi")
        return "pypi", None

    def _get_merged_env_file_mapping(self, workspace_env_file_path: Path) -> dict[str, Any]:
        """Merges the secrets from the workspace env file with the secrets from the GriptapeNodes SecretsManager.

        This is used to create a single .env file for the workflow. We can gather all secrets explicitly defined in the .env file
        and by the settings/SecretsManager, but we will not gather all secrets from the OS env for the purpose of publishing.
        """
        env_file_dict = {}
        if workspace_env_file_path.exists():
            env_file = DotEnv(workspace_env_file_path)
            env_file_dict = env_file.dict()

        get_all_secrets_request = GetAllSecretValuesRequest()
        get_all_secrets_result = GriptapeNodes.handle_request(request=get_all_secrets_request)
        if not isinstance(get_all_secrets_result, GetAllSecretValuesResultSuccess):
            details = "Failed to get all secret values."
            logger.error(details)
            raise TypeError(details)

        secret_values = get_all_secrets_result.values
        for secret_name, secret_value in secret_values.items():
            if secret_name not in env_file_dict:
                env_file_dict[secret_name] = secret_value

        return env_file_dict

    def _write_env_file(self, env_file_path: Path, env_file_dict: dict[str, Any]) -> None:
        env_file_path.touch(exist_ok=True)
        for key, val in env_file_dict.items():
            set_key(env_file_path, key, str(val))

    def _package_workflow(self, workflow_name: str, start_flow_node: GriptapeCloudStartFlow | None) -> str:  # noqa: PLR0915
        config_manager = GriptapeNodes.ConfigManager()
        secrets_manager = GriptapeNodes.SecretsManager()
        workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)

        engine_version: str = ""
        engine_version_request = GetEngineVersionRequest()
        engine_version_result = GriptapeNodes.handle_request(request=engine_version_request)
        if not engine_version_result.succeeded():
            details = (
                f"Attempted to publish workflow '{workflow.metadata.name}', but failed getting the engine version."
            )
            logger.error(details)
            raise ValueError(details)
        engine_version_success = cast("GetEngineVersionResultSuccess", engine_version_result)
        engine_version = (
            f"v{engine_version_success.major}.{engine_version_success.minor}.{engine_version_success.patch}"
        )

        # This is the path where the full workflow will be packaged to in the runtime environment.
        packaged_top_level_dir = "/structure"

        # Gather the paths to the files we need to copy.
        # Files are now located in the publish_workflow directory
        publish_workflow_path = Path(__file__).parent
        structure_file_path = publish_workflow_path / "structure.py"
        structure_workflow_executor_file_path = publish_workflow_path / "structure_workflow_executor.py"
        structure_config_file_path = publish_workflow_path / "structure_config.yaml"
        pre_build_install_script_path = publish_workflow_path / "pre_build_install_script.sh"
        post_build_install_script_path = publish_workflow_path / "post_build_install_script.sh"
        register_libraries_script_path = publish_workflow_path / "register_libraries_script.py"
        download_models_script_path = publish_workflow_path / "download_models_script.py"
        full_workflow_file_path = WorkflowRegistry.get_complete_file_path(workflow.file_path)

        env_file_mapping = self._get_merged_env_file_mapping(secrets_manager.workspace_env_path)

        config = config_manager.user_config
        config["workspace_directory"] = packaged_top_level_dir

        # Create a temporary directory to perform the packaging
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            temp_workflow_file_path = tmp_dir_path / "workflow.py"
            temp_structure_path = tmp_dir_path / "structure.py"
            temp_structure_workflow_executor_path = tmp_dir_path / "structure_workflow_executor.py"
            temp_pre_build_install_script_path = tmp_dir_path / "pre_build_install_script.sh"
            temp_post_build_install_script_path = tmp_dir_path / "post_build_install_script.sh"
            temp_register_libraries_script_path = tmp_dir_path / "register_libraries_script.py"
            temp_download_models_script_path = tmp_dir_path / "download_models_script.py"
            config_file_path = tmp_dir_path / "GriptapeNodes" / "griptape_nodes_config.json"
            init_file_path = tmp_dir_path / "__init__.py"

            try:
                # Copy the workflow file, libraries, and structure files to the temporary directory
                self._copy_file(full_workflow_file_path, temp_workflow_file_path)
                self._copy_file(structure_workflow_executor_file_path, temp_structure_workflow_executor_path)
                self._copy_file(pre_build_install_script_path, temp_pre_build_install_script_path)
                self._normalize_line_endings(temp_pre_build_install_script_path)
                custom_install_script_path_val: str | None = None
                if start_flow_node is not None:
                    custom_install_script_path_val = start_flow_node.get_parameter_value("custom_install_script_path")
                if custom_install_script_path_val:
                    self._validate_custom_install_script_path(custom_install_script_path_val, workflow_name)
                    custom_script_contents = Path(custom_install_script_path_val).read_text(encoding="utf-8")
                    with temp_pre_build_install_script_path.open("a", encoding="utf-8", newline="\n") as f:
                        f.write("\n")
                        f.write(custom_script_contents)
                    self._normalize_line_endings(temp_pre_build_install_script_path)
                self._copy_file(post_build_install_script_path, temp_post_build_install_script_path)
                self._normalize_line_endings(temp_post_build_install_script_path)
                self._copy_file(structure_config_file_path, tmp_dir_path / "structure_config.yaml")

                # Write the environment variables to the .env file
                self._write_env_file(tmp_dir_path / ".env", env_file_mapping)

                # Get the library paths
                library_paths: list[str] = self._copy_libraries_to_path_for_workflow(
                    node_libraries=workflow.metadata.node_libraries_referenced,
                    destination_path=tmp_dir_path / "libraries",
                    runtime_env_path=Path(packaged_top_level_dir) / "libraries",
                    workflow=workflow,
                )
                config["app_events"] = {
                    "on_app_initialization_complete": {
                        "workflows_to_register": [],
                        "libraries_to_register": library_paths,
                    }
                }
                config["enable_workspace_file_watching"] = False
                library_paths_formatted = [f'"{library_path}"' for library_path in library_paths]

                with register_libraries_script_path.open("r", encoding="utf-8") as register_libraries_script_file:
                    register_libraries_script_contents = register_libraries_script_file.read()
                    register_libraries_script_contents = register_libraries_script_contents.replace(
                        '["REPLACE_LIBRARY_PATHS"]',
                        f"[{', '.join(library_paths_formatted)}]",
                    )
                with temp_register_libraries_script_path.open("w", encoding="utf-8") as register_libraries_script_file:
                    register_libraries_script_file.write(register_libraries_script_contents)

                download_commands = self._collect_workflow_download_commands()
                download_commands_formatted = [repr(cmd) for cmd in download_commands]
                with download_models_script_path.open("r", encoding="utf-8") as download_models_script_file:
                    download_models_script_contents = download_models_script_file.read().replace(
                        '["REPLACE_DOWNLOAD_COMMANDS"]',
                        f"[{', '.join(download_commands_formatted)}]",
                    )
                with temp_download_models_script_path.open("w", encoding="utf-8") as download_models_script_file:
                    download_models_script_file.write(download_models_script_contents)
                with temp_post_build_install_script_path.open("a", encoding="utf-8", newline="\n") as f:
                    f.write("\npython download_models_script.py\n")
                self._normalize_line_endings(temp_post_build_install_script_path)

                with structure_file_path.open("r", encoding="utf-8") as structure_file:
                    structure_file_contents = structure_file.read()
                    structure_file_contents = structure_file_contents.replace(
                        '["REPLACE_LIBRARIES"]',
                        f"[{', '.join(library_paths_formatted)}]",
                    )
                    structure_file_contents = structure_file_contents.replace(
                        '"REPLACE_PICKLE_DEFAULT"',
                        "True" if self.pickle_control_flow_result else "False",
                    )
                with temp_structure_path.open("w", encoding="utf-8") as structure_file:
                    structure_file.write(structure_file_contents)

                config_file_path.parent.mkdir(parents=True, exist_ok=True)
                with config_file_path.open("w", encoding="utf-8") as config_file:
                    config_file.write(json.dumps(config, indent=4))

                init_file_path.parent.mkdir(parents=True, exist_ok=True)
                with init_file_path.open("w", encoding="utf-8") as init_file:
                    init_file.write('"""This is a temporary __init__.py file for the structure."""\n')

                self._copy_file(config_file_path, tmp_dir_path / "griptape_nodes_config.json")

            except Exception as e:
                details = f"Failed to copy files to temporary directory. Error: {e}"
                logger.exception(details)
                raise

            # Create the requirements.txt file using the correct engine version
            source, commit_id = self.__get_install_source()
            if source == "git" and commit_id is not None:
                engine_version = commit_id
            requirements_file_path = tmp_dir_path / "requirements.txt"
            with requirements_file_path.open("w", encoding="utf-8") as requirements_file:
                requirements_file.write(
                    f"griptape-nodes @ git+https://github.com/griptape-ai/griptape-nodes.git@{engine_version}\n"
                )
                requirements_file.write(
                    "griptape_cloud_client @ git+https://github.com/griptape-ai/griptape-cloud-python-client.git@main"
                )

            archive_base_name = config_manager.workspace_path / workflow_name
            shutil.make_archive(str(archive_base_name), "zip", tmp_dir)
            return str(archive_base_name) + ".zip"

    def _generate_executor_workflow(
        self,
        structure: UpdateStructureResponseContent,
        workflow_shape: dict[str, Any],
        webhook_integration: GriptapeCloudWebhookIntegration | None,
    ) -> Path:
        """Generate a new workflow file that can execute the published structure.

        This creates a simple workflow with StartNode -> PublishedWorkflow -> EndNode
        that can invoke the published workflow in Griptape Cloud.

        Args:
            structure: The published structure in Griptape Cloud.
            workflow_shape: The input/output shape of the original workflow.
            webhook_integration: The webhook integration for the published structure, if any.

        Returns:
            Path to the generated executor workflow file.
        """
        # Use WorkflowBuilder to generate the executor workflow
        libraries: list[LibraryManager.LibraryInfo] = []
        if nodes_library := GriptapeNodes.LibraryManager().get_library_info_by_library_name("Griptape Nodes Library"):
            libraries.append(nodes_library)
        else:
            details = "Griptape Nodes Library is not available. Cannot generate executor workflow."
            logger.error(details)
            raise ValueError(details)
        if cloud_library := GriptapeNodes.LibraryManager().get_library_info_by_library_name("Griptape Cloud Library"):
            libraries.append(cloud_library)
        else:
            details = "Griptape Cloud Library is not available. Cannot generate executor workflow."
            logger.error(details)
            raise ValueError(details)
        library_paths = [library.library_path for library in libraries if library.library_path is not None]
        if self._published_workflow_file_name is None:
            self._published_workflow_file_name = f"{self._workflow_name}_gtc_executor_{structure.structure_id}"
        builder = GriptapeCloudWorkflowBuilder(
            workflow_builder_input=GriptapeCloudWorkflowBuilderInput(
                workflow_name=self._workflow_name,
                workflow_shape=workflow_shape,
                structure=structure,
                webhook_integration=webhook_integration,
                executor_workflow_name=self._published_workflow_file_name,
                libraries=library_paths,
                pickle_control_flow_result=self.pickle_control_flow_result,
            )
        )
        return builder.generate_executor_workflow()
