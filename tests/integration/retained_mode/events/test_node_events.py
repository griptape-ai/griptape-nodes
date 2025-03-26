from typing import Any

import pytest

from griptape_nodes.exe_types.core_types import ParameterUIOptions
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    GetAllNodeInfoRequest,
    GetAllNodeInfoResult_Success,
    GetParameterDetailsResult_Success,
    GetParameterValueResult_Success,
    ListConnectionsForNodeResult_Success,
    ParameterInfoValue,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestNodeEvents:
    @pytest.fixture
    def create_node_result(self, flow) -> Any:  # noqa: ARG002
        request = CreateNodeRequest(node_type="gnRunAgent", override_parent_flow_name="canvas")
        result = GriptapeNodes.handle_request(request)

        return result

    def test_GetNodeMetadataRequest(self, create_node_result) -> None:
        request = GetAllNodeInfoRequest(node_name=create_node_result.node_name)
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, GetAllNodeInfoResult_Success)
        assert result.__dict__ == {
            "connections": ListConnectionsForNodeResult_Success(
                incoming_connections=[],
                outgoing_connections=[],
            ),
            "metadata": {
                "library": "Griptape Nodes Library",
                "library_node_metadata": {
                    "category": "Agent",
                    "description": "Griptape Agent that can execute prompts and use tools",
                    "display_name": "Run Agent",
                },
                "node_type": "gnRunAgent",
            },
            "node_resolution_state": "UNRESOLVED",
            "parameter_name_to_info": {
                "agent": ParameterInfoValue(
                    details=GetParameterDetailsResult_Success(
                        allowed_types=[
                            "Agent",
                        ],
                        default_value=None,
                        tooltip="",
                        tooltip_as_input=None,
                        tooltip_as_property=None,
                        tooltip_as_output=None,
                        mode_allowed_input=True,
                        mode_allowed_property=True,
                        mode_allowed_output=True,
                        is_user_defined=False,
                        ui_options=None,
                    ),
                    value=GetParameterValueResult_Success(
                        data_type="<class 'NoneType'>",
                        value=None,
                    ),
                ),
                "prompt": ParameterInfoValue(
                    details=GetParameterDetailsResult_Success(
                        allowed_types=[
                            "str",
                        ],
                        default_value="",
                        tooltip="",
                        tooltip_as_input=None,
                        tooltip_as_property=None,
                        tooltip_as_output=None,
                        mode_allowed_input=True,
                        mode_allowed_property=True,
                        mode_allowed_output=True,
                        is_user_defined=False,
                        ui_options=ParameterUIOptions(
                            string_type_options=ParameterUIOptions.StringType(
                                multiline=True,
                                markdown=None,
                                placeholder_text=None,
                            ),
                            boolean_type_options=None,
                            number_type_options=None,
                            simple_dropdown_options=None,
                            fancy_dropdown_options=None,
                            image_type_options=None,
                            video_type_options=None,
                            audio_type_options=None,
                            property_array_type_options=None,
                            list_container_options=None,
                            display=True,
                        ),
                    ),
                    value=GetParameterValueResult_Success(
                        data_type="str",
                        value="",
                    ),
                ),
                "prompt_driver": ParameterInfoValue(
                    details=GetParameterDetailsResult_Success(
                        allowed_types=[
                            "BasePromptDriver",
                        ],
                        default_value=None,
                        tooltip="",
                        tooltip_as_input=None,
                        tooltip_as_property=None,
                        tooltip_as_output=None,
                        mode_allowed_input=True,
                        mode_allowed_property=True,
                        mode_allowed_output=True,
                        is_user_defined=False,
                        ui_options=None,
                    ),
                    value=GetParameterValueResult_Success(
                        data_type="<class 'NoneType'>",
                        value=None,
                    ),
                ),
                "prompt_model": ParameterInfoValue(
                    details=GetParameterDetailsResult_Success(
                        allowed_types=[
                            "str",
                        ],
                        default_value="gpt-4o",
                        tooltip="",
                        tooltip_as_input=None,
                        tooltip_as_property=None,
                        tooltip_as_output=None,
                        mode_allowed_input=True,
                        mode_allowed_property=True,
                        mode_allowed_output=True,
                        is_user_defined=False,
                        ui_options=None,
                    ),
                    value=GetParameterValueResult_Success(
                        data_type="str",
                        value="gpt-4o",
                    ),
                ),
            },
        }
