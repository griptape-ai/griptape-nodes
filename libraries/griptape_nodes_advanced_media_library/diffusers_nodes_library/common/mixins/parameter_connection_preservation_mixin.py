"""Mixin for preserving parameter connections and properties when parameters are dynamically removed/added."""

import logging
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    IncomingConnection,
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
    OutgoingConnection,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("diffusers_nodes_library")


class ParameterConnectionPreservationMixin:
    """Mixin that provides parameter connection and property preservation when parameters are dynamically recreated.

    This mixin handles:
    - Saving/restoring connections when parameters are removed and re-added
    - Caching/restoring parameter properties (ui_options, allowed_modes)
    - Parameter reordering to maintain consistent UI layout

    Classes using this mixin should define:
    - STATIC_PARAMS: ClassVar - parameters to exclude from save/restore
    - START_PARAMS: ClassVar - parameters that should appear at the top
    - END_PARAMS: ClassVar - parameters that should appear at the bottom
    """

    STATIC_PARAMS: ClassVar[list[str]] = []
    START_PARAMS: ClassVar[list[str]] = []
    END_PARAMS: ClassVar[list[str]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.parameter_cache: dict[str, dict[str, Any]] = {}

    def save_parameter_properties(self) -> None:
        """Save ui_options and allowed_modes for all current parameters to cache."""
        for element in self.root_ui_element.children:  # type: ignore[attr-defined]
            parameter = self.get_parameter_by_name(element.name)  # type: ignore[attr-defined]
            if parameter is not None:
                self.parameter_cache[parameter.name] = {}
                if parameter.ui_options:
                    self.parameter_cache[parameter.name]["ui_options"] = parameter.ui_options.copy()
                if parameter.allowed_modes:
                    self.parameter_cache[parameter.name]["allowed_modes"] = parameter.allowed_modes.copy()

    def clear_parameter_cache(self) -> None:
        """Clear the parameter cache."""
        self.parameter_cache.clear()

    def restore_cached_parameter_properties(self, parameter: Parameter) -> None:
        """Restore cached properties for a parameter if available.

        Args:
            parameter: The parameter to restore properties for
        """
        if parameter.name not in self.parameter_cache:
            return

        cached = self.parameter_cache[parameter.name]

        # Restore ui_options
        ui_options_to_restore = {"hide"}
        if "ui_options" in cached:
            parameter.ui_options = {
                **parameter.ui_options,
                **{k: v for k, v in cached["ui_options"].items() if k in ui_options_to_restore},
            }

        # Restore allowed_modes
        if "allowed_modes" in cached:
            parameter.allowed_modes = cached["allowed_modes"]

    def _save_connections(self) -> tuple[list[IncomingConnection], list[OutgoingConnection]]:
        """Save all incoming and outgoing connections for this node, excluding static parameters.

        Returns:
            Tuple of (incoming_connections, outgoing_connections)
        """
        result = GriptapeNodes.handle_request(ListConnectionsForNodeRequest(node_name=self.name))  # type: ignore[attr-defined]
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            logger.error("Failed to list connections for node '%s'", self.name)  # type: ignore[attr-defined]
            return [], []

        # Exclude static parameters since restoring them will trigger cascade of changes
        incoming = [
            conn for conn in result.incoming_connections if conn.target_parameter_name not in self.STATIC_PARAMS
        ]
        outgoing = [
            conn for conn in result.outgoing_connections if conn.source_parameter_name not in self.STATIC_PARAMS
        ]
        return incoming, outgoing

    def _restore_connections(
        self, saved_incoming: list[IncomingConnection], saved_outgoing: list[OutgoingConnection]
    ) -> None:
        """Restore connections for parameters that still exist after parameter changes.

        Args:
            saved_incoming: List of incoming connections to restore
            saved_outgoing: List of outgoing connections to restore
        """
        for conn in saved_incoming:
            if self.does_name_exist(conn.target_parameter_name):  # type: ignore[attr-defined]
                GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=conn.source_node_name,
                        source_parameter_name=conn.source_parameter_name,
                        target_node_name=self.name,  # type: ignore[attr-defined]
                        target_parameter_name=conn.target_parameter_name,
                    )
                )

        for conn in saved_outgoing:
            if self.does_name_exist(conn.source_parameter_name):  # type: ignore[attr-defined]
                GriptapeNodes.handle_request(
                    CreateConnectionRequest(
                        source_node_name=self.name,  # type: ignore[attr-defined]
                        source_parameter_name=conn.source_parameter_name,
                        target_node_name=conn.target_node_name,
                        target_parameter_name=conn.target_parameter_name,
                    )
                )

    def reorder_parameters_by_groups(self) -> None:
        """Reorder parameters to maintain consistent layout with START/END groups."""
        excluded_params = {*self.START_PARAMS, *self.END_PARAMS}

        middle_elements = [
            element.name
            for element in self.root_ui_element._children  # type: ignore[attr-defined]
            if element.name not in excluded_params
        ]
        sorted_parameters = [*self.START_PARAMS, *middle_elements, *self.END_PARAMS]

        self.reorder_elements(sorted_parameters)  # type: ignore[attr-defined]
