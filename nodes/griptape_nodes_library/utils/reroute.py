from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class Reroute(DataNode):
    # Track the incoming and outgoing connections to choose our allowed types.
    # I'd use sets for faster removal but I don't know if I want to hash Parameter objects
    incoming_connection_params: list[Parameter]
    outgoing_connection_params: list[Parameter]

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.incoming_connection_params = []
        self.outgoing_connection_params = []

        passthru = Parameter(
            name="passThru",
            input_types=["Any"],
            output_type="Any",
            default_value=None,
            tooltip="",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(passthru)

    @staticmethod
    def intersection_of_allowed_types(*allowed_type_lists) -> list[str]:  # noqa: C901
        """Intersects allowed types lists.

        Find intersection of N lists with special rules:
        1. Preserve order where possible
        2. "Any" is a wildcard that matches any string.

        Args:
            *allowed_type_lists: Variable number of string lists
        Returns:
            List containing the intersection with preserved order
        One day we will handle things like dict[Any, List[Tuple[Str, Any]]]
        ...but today is not that day.
        """
        if len(allowed_type_lists) == 0:
            return ["Any"]

        if len(allowed_type_lists) == 1:
            return allowed_type_lists[0].copy()

        # Check which lists contain "Any"
        has_any = [("Any" in lst) for lst in allowed_type_lists]

        # Initialize result with first list's items
        all_items = set()
        for lst in allowed_type_lists:
            all_items.update(lst)

        result = []

        # If all lists have "Any", include it in the result
        if all(has_any):
            result.append("Any")

        # Process each list in order
        for list_index, current_list in enumerate(allowed_type_lists):
            for item in current_list:
                if item == "Any":
                    # Skip "Any" as it's already handled
                    continue

                # Check if item should be in result
                should_include = True

                for other_index, other_list in enumerate(allowed_type_lists):
                    if other_index == list_index:
                        continue

                    # Item should be included if it's in the other list
                    # OR if the other list contains "Any"
                    if item not in other_list and not has_any[other_index]:
                        should_include = False
                        break

                if should_include and item not in result:
                    result.append(item)

        return result

    def update_allowed_types_based_on_connection_status(self, parameter: Parameter) -> None:
        # Our allowed types is the intersection of all of our current connections.
        all_allowed_types = []
        for incoming_connection_param in self.incoming_connection_params:
            allowed_type = incoming_connection_param.output_type
            all_allowed_types.append(allowed_type)
        for outgoing_connection_param in self.outgoing_connection_params:
            allowed_types = outgoing_connection_param.input_types
            all_allowed_types.append(allowed_types)

        intersection = Reroute.intersection_of_allowed_types(*all_allowed_types)
        parameter.input_types = intersection
        parameter.output_type = intersection[0]

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        self.incoming_connection_params.append(source_parameter)
        self.update_allowed_types_based_on_connection_status(parameter=target_parameter)

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        self.outgoing_connection_params.append(target_parameter)
        self.update_allowed_types_based_on_connection_status(parameter=source_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        self.incoming_connection_params.remove(source_parameter)
        self.update_allowed_types_based_on_connection_status(parameter=target_parameter)

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        self.outgoing_connection_params.remove(target_parameter)
        self.update_allowed_types_based_on_connection_status(parameter=source_parameter)

    def process(self) -> None:
        pass
