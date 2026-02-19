from unittest.mock import ANY

import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import (
    BadgeData,
    BaseNodeElement,
    NodeMessagePayload,
    Parameter,
    ParameterGroup,
)

# No badge by default; elements send badge: null until set_badge() is called.
NO_BADGE = None


class TestBaseNodeElement:
    @pytest.fixture
    def ui_element(self) -> BaseNodeElement:
        with BaseNodeElement() as root:
            with BaseNodeElement():
                BaseNodeElement()
                with ParameterGroup(name="group1"):
                    BaseNodeElement(element_id="leaf1")
            with BaseNodeElement():
                BaseNodeElement(element_id="leaf2")
                Parameter(
                    element_id="parameter",
                    name="test",
                    input_types=["str"],
                    type="str",
                    output_type="str",
                    tooltip="test",
                )

        return root

    def test_init(self) -> None:
        assert BaseNodeElement()

        with BaseNodeElement() as root:
            child = BaseNodeElement()

            assert root._children == [child]

    def test__enter__(self) -> None:
        with BaseNodeElement() as ui:
            assert ui

    def test__repr__(self) -> None:
        assert repr(BaseNodeElement()) == "BaseNodeElement(self.children=[])"

    def test_to_dict(self, ui_element: BaseNodeElement) -> None:
        assert ui_element.to_dict() == {
            "element_id": ANY,
            "element_type": "BaseNodeElement",
            "parent_group_name": None,
            "badge": NO_BADGE,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "ui_options": {},
                            "children": [
                                {
                                    "element_id": "leaf1",
                                    "element_type": "BaseNodeElement",
                                    "parent_group_name": "group1",
                                    "badge": NO_BADGE,
                                    "children": [],
                                }
                            ],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "element_id": "parameter",
                            "element_type": "Parameter",
                            "children": [],
                            "default_value": None,
                            "input_types": [
                                "str",
                            ],
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "name": "test",
                            "parent_group_name": None,
                            "output_type": "str",
                            "tooltip": "test",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "type": "str",
                            "settable": True,
                            "serializable": True,
                            "private": False,
                            "ui_options": {},
                            "parent_container_name": None,
                            "parent_element_name": None,
                            "badge": NO_BADGE,
                        },
                    ],
                },
            ],
        }

    def test_add_child(self, ui_element: BaseNodeElement) -> None:
        found_element = ui_element.find_element_by_id("leaf1")
        assert found_element is not None
        found_element.add_child(BaseNodeElement(element_id="leaf3"))

        assert ui_element.to_dict() == {
            "element_id": ANY,
            "element_type": "BaseNodeElement",
            "parent_group_name": None,
            "badge": NO_BADGE,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "ui_options": {},
                            "children": [
                                {
                                    "element_id": "leaf1",
                                    "element_type": "BaseNodeElement",
                                    "parent_group_name": "group1",
                                    "badge": NO_BADGE,
                                    "children": [
                                        {
                                            "element_id": "leaf3",
                                            "element_type": "BaseNodeElement",
                                            "parent_group_name": None,
                                            "badge": NO_BADGE,
                                            "children": [],
                                        },
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "children": [],
                            "default_value": None,
                            "element_id": "parameter",
                            "element_type": "Parameter",
                            "input_types": [
                                "str",
                            ],
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "name": "test",
                            "parent_group_name": None,
                            "output_type": "str",
                            "tooltip": "test",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "type": "str",
                            "settable": True,
                            "serializable": True,
                            "private": False,
                            "ui_options": {},
                            "parent_container_name": None,
                            "parent_element_name": None,
                            "badge": NO_BADGE,
                        },
                    ],
                },
            ],
        }

    def test_find_element_by_id(self, ui_element: BaseNodeElement) -> None:
        element = ui_element.find_element_by_id("leaf1")
        assert element is not None
        assert element.element_id == "leaf1"

        element = ui_element.find_element_by_id("leaf2")
        assert element is not None
        assert element.element_id == "leaf2"

    @pytest.mark.parametrize(("element_type", "num_expected"), [(BaseNodeElement, 7), (Parameter, 1)])
    def test_find_elements_by_type(self, ui_element: BaseNodeElement, element_type: type, num_expected: int) -> None:
        elements = ui_element.find_elements_by_type(element_type)
        assert len(elements) == num_expected

    def test_remove_child(self, ui_element: BaseNodeElement) -> None:
        element_to_remove = ui_element.find_element_by_id("leaf1")

        assert element_to_remove is not None

        ui_element.remove_child(element_to_remove)

        assert ui_element.to_dict() == {
            "element_id": ANY,
            "element_type": "BaseNodeElement",
            "parent_group_name": None,
            "badge": NO_BADGE,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "ui_options": {},
                            "children": [],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "badge": NO_BADGE,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "badge": NO_BADGE,
                            "children": [],
                        },
                        {
                            "element_id": "parameter",
                            "element_type": "Parameter",
                            "children": [],
                            "default_value": None,
                            "input_types": [
                                "str",
                            ],
                            "is_user_defined": False,
                            "mode_allowed_input": True,
                            "mode_allowed_output": True,
                            "mode_allowed_property": True,
                            "name": "test",
                            "parent_group_name": None,
                            "output_type": "str",
                            "tooltip": "test",
                            "tooltip_as_input": None,
                            "tooltip_as_output": None,
                            "tooltip_as_property": None,
                            "type": "str",
                            "settable": True,
                            "serializable": True,
                            "private": False,
                            "ui_options": {},
                            "parent_container_name": None,
                            "parent_element_name": None,
                            "badge": NO_BADGE,
                        },
                    ],
                },
            ],
        }

    def test_get_current(self) -> None:
        with BaseNodeElement() as ui:
            assert ui
            assert ui.get_current() == ui
        assert ui.get_current() is None


