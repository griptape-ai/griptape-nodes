"""Proxy node that stands in for a node executing in a library worker subprocess.

Created by LibraryRegistry when a library is out-of-process. Participates
in the DAG like any normal BaseNode. On aprocess(), sends an execute request
to the worker and populates parameter_output_values from the response.
"""

from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger(__name__)

# Mapping from mode name strings to ParameterMode enum values
_MODE_MAP = {
    "OUTPUT": ParameterMode.OUTPUT,
    "INPUT": ParameterMode.INPUT,
    "PROPERTY": ParameterMode.PROPERTY,
}


class ProxyNode(BaseNode):
    """A proxy that stands in for a node executing in a library worker subprocess.

    Created from a serialized root_ui_element tree received from the worker
    after the real node is instantiated there. Participates in the DAG like
    any normal BaseNode. When aprocess() is called, it sends an execute request
    to the worker and populates parameter_output_values from the response.
    """

    _library_name: str
    _node_type: str
    _selected_control_output_name: str | None

    def __init__(
        self,
        name: str,
        library_name: str,
        node_type: str,
        root_element_tree: dict[str, Any] | None = None,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name=name, metadata=metadata)
        self._library_name = library_name
        self._node_type = node_type
        self._selected_control_output_name = None
        if root_element_tree is not None:
            self._build_from_element_tree(root_element_tree)

    @property
    def library_name(self) -> str:
        return self._library_name

    @property
    def node_type(self) -> str:
        return self._node_type

    def _build_from_element_tree(self, tree: dict[str, Any]) -> None:
        """Reconstruct the node's element hierarchy from the serialized tree.

        Walks the tree in order, creating ParameterGroups and Parameters so
        that the proxy mirrors the real node's structure exactly.
        """
        for child in tree.get("children", []):
            self._build_element(child, parent_group=None)

    _GROUP_ELEMENT_TYPES = frozenset({"ParameterGroup", "ParameterButtonGroup"})

    def _build_element(self, data: dict[str, Any], parent_group: ParameterGroup | None) -> None:
        """Recursively build an element from its serialized dict."""
        element_type = data.get("element_type", "")

        if element_type in self._GROUP_ELEMENT_TYPES:
            self._build_group(data, parent_group)
        elif element_type:
            self._build_parameter(data, parent_group)

    def _build_group(self, data: dict[str, Any], parent_group: ParameterGroup | None) -> None:
        """Create a ParameterGroup and recursively build its children."""
        group = ParameterGroup(name=data.get("name", ""), ui_options=data.get("ui_options"))

        if parent_group is not None:
            parent_group.add_child(group)
        else:
            self.add_node_element(group)

        for child in data.get("children", []):
            self._build_element(child, parent_group=group)

    def _build_parameter(self, data: dict[str, Any], parent_group: ParameterGroup | None) -> None:
        """Create a Parameter from its serialized dict and add it to the node."""
        allowed_modes: set[ParameterMode] | None = None
        if data.get("mode_allowed_input") is not None:
            allowed_modes = set()
            if data.get("mode_allowed_input"):
                allowed_modes.add(ParameterMode.INPUT)
            if data.get("mode_allowed_property"):
                allowed_modes.add(ParameterMode.PROPERTY)
            if data.get("mode_allowed_output"):
                allowed_modes.add(ParameterMode.OUTPUT)

        display_name = None
        ui_options = data.get("ui_options")
        if ui_options:
            display_name = ui_options.get("display_name")

        param = Parameter(
            name=data.get("name", ""),
            type=data.get("type"),
            input_types=data.get("input_types"),
            output_type=data.get("output_type"),
            default_value=data.get("default_value"),
            tooltip=data.get("tooltip") or data.get("name", ""),
            allowed_modes=allowed_modes,
            ui_options=ui_options,
            element_type=data.get("element_type"),
            display_name=display_name,
            parent_element_name=parent_group.name if parent_group is not None else None,
        )
        self.add_parameter(param)

    def get_next_control_output(self) -> Parameter | None:
        """Return the control output selected by the worker's execution."""
        if self._selected_control_output_name is not None:
            param = self.get_parameter_by_name(self._selected_control_output_name)
            if param is not None:
                return param

        # Fall back to default behavior (first control output)
        return super().get_next_control_output()

    def allow_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        """ProxyNode allows all incoming connections."""
        return True

    def allow_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        """ProxyNode allows all outgoing connections."""
        return True

    def process(self) -> None:
        """Not used; aprocess() handles execution."""

    async def aprocess(self) -> None:
        """Send execute request to worker and populate outputs from response."""
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        process_manager = GriptapeNodes.LibraryProcessManager()

        entry_param_name = None
        if self._entry_control_parameter is not None:
            entry_param_name = self._entry_control_parameter.name

        # Collect parameter values, aggregating container children into
        # their parent values (e.g., ParameterList children become a list).
        # Child parameter UUIDs differ between the proxy and the real node,
        # so we must send aggregated values keyed by the parent name.
        param_values: dict[str, Any] = {}
        for param in self.parameters:
            if param.parent_container_name is not None:
                continue
            value = self.get_parameter_value(param.name)
            if value is not None:
                param_values[param.name] = value

        result = await process_manager.execute_node(
            library_name=self._library_name,
            node_name=self.name,
            parameter_values=param_values,
            entry_control_parameter_name=entry_param_name,
        )

        # Populate output values from worker response
        for key, value in result.parameter_output_values.items():
            self.parameter_output_values[key] = value

        # Record which control output the worker selected
        self._selected_control_output_name = result.next_control_output_name
