import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urljoin

import httpx
from httpx import Response

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.retained_mode.events.connection_events import (
    DeleteConnectionRequest,
    DeleteConnectionResultSuccess,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options

DEFAULT_WORKFLOW_BASE_ENDPOINT = urljoin(
    os.getenv("GRIPTAPE_NODES_API_BASE_URL", "https://api.nodes.griptape.ai"),
    "/api/workflows",
)
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass(eq=False)
class WorkflowOptions(Options):
    choices_value_lookup: dict[str, Any] = field(kw_only=True)

    def converters_for_trait(self) -> list[Callable]:
        def converter(value: Any) -> Any:
            if value not in self.choices:
                msg = f"Selection '{value}' is not in choices. Defaulting to first choice: '{self.choices[0]}'."
                logger.warning(msg)
                value = self.choices[0]
            value = self.choices_value_lookup.get(value, self.choices[0])["id"]
            msg = f"Converted choice into value: {value}"
            logger.warning(msg)
            return value

        return [converter]

    def validators_for_trait(self) -> list[Callable[[Parameter, Any], Any]]:
        def validator(param: Parameter, value: Any) -> None:
            if value not in [x.get("id") for x in self.choices_value_lookup.values()]:
                msg = f"Attempted to set Parameter '{param.name}' to value '{value}', but that was not one of the available choices."

                def raise_error() -> None:
                    raise ValueError(msg)

                raise_error()

        return [validator]


class PublishedWorkflow(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.workflows = self._get_workflow_options()
        self.choices = list(map(PublishedWorkflow._workflow_to_name_and_id, self.workflows))

        self.add_parameter(
            Parameter(
                name="workflow_id",
                default_value=(self.workflows[0]["id"] if self.workflows else None),
                input_types=["str"],
                output_type="str",
                type="str",
                traits={
                    WorkflowOptions(
                        choices=list(map(PublishedWorkflow._workflow_to_name_and_id, self.workflows)),
                        choices_value_lookup={PublishedWorkflow._workflow_to_name_and_id(w): w for w in self.workflows},
                    )
                },
                allowed_modes={
                    ParameterMode.INPUT,
                    ParameterMode.OUTPUT,
                    ParameterMode.PROPERTY,
                },
                tooltip="workflow",
            )
        )

    @classmethod
    def _workflow_to_name_and_id(cls, workflow: dict[str, Any]) -> str:
        return f"{workflow['name']} ({workflow['id']})"

    def _get_headers(self) -> dict[str, str]:
        api_key = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _get_workflow_options(self) -> list[dict[str, Any]]:
        try:
            list_workflows_response = self._list_workflows()
            data = list_workflows_response.json()
            return data.get("workflows", [])
        except Exception:
            return []

    def _list_workflows(self) -> Response:
        httpx_client = httpx.Client(base_url=DEFAULT_WORKFLOW_BASE_ENDPOINT)
        url = urljoin(
            DEFAULT_WORKFLOW_BASE_ENDPOINT,
            "/api/workflows",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def _get_workflow(self) -> Response:
        httpx_client = httpx.Client(base_url=DEFAULT_WORKFLOW_BASE_ENDPOINT)
        workflow_id = self.get_parameter_value("workflow_id")
        url = urljoin(
            DEFAULT_WORKFLOW_BASE_ENDPOINT,
            f"/api/workflows/{workflow_id}",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def _purge_old_connections(self) -> None:
        connection_request: ListConnectionsForNodeRequest = ListConnectionsForNodeRequest(node_name=self.name)
        result = GriptapeNodes.NodeManager().on_list_connections_for_node_request(request=connection_request)
        flow_manager = GriptapeNodes.FlowManager()
        if isinstance(result, ListConnectionsForNodeResultSuccess):
            for con in result.incoming_connections:
                del_req: DeleteConnectionRequest = DeleteConnectionRequest(
                    source_parameter_name=con.source_parameter_name,
                    target_parameter_name=con.target_parameter_name,
                    source_node_name=con.source_node_name,
                    target_node_name=self.name,
                )
                del_result = flow_manager.on_delete_connection_request(request=del_req)
                if not isinstance(del_result, DeleteConnectionResultSuccess):
                    err_msg = f"Error deleting connection for node {self.name}: {del_result}"
                    raise TypeError(err_msg)
            for con in result.outgoing_connections:
                del_req: DeleteConnectionRequest = DeleteConnectionRequest(
                    source_parameter_name=con.source_parameter_name,
                    target_parameter_name=con.target_parameter_name,
                    source_node_name=self.name,
                    target_node_name=con.target_node_name,
                )
                del_result = flow_manager.on_delete_connection_request(request=del_req)
                if not isinstance(del_result, DeleteConnectionResultSuccess):
                    err_msg = f"Error deleting connection for node {self.name}: {del_result}"
                    raise TypeError(err_msg)
        else:
            err_msg = f"Error fetching connections for node {self.name}: {result}"
            raise TypeError(err_msg)

    def _purge_old_parameters(self, valid_parameter_names: set[str]) -> set[str]:
        # Always maintain these parameters
        valid_parameter_names.update(
            [
                "exec_in",
                "exec_out",
                "workflow_id",
            ]
        )

        modified_parameters_set = set()
        for param in self.parameters:
            if param.name not in valid_parameter_names:
                self.remove_parameter_element(param)
                modified_parameters_set.add(param.name)
        return modified_parameters_set

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Callback after a value has been set on this Node."""
        # If the workflow_id is set, we can fetch the workflow.
        if parameter.name == "workflow_id" and value is not None:
            try:
                response = self._get_workflow()
                workflow = response.json()
                self.workflow_details = workflow

                # If the targeted workflow is updated, we need to purge the old connections
                # since the workflow parameters have likely changed.
                self._purge_old_connections()

                # Additionally, we need to purge the old parameters for the Node,
                # and update the set of modified parameters.

                # Retrieve the input parameters modified, and update the set of modified parameters
                input_parameters_defined_for_workflow = {
                    i for i, v in cast("dict[str, Any]", workflow["input"]).items()
                }
                modified_input_parameters = self._purge_old_parameters(input_parameters_defined_for_workflow)
                modified_parameters_set.update(modified_input_parameters)

                # Retrieve the output parameters modified, and update the set of modified parameters
                output_parameters_defined_for_workflow = {
                    i for i, v in cast("dict[str, Any]", workflow["output"]).items()
                }
                modified_output_parameters = self._purge_old_parameters(output_parameters_defined_for_workflow)
                modified_parameters_set.update(modified_output_parameters)

                self.add_parameter(
                    Parameter(
                        name="workflow_name",
                        type="str",
                        input_types=["str"],
                        default_value=workflow["name"],
                        tooltip="The name of the published Nodes Workflow.",
                        allowed_modes={
                            ParameterMode.OUTPUT,
                        },
                        user_defined=False,
                        settable=False,
                    )
                )
                modified_parameters_set.add("workflow_name")

                for params in workflow["input"].values():
                    for param, info in params.items():
                        kwargs: dict[str, Any] = {**info}
                        kwargs["allowed_modes"] = {
                            ParameterMode.INPUT,
                        }
                        self.add_parameter(Parameter(**kwargs))
                        modified_parameters_set.add(param)
                for params in workflow["output"].values():
                    for param, info in params.items():
                        kwargs: dict[str, Any] = {**info}
                        kwargs["allowed_modes"] = {
                            ParameterMode.OUTPUT,
                        }
                        self.add_parameter(Parameter(**kwargs))
                        modified_parameters_set.add(param)

            except Exception as e:
                err_msg = f"Error fetching workflow: {e!s}"
                raise ValueError(err_msg) from e

    def validate_before_workflow_run(self) -> list[Exception] | None:
        # All env values are stored in the SecretsManager. Check if they exist using this method.
        exceptions = []

        def raise_error(msg: str) -> None:
            raise ValueError(msg)

        try:
            api_key = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

            if not api_key:
                msg = f"{API_KEY_ENV_VAR} is not defined"
                exceptions.append(KeyError(msg))

            if not self.get_parameter_value("workflow_id"):
                msg = "Workflow ID is not set. Configure the Node with a valid published workflow ID before running."
                exceptions.append(ValueError(msg))

            if (self.workflow_details.get("status", None)) not in ["READY"]:
                response = self._get_workflow()
                response.raise_for_status()
                workflow = response.json()
                if workflow["status"] == "PENDING":
                    msg = f"Workflow ID {self.get_parameter_value('workflow_id')} is currently {workflow['status']}. Please wait until the workflow status is 'READY' before running the Node."
                    exceptions.append(ValueError(msg))
                elif workflow["status"] == "ERROR":
                    structure_url = urljoin(
                        os.getenv("GRIPTAPE_CLOUD_API_BASE_URL", "https://cloud.griptape.ai"),
                        f"/structures/{self.get_parameter_value('workflow_id')}",
                    )
                    # TODO: Add details about a Workflow's status: https://github.com/griptape-ai/griptape-nodes/issues/1010
                    msg = f"Workflow ID {self.get_parameter_value('workflow_id')} is currently {workflow['status']}. Please check the Griptape Cloud Structure for more details: {structure_url}"
                    exceptions.append(ValueError(msg))
                self.workflow_details = workflow

        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)

        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def _get_workflow_run_input(self) -> dict[str, Any]:
        workflow_run_input: dict[str, Any] = {}

        for node_name, params in self.workflow_details["input"].items():
            for param_name in params:
                workflow_run_input[node_name] = {param_name: self.get_parameter_value(param_name)}

        return workflow_run_input

    def _create_workflow_run(self) -> Response:
        httpx_client = httpx.Client(base_url=DEFAULT_WORKFLOW_BASE_ENDPOINT)
        url = urljoin(
            DEFAULT_WORKFLOW_BASE_ENDPOINT,
            f"/api/workflows/{self.get_parameter_value('workflow_id')}/runs",
        )
        response = httpx_client.post(url, headers=self._get_headers(), json=self._get_workflow_run_input())
        response.raise_for_status()
        return response

    def _get_workflow_run(self, workflow_id: str, workflow_run_id: str) -> Response:
        httpx_client = httpx.Client(base_url=DEFAULT_WORKFLOW_BASE_ENDPOINT)
        url = urljoin(
            DEFAULT_WORKFLOW_BASE_ENDPOINT,
            f"/api/workflows/{workflow_id}/workflow-runs/{workflow_run_id}",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def _poll_workflow_run(self, workflow_id: str, workflow_run_id: str) -> Response:
        response = self._get_workflow_run(workflow_id, workflow_run_id)
        run_status = response.json()["status"]

        while run_status not in ["SUCCEEDED", "FAILED", "ERROR", "CANCELLED"]:
            response = self._get_workflow_run(workflow_id, workflow_run_id)
            run_status = response.json()["status"]
            time.sleep(3)

        return response

    def _process(self) -> Response:
        create_run_response = self._create_workflow_run()
        res_json = create_run_response.json()
        workflow_id = res_json["workflow_id"]
        workflow_run_id = res_json["id"]
        response = self._poll_workflow_run(workflow_id, workflow_run_id)

        response_data = response.json()
        if response_data["status"] == "SUCCEEDED" and response_data["output"]:
            for params in json.loads(response_data["output"]).values():
                for param, val in params.items():
                    if param in [param.name for param in self.parameters]:
                        self.append_value_to_parameter(param, value=val)
        else:
            run_url = urljoin(
                os.getenv("GRIPTAPE_CLOUD_API_BASE_URL", "https://cloud.griptape.ai"),
                f"/structures/{workflow_id}/runs/{workflow_run_id}",
            )
            err_msg = f"Workflow run failed with status: {response_data['status']}. Please check the Griptape Cloud Structure for more details: {run_url}"
            raise ValueError(err_msg)

        return Response(
            json=response_data,
            status_code=200,
        )

    def process(
        self,
    ) -> AsyncResult[None]:
        yield lambda: None
        self._process()