class TestBadgeData:
    def test_to_dict_includes_icon_and_color_when_set(self) -> None:
        badge = BadgeData(
            variant="info",
            message="Drop files here",
            icon="upload-cloud",
            color="#3b82f6",
        )
        result = badge.to_dict()
        assert result["variant"] == "info"
        assert result["message"] == "Drop files here"
        assert result["icon"] == "upload-cloud"
        assert result["color"] == "#3b82f6"

    def test_to_dict_omits_icon_and_color_when_not_set(self) -> None:
        badge = BadgeData(variant="info", message="Info message")
        result = badge.to_dict()
        assert "icon" not in result
        assert "color" not in result

    def test_set_badge_with_icon_and_color(self) -> None:
        element = BaseNodeElement()
        element.set_badge(
            variant="info",
            message="Upload",
            icon="upload-cloud",
            color="#3b82f6",
        )
        badge = element.get_badge()
        assert badge is not None
        assert badge.variant == "info"
        assert badge.icon == "upload-cloud"
        assert badge.color == "#3b82f6"
        assert badge.to_dict()["icon"] == "upload-cloud"
        assert badge.to_dict()["color"] == "#3b82f6"

    def test_apply_badge_from_message_data_with_icon_and_color(self) -> None:
        element = BaseNodeElement()
        element.set_badge(variant="info", message="Initial")
        payload = NodeMessagePayload(
            data={
                "variant": "info",
                "message": "Updated",
                "icon": "upload-cloud",
                "color": "#3b82f6",
            }
        )
        result = element.on_message_received("set_badge", payload)
        assert result is not None
        assert result.success is True
        badge = element.get_badge()
        assert badge is not None
        assert badge.message == "Updated"
        assert badge.icon == "upload-cloud"
        assert badge.color == "#3b82f6"

    def test_parameter_with_badge_icon_and_color(self) -> None:
        badge = BadgeData(
            variant="info",
            message="Drop files here",
            icon="upload-cloud",
            color="#3b82f6",
        )
        param = Parameter(
            name="test",
            input_types=["str"],
            type="str",
            output_type="str",
            tooltip="test",
            badge=badge,
        )
        badge_result = param.get_badge()
        assert badge_result is not None
        assert badge_result.icon == "upload-cloud"
        assert badge_result.color == "#3b82f6"
        assert badge_result.to_dict()["icon"] == "upload-cloud"
        assert badge_result.to_dict()["color"] == "#3b82f6"

    def test_set_badge_with_color(self) -> None:
        """set_badge accepts color (hex, rgb, etc.)."""
        element = BaseNodeElement()
        element.set_badge(variant="info", color="#3b82f6")
        badge = element.get_badge()
        assert badge is not None
        assert badge.color == "#3b82f6"


class TestParameterGroup:
    def test_init(self) -> None:
        assert ParameterGroup(name="test")


class TestParameter:
    def test_init(self) -> None:
        assert Parameter(name="test", input_types=["str"], type="str", output_type="str", tooltip="test")

    def test_settable_property(self) -> None:
        """Test that settable property works correctly and is included in serialization."""
        # Test default value
        param = Parameter(name="test", input_types=["str"], type="str", output_type="str", tooltip="test")
        assert param.settable is True

        # Test setting to False
        param_false = Parameter(
            name="test", input_types=["str"], type="str", output_type="str", tooltip="test", settable=False
        )
        assert param_false.settable is False

        # Test property setter
        param.settable = False
        assert param.settable is False
        param.settable = True
        assert param.settable is True

        # Test serialization includes settable
        param_dict = param.to_dict()
        assert "settable" in param_dict
        assert param_dict["settable"] is True

        param_false_dict = param_false.to_dict()
        assert "settable" in param_false_dict
        assert param_false_dict["settable"] is False
