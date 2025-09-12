import logging
from copy import deepcopy
from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options

logger = logging.getLogger("griptape_nodes")


class AddToList(ControlNode):
    """AddToList Node that takes a list, an item, and an optional index.

    It adds the item to the list at the specified index, or at the end of the list if no index is provided.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items_list = Parameter(
            name="items",
            tooltip="List of items to add to",
            input_types=["list"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.items_list)

        self.item = Parameter(
            name="item",
            tooltip="Item to add to the list",
            input_types=["any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.item)

        self.position = Parameter(
            name="position",
            tooltip="Position to add the value to the list",
            input_types=["str"],
            allowed_modes={ParameterMode.PROPERTY},
            default_value="end",
        )
        self.add_parameter(self.position)
        self.position.add_trait(Options(choices=["start", "end", "index"]))
        self.index = Parameter(
            name="index",
            tooltip="Index to add the value to the list",
            type="int",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            ui_options={"hide": True},
        )
        self.add_parameter(self.index)

        self.output = Parameter(
            name="output",
            tooltip="Output list",
            output_type="list",
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output)

        # Advanced Behavior parameter group (collapsed by default)
        advanced_group = ParameterGroup(name="Advanced", ui_options={"collapsed": True})

        with advanced_group:
            self.skip_empty_values = Parameter(
                name="skip_empty_values",
                type="bool",
                default_value=True,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="If True, skip adding None values to the list. If False, add None values normally.",
            )

        self.add_node_element(advanced_group)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "position":
            if value in {"start", "end"}:
                self.hide_parameter_by_name("index")
            elif value == "index":
                self.show_parameter_by_name("index")
        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate inputs before processing."""
        exceptions = []

        # Validate list input - let upstream handle type checking, we just need to handle None gracefully
        list_values = self.get_parameter_value("items")
        if list_values is not None and not isinstance(list_values, list):
            exceptions.append(
                TypeError(
                    f"AddToList node '{self.name}' expected 'items' parameter to be a list, but got {type(list_values).__name__}"
                )
            )

        # Validate index parameter when position is "index"
        position = self.get_parameter_value("position")
        if position == "index":
            index = self.get_parameter_value("index")
            if index is None:
                exceptions.append(
                    ValueError(
                        f"AddToList node '{self.name}' requires an 'index' value when position is set to 'index'"
                    )
                )
            elif not isinstance(index, int):
                exceptions.append(
                    TypeError(
                        f"AddToList node '{self.name}' expected 'index' parameter to be an integer, but got {type(index).__name__}"
                    )
                )

        return exceptions if exceptions else None

    def process(self) -> None:
        # Get the list of items from the input parameter
        list_values = self.get_parameter_value("items")
        if list_values is None:
            # Generate a new list for the user.
            list_values = []
            logger.debug("AddToList node '%s' received None as 'items' parameter, creating new empty list", self.name)

        item = self.get_parameter_value("item")
        skip_empty_values = self.get_parameter_value("skip_empty_values")

        new_list = deepcopy(list_values)

        # Only add item if it's not None or if we're not skipping empty values
        if item is not None or not skip_empty_values:
            position = self.get_parameter_value("position")
            if position == "start":
                index = 0
            elif position == "end":
                index = len(new_list)
            else:
                index = self.get_parameter_value("index")

            # Let insert handle any index errors naturally
            new_list.insert(index, item)
        else:
            logger.debug(
                "AddToList node '%s' received None as 'item' parameter, skipping addition due to skip_empty_values=True",
                self.name,
            )

        # Single path to success - always set outputs at the bottom
        self.parameter_output_values["output"] = new_list
        self.parameter_output_values["skip_empty_values"] = skip_empty_values
