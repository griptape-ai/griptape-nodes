from unittest.mock import ANY

import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import BaseNodeElement, Parameter, ParameterGroup

# Default status dict from BaseNodeElement.get_status() / StatusData.to_dict()
_DEFAULT_STATUS = {
    "hide": False,
    "hide_clear_button": True,
    "message": "",
    "title": None,
    "variant": "none",
}


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
            "status": _DEFAULT_STATUS,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "ui_options": {},
                            "children": [
                                {
                                    "element_id": "leaf1",
                                    "element_type": "BaseNodeElement",
                                    "parent_group_name": "group1",
                                    "status": _DEFAULT_STATUS,
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
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
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
                            "status": _DEFAULT_STATUS,
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
            "status": _DEFAULT_STATUS,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "ui_options": {},
                            "children": [
                                {
                                    "element_id": "leaf1",
                                    "element_type": "BaseNodeElement",
                                    "parent_group_name": "group1",
                                    "status": _DEFAULT_STATUS,
                                    "children": [
                                        {
                                            "element_id": "leaf3",
                                            "element_type": "BaseNodeElement",
                                            "parent_group_name": None,
                                            "status": _DEFAULT_STATUS,
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
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
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
                            "status": _DEFAULT_STATUS,
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
            "status": _DEFAULT_STATUS,
            "children": [
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": ANY,
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "children": [],
                        },
                        {
                            "element_id": ANY,
                            "element_type": "ParameterGroup",
                            "name": "group1",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
                            "ui_options": {},
                            "children": [],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "element_type": "BaseNodeElement",
                    "parent_group_name": None,
                    "status": _DEFAULT_STATUS,
                    "children": [
                        {
                            "element_id": "leaf2",
                            "element_type": "BaseNodeElement",
                            "parent_group_name": None,
                            "status": _DEFAULT_STATUS,
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
                            "status": _DEFAULT_STATUS,
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
