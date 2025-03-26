import pytest

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, UIElement


class TestUIElement:
    @pytest.fixture
    def ui_element(self) -> UIElement:
        with UIElement() as root:
            with UIElement():
                UIElement()
                with UIElement():
                    UIElement(element_id="leaf1")
            with UIElement():
                UIElement(element_id="leaf2")

        return root

    def test_init(self) -> None:
        assert UIElement()

        with UIElement() as root:
            child = UIElement()

            assert root.children == [child]

    def test__enter__(self) -> None:
        with UIElement() as ui:
            assert ui

    def test__repr__(self) -> None:
        assert repr(UIElement()) == "UIElement(self.children=[])"

    def test_to_dict(self, ui_element) -> None:
        assert ui_element.to_dict() == {
            "element_id": None,
            "children": [
                {
                    "element_id": None,
                    "children": [
                        {"element_id": None, "children": []},
                        {"element_id": None, "children": [{"element_id": "leaf1", "children": []}]},
                    ],
                },
                {"element_id": None, "children": [{"element_id": "leaf2", "children": []}]},
            ],
        }

    def test_add_child(self, ui_element) -> None:
        ui_element.find_element_by_id("leaf1").add_child(UIElement(element_id="leaf3"))

        assert ui_element.to_dict() == {
            "element_id": None,
            "children": [
                {
                    "element_id": None,
                    "children": [
                        {"element_id": None, "children": []},
                        {
                            "element_id": None,
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
                {"element_id": None, "children": [{"element_id": "leaf2", "children": []}]},
            ],
        }

    def test_find_element_by_id(self, ui_element) -> None:
        assert ui_element.find_element_by_id("leaf1").element_id == "leaf1"
        assert ui_element.find_element_by_id("leaf2").element_id == "leaf2"

    def test_remove_child(self, ui_element) -> None:
        element_to_remove = ui_element.find_element_by_id("leaf1")

        ui_element.remove_child(element_to_remove)

        assert ui_element.to_dict() == {
            "element_id": None,
            "children": [
                {
                    "element_id": None,
                    "children": [
                        {"element_id": None, "children": []},
                        {
                            "element_id": None,
                            "children": [],
                        },
                    ],
                },
                {"element_id": None, "children": [{"element_id": "leaf2", "children": []}]},
            ],
        }

    def test_get_current(self) -> None:
        with UIElement() as ui:
            assert ui
            assert ui.get_current() == ui
        assert ui.get_current() is None


class TestParameterGroup:
    def test_init(self) -> None:
        assert ParameterGroup(group_name="test")


class TestParameter:
    def test_init(self) -> None:
        assert Parameter(name="test", allowed_types=["str"], tooltip="test")
