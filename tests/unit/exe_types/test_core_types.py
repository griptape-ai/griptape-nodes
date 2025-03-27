from unittest.mock import ANY

import pytest

from griptape_nodes.exe_types.core_types import BaseNodeElement, Parameter, ParameterGroup


class TestBaseNodeElement:
    @pytest.fixture
    def ui_element(self) -> BaseNodeElement:
        with BaseNodeElement() as root:
            with BaseNodeElement():
                BaseNodeElement()
                with BaseNodeElement():
                    BaseNodeElement(element_id="leaf1")
            with BaseNodeElement():
                BaseNodeElement(element_id="leaf2")
                Parameter(element_id="parameter", name="test", allowed_types=["str"], tooltip="test")

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

    def test_to_dict(self, ui_element) -> None:
        assert ui_element.to_dict() == {
            "element_id": ANY,
            "children": [
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": ANY, "children": []},
                        {"element_id": ANY, "children": [{"element_id": "leaf1", "children": []}]},
                    ],
                },
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": "leaf2", "children": []},
                        {
                            "children": [],
                            "element_id": "parameter",
                        },
                    ],
                },
            ],
        }

    def test_add_child(self, ui_element) -> None:
        ui_element.find_element_by_id("leaf1").add_child(BaseNodeElement(element_id="leaf3"))

        assert ui_element.to_dict() == {
            "element_id": ANY,
            "children": [
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": ANY, "children": []},
                        {
                            "element_id": ANY,
                            "children": [
                                {
                                    "element_id": "leaf1",
                                    "children": [
                                        {"element_id": "leaf3", "children": []},
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": "leaf2", "children": []},
                        {
                            "children": [],
                            "element_id": "parameter",
                        },
                    ],
                },
            ],
        }

    def test_find_element_by_id(self, ui_element) -> None:
        assert ui_element.find_element_by_id("leaf1").element_id == "leaf1"
        assert ui_element.find_element_by_id("leaf2").element_id == "leaf2"

    @pytest.mark.parametrize(("element_type", "num_expected"), [(BaseNodeElement, 7), (Parameter, 1)])
    def test_find_elements_by_type(self, ui_element, element_type, num_expected) -> None:
        elements = ui_element.find_elements_by_type(element_type)
        assert len(elements) == num_expected

    def test_remove_child(self, ui_element) -> None:
        element_to_remove = ui_element.find_element_by_id("leaf1")

        ui_element.remove_child(element_to_remove)

        assert ui_element.to_dict() == {
            "element_id": ANY,
            "children": [
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": ANY, "children": []},
                        {
                            "element_id": ANY,
                            "children": [],
                        },
                    ],
                },
                {
                    "element_id": ANY,
                    "children": [
                        {"element_id": "leaf2", "children": []},
                        {
                            "children": [],
                            "element_id": "parameter",
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
        assert ParameterGroup(group_name="test")


class TestParameter:
    def test_init(self) -> None:
        assert Parameter(name="test", allowed_types=["str"], tooltip="test")
