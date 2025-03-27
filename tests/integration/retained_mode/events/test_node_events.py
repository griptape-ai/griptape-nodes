from typing import Any
from unittest.mock import ANY

import pytest

from griptape_nodes.retained_mode.events.base_events import EventResult_Success
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    GetAllNodeInfoRequest,
    GetAllNodeInfoResult_Success,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestNodeEvents:
    @pytest.fixture
    def create_node_result(self, flow) -> Any:  # noqa: ARG002
        request = CreateNodeRequest(node_type="gnRunAgent", override_parent_flow_name="canvas")
        result = GriptapeNodes.handle_request(request)

        return result

    def test_GetAllNodeInfoResult(self, create_node_result) -> None:
        request = GetAllNodeInfoRequest(node_name=create_node_result.node_name)
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, GetAllNodeInfoResult_Success)

        assert EventResult_Success(request=request, result=result).dict() == {
            "event_type": "EventResult_Success",
            "request": {
                "node_name": "gnRunAgent_1",
                "request_id": None,
            },
            "request_type": "GetAllNodeInfoRequest",
            "result": {
                "connections": {
                    "incoming_connections": [],
                    "outgoing_connections": [],
                },
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
                    "agent": {
                        "details": {
                            "element_id": ANY,
                            "allowed_types": [
                                "Agent",
                            ],
                            "default_value": None,
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "tooltip": "",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "ui_options": None,
                        },
                        "value": {
                            "data_type": "<class 'NoneType'>",
                            "value": None,
                        },
                    },
                    "prompt": {
                        "details": {
                            "element_id": ANY,
                            "allowed_types": [
                                "str",
                            ],
                            "default_value": "",
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "tooltip": "",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "ui_options": {
                                "audio_type_options": None,
                                "boolean_type_options": None,
                                "display": True,
                                "fancy_dropdown_options": None,
                                "image_type_options": None,
                                "list_container_options": None,
                                "number_type_options": None,
                                "property_array_type_options": None,
                                "simple_dropdown_options": None,
                                "string_type_options": {
                                    "markdown": None,
                                    "multiline": True,
                                    "placeholder_text": None,
                                },
                                "video_type_options": None,
                            },
                        },
                        "value": {
                            "data_type": "str",
                            "value": "",
                        },
                    },
                    "prompt_driver": {
                        "details": {
                            "element_id": ANY,
                            "allowed_types": [
                                "BasePromptDriver",
                            ],
                            "default_value": None,
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "tooltip": "",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "ui_options": None,
                        },
                        "value": {
                            "data_type": "<class 'NoneType'>",
                            "value": None,
                        },
                    },
                    "prompt_model": {
                        "details": {
                            "element_id": ANY,
                            "allowed_types": [
                                "str",
                            ],
                            "default_value": "gpt-4o",
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "tooltip": "",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "ui_options": None,
                        },
                        "value": {
                            "data_type": "str",
                            "value": "gpt-4o",
                        },
                    },
                },
                "root_node_element": {
                    "children": [
                        {
                            "children": [],
                            "element_id": ANY,
                            "element_type": "Parameter",
                        },
                        {
                            "children": [
                                {
                                    "children": [],
                                    "element_id": ANY,
                                    "element_type": "Parameter",
                                },
                                {
                                    "children": [],
                                    "element_id": ANY,
                                    "element_type": "Parameter",
                                },
                                {
                                    "children": [],
                                    "element_id": ANY,
                                    "element_type": "Parameter",
                                },
                            ],
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                        },
                        {
                            "children": [
                                {
                                    "children": [],
                                    "element_id": ANY,
                                    "element_type": "Parameter",
                                },
                                {
                                    "children": [],
                                    "element_type": "Parameter",
                                    "element_id": ANY,
                                },
                                {
                                    "children": [],
                                    "element_id": ANY,
                                    "element_type": "Parameter",
                                },
                            ],
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                        },
                    ],
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                },
            },
            "result_type": "GetAllNodeInfoResult_Success",
            "retained_mode": None,
        }
