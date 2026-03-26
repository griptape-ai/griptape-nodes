"""Proxy node that stands in for a node executing in a library worker subprocess.

Created by LibraryRegistry when a library is out-of-process. Participates
in the DAG like any normal BaseNode. On aprocess(), sends an execute request
to the worker and populates parameter_output_values from the response.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass
class ParameterSchema:
    """Serialized parameter definition for proxy node construction.

    Sent from the worker after real node creation so the proxy can mirror
    the node's parameter interface.
    """

    name: str
    type: str | None = None
    input_types: list[str] | None = None
    output_type: str | None = None
    allowed_modes: list[str] | None = None
    default_value: Any = None
    tooltip: str = ""
    ui_options: dict[str, Any] | None = None
    element_type: str | None = None
    display_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "input_types": self.input_types,
            "output_type": self.output_type,
            "allowed_modes": self.allowed_modes,
            "default_value": self.default_value,
            "tooltip": self.tooltip,
            "ui_options": self.ui_options,
            "element_type": self.element_type,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParameterSchema:
        return cls(
            name=data["name"],
            type=data.get("type"),
            input_types=data.get("input_types"),
            output_type=data.get("output_type"),
            allowed_modes=data.get("allowed_modes"),
            default_value=data.get("default_value"),
            tooltip=data.get("tooltip", ""),
            ui_options=data.get("ui_options"),
            element_type=data.get("element_type"),
            display_name=data.get("display_name"),
        )


@dataclass
class ParameterGroupSchema:
    """Serialized parameter group definition for proxy node construction."""

    name: str
    ui_options: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ui_options": self.ui_options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParameterGroupSchema:
        return cls(
            name=data["name"],
            ui_options=data.get("ui_options"),
        )


class ProxyNode(BaseNode):
    """A proxy that stands in for a node executing in a library worker subprocess.

    Created from a parameter schema received from the worker after the real node
    is instantiated there. Participates in the DAG like any normal BaseNode.
    When aprocess() is called, it sends an execute request to the worker and
    populates parameter_output_values from the response.
    """

    _library_name: str
    _node_type: str
    _selected_control_output_name: str | None

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        library_name: str,
        node_type: str,
        parameter_schemas: list[ParameterSchema],
        parameter_group_schemas: list[ParameterGroupSchema] | None = None,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name=name, metadata=metadata)
        self._library_name = library_name
        self._node_type = node_type
        self._selected_control_output_name = None
        self._build_parameter_groups_from_schema(parameter_group_schemas or [])
        self._build_parameters_from_schema(parameter_schemas)

    @property
    def library_name(self) -> str:
        return self._library_name

    @property
    def node_type(self) -> str:
        return self._node_type

    def _build_parameter_groups_from_schema(self, schemas: list[ParameterGroupSchema]) -> None:
        """Create ParameterGroup objects matching the real node's groups."""
        for schema in schemas:
            group = ParameterGroup(name=schema.name, ui_options=schema.ui_options)
            self.add_node_element(group)

    def _build_parameters_from_schema(self, schemas: list[ParameterSchema]) -> None:
        """Create Parameter objects matching the real node's parameters."""
        for schema in schemas:
            allowed_modes: set[ParameterMode] | None = None
            if schema.allowed_modes is not None:
                allowed_modes = set()
                for mode_name in schema.allowed_modes:
                    mode = _MODE_MAP.get(mode_name)
                    if mode is not None:
                        allowed_modes.add(mode)

            param = Parameter(
                name=schema.name,
                type=schema.type,
                input_types=schema.input_types,
                output_type=schema.output_type,
                default_value=schema.default_value,
                tooltip=schema.tooltip or schema.name,
                allowed_modes=allowed_modes,
                ui_options=schema.ui_options,
                element_type=schema.element_type,
                display_name=schema.display_name,
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

        result = await process_manager.execute_node(
            library_name=self._library_name,
            node_name=self.name,
            parameter_values=dict(self.parameter_values),
            entry_control_parameter_name=entry_param_name,
        )

        # Populate output values from worker response
        for key, value in result.parameter_output_values.items():
            self.parameter_output_values[key] = value

        # Record which control output the worker selected
        self._selected_control_output_name = result.next_control_output_name
