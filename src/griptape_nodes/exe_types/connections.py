import logging
from dataclasses import dataclass
from enum import StrEnum

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, Connection, EndLoopNode, NodeResolutionState, StartLoopNode

logger = logging.getLogger("griptape_nodes")


class Direction(StrEnum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


@dataclass
class Connections:
    # store connections as IDs
    connections: dict[int, Connection]
    # Store in node.name:parameter.name to connection id
    outgoing_index: dict[str, dict[str, list[int]]]
    incoming_index: dict[str, dict[str, list[int]]]

    # In order to get those nodes that are dirty and resolve them
    def __init__(self) -> None:
        self.connections = {}
        self.outgoing_index = {}
        self.incoming_index = {}

    def add_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> bool:
        if ParameterMode.OUTPUT not in source_parameter.get_mode():
            errormsg = f"Output Connection not allowed on Parameter '{source_parameter.name}'."
            raise ValueError(errormsg)
        if ParameterMode.INPUT not in target_parameter.get_mode():
            errormsg = f"Input Connection not allowed on Parameter '{target_parameter.name}'."
            raise ValueError(errormsg)
        # Handle multiple inputs on parameters and multiple outputs on controls
        if self.connection_allowed(source_node, source_parameter, is_source=True) and self.connection_allowed(
            target_node, target_parameter, is_source=False
        ):
            connection = Connection(source_node, source_parameter, target_node, target_parameter)
            # New index management.
            connection_id = id(connection)
            # Add connection to our dict here
            self.connections[connection_id] = connection
            # Outgoing connection
            self.outgoing_index.setdefault(source_node.name, {}).setdefault(source_parameter.name, []).append(
                connection_id
            )
            # Incoming connection
            self.incoming_index.setdefault(target_node.name, {}).setdefault(target_parameter.name, []).append(
                connection_id
            )
            return True
        msg = "Connection not allowed because of multiple connections on the same parameter input or control output parameter"
        raise ValueError(msg)

    def get_existing_connection_for_restricted_scenario(
        self, node: BaseNode, parameter: Parameter, *, is_source: bool
    ) -> Connection | None:
        """Returns connections that may exist if we are in a restricted connection scenario (see below), or None if not in such as scenario.

        Here are the rules as enforced by the engine:
          * A Control Parameter can have multiple connections to an input, but only one connection on an output.
          * A Data Parameter can have one connection on an input, but multiple outputs.

        Args:
            node: the Node we are querying
            parameter: the parameter on the Node
            is_source: are we assessing this node/parameter combo as a SOURCE for a connection or as a TARGET?

        Returns:
            None: if the source node/parameter isn't in a restricted scenario OR in a restricted scenario but no connection in place.
            Connection: if in a restricted scenario and has a Connection.
        """
        connection_list = None
        if is_source and ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
            connections = self.outgoing_index
            connections_from_node = connections.get(node.name, {})
            connection_list = connections_from_node.get(parameter.name, None)
        if not is_source and ParameterTypeBuiltin.CONTROL_TYPE.value not in parameter.input_types:
            connections = self.incoming_index
            connections_from_node = connections.get(node.name, {})
            connection_list = connections_from_node.get(parameter.name, None)

        if connection_list:
            connection_id = connection_list[0]
            connection = self.connections[connection_id]
            return connection

        # Not in a restricted scenario and/or no connection in place.
        return None

    def connection_allowed(self, node: BaseNode, parameter: Parameter, *, is_source: bool) -> bool:
        # True if allowed, false if not
        # See if we're in a scenario where we can only have one such connection which would prevent us from establishing an additional connection.
        connection = self.get_existing_connection_for_restricted_scenario(
            node=node, parameter=parameter, is_source=is_source
        )
        return connection is None

    def _get_connected_node_for_end_loop_control(
        self, end_loop_node: EndLoopNode, control_parameter: Parameter
    ) -> tuple[BaseNode, Parameter] | None:
        """For an EndLoopNode and its control parameter, finds the connected node and parameter.

        It checks both outgoing connections (where EndLoopNode's parameter is a source)
        and incoming connections (where EndLoopNode's parameter is a target).
        """
        # Check if the EndLoopNode's control parameter is a source for an outgoing connection
        if ParameterMode.OUTPUT in control_parameter.allowed_modes:
            outgoing_connections_for_node = self.outgoing_index.get(end_loop_node.name, {})
            connection_ids_as_source = outgoing_connections_for_node.get(control_parameter.name, [])
            if connection_ids_as_source:
                connection_id = connection_ids_as_source[0]
                connection = self.connections.get(connection_id)
                if connection:
                    return connection.target_node, connection.target_parameter
        elif ParameterMode.INPUT in control_parameter.allowed_modes:
            # Check if the EndLoopNode's control parameter is a target for an incoming connection
            incoming_connections_for_node = self.incoming_index.get(end_loop_node.name, {})
            connection_ids_as_target = incoming_connections_for_node.get(control_parameter.name, [])
            if connection_ids_as_target:
                for connection_id in connection_ids_as_target:
                    connection = self.connections.get(connection_id)
                    if connection and isinstance(connection.source_node, StartLoopNode):
                        return connection.source_node, connection.source_parameter
        return None  # No connection found for this control parameter

    def get_connected_node(
        self, node: BaseNode, parameter: Parameter, direction: Direction | None = None
    ) -> tuple[BaseNode, Parameter] | None:
        # Check to see if we should be getting the next connection or the previous connection based on the parameter.
        # Override this method for EndLoopNodes - these might have to go backwards or forwards.
        if direction is not None:
            # We've added direction as an override, since we sometimes need to get connections in a certain direction regardless of parameter types.
            if direction == Direction.UPSTREAM:
                connections = self.incoming_index
            elif direction == Direction.DOWNSTREAM:
                connections = self.outgoing_index
        else:
            if isinstance(node, EndLoopNode) and ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
                return self._get_connected_node_for_end_loop_control(node, parameter)
            if ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
                connections = self.outgoing_index
                # We still default to downstream (forwards) connections for control parameters
                direction = Direction.DOWNSTREAM
            else:
                connections = self.incoming_index
                # And upstream (backwards) connections for data parameters.
                direction = Direction.UPSTREAM
        connections_from_node = connections.get(node.name, {})

        connection_id = connections_from_node.get(parameter.name, [])
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/859
        if not len(connection_id):
            return None
        # Right now, our special case is that it is ok to have multiple inputs to a CONTROL_TYPE parameter, so if we're going upstream, it's ok. And it's ok to have multiple downstream outputs from a data type parameter.
        if (
            len(connection_id) > 1
            and not (
                direction == Direction.UPSTREAM and parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value
            )
            and not (
                direction == Direction.DOWNSTREAM and parameter.output_type != ParameterTypeBuiltin.CONTROL_TYPE.value
            )
        ):
            msg = f"There should not be more than one {direction} connection here to/from {node.name}.{parameter.name}"
            raise ValueError(msg)
        connection_id = connection_id[0]
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            if direction == Direction.DOWNSTREAM:
                # Return the target (next place to go)
                return connection.target_node, connection.target_parameter
            # Return the source (next place to chain back to)
            return connection.source_node, connection.source_parameter
        return None

    def remove_connection(
        self, source_node: str, source_parameter: str, target_node: str, target_parameter: str
    ) -> bool:
        # Remove from outgoing
        try:
            # use copy to prevent modifying the list while it's iterating
            outgoing_parameter_connections = self.outgoing_index[source_node][source_parameter].copy()
        except Exception:
            logger.exception("Cannot remove connection that does not exist")
            return False
        for connection_id in outgoing_parameter_connections:
            if connection_id not in self.connections:
                logger.error("Cannot remove connection does not exist")
                return False
            connection = self.connections[connection_id]
            test_target_node = connection.target_node.name
            test_target_parameter = connection.target_parameter.name
            if test_target_node == target_node and test_target_parameter == target_parameter:
                self._remove_connection(
                    connection_id, source_node, source_parameter, test_target_node, test_target_parameter
                )
                return True
        return False

    def _remove_connection(
        self, connection_id: int, source_node: str, source_param: str, target_node: str, target_param: str
    ) -> None:
        # Now delete from EVERYWHERE!
        # delete the parameter from the node name dictionary
        self.outgoing_index[source_node][source_param].remove(connection_id)
        if not self.outgoing_index[source_node][source_param]:
            del self.outgoing_index[source_node][source_param]
            # if the node name dictionary is empty, delete it!
            if not self.outgoing_index[source_node]:
                del self.outgoing_index[source_node]
        # delete the parameter from the node name dictionary
        self.incoming_index[target_node][target_param].remove(connection_id)
        if not self.incoming_index[target_node][target_param]:
            del self.incoming_index[target_node][target_param]
            # if the node name dictionary is empty, delete it!
            if not self.incoming_index[target_node]:
                del self.incoming_index[target_node]
        # delete from the connections dictionary
        del self.connections[connection_id]

    # Used to check data connections for all future nodes to be BAD!
    def unresolve_future_nodes(self, node: BaseNode) -> None:
        # Recursive loop
        # For each parameter
        if node.name not in self.outgoing_index:
            # There are no outgoing connections from this node.
            return
        for parameter in node.parameters:
            # If it is a data connection and has an OUTPUT type
            if (
                ParameterMode.OUTPUT in parameter.allowed_modes
                and ParameterTypeBuiltin.CONTROL_TYPE.value != parameter.output_type
                # check if a outgoing connection exists from this parameter
                and parameter.name in self.outgoing_index[node.name]
            ):
                # A connection or connections exist
                connections = self.outgoing_index[node.name][parameter.name]
                # for each connection, check the next node and do all the same.
                for connection_id in connections:
                    if connection_id in self.connections:
                        connection = self.connections[connection_id]
                        target_node = connection.target_node
                        # if that node is already unresolved, we're all good.
                        if target_node.state == NodeResolutionState.RESOLVED:
                            # Sends an event to the GUI so it knows this node has changed resolution state.
                            target_node.make_node_unresolved(
                                current_states_to_trigger_change_event=set(
                                    {NodeResolutionState.RESOLVED, NodeResolutionState.RESOLVING}
                                )
                            )
                            self.unresolve_future_nodes(target_node)

    def _update_incoming_connections_for_parameter(
        self, node: BaseNode, param_name: str, new_param: Parameter, connections_to_delete: list[int]
    ) -> None:
        """Update incoming connections for a replaced parameter."""
        if node.name not in self.incoming_index or param_name not in self.incoming_index[node.name]:
            return

        for conn_id in list(self.incoming_index[node.name][param_name]):
            connection = self.connections[conn_id]
            source_output_type = connection.source_parameter.output_type

            # Check type compatibility
            if source_output_type not in new_param.input_types:
                logger.debug(
                    "Removing incompatible incoming connection: %s.%s (%s) -> %s.%s (accepts %s)",
                    connection.source_node.name,
                    connection.source_parameter.name,
                    source_output_type,
                    node.name,
                    param_name,
                    new_param.input_types,
                )
                connections_to_delete.append(conn_id)
                continue

            # Type compatible - update the connection's target_parameter reference
            connection.target_parameter = new_param
            logger.debug(
                "Updated incoming connection parameter reference: %s.%s -> %s.%s",
                connection.source_node.name,
                connection.source_parameter.name,
                node.name,
                param_name,
            )

    def _update_outgoing_connections_for_parameter(
        self, node: BaseNode, param_name: str, new_param: Parameter, connections_to_delete: list[int]
    ) -> None:
        """Update outgoing connections for a replaced parameter."""
        if node.name not in self.outgoing_index or param_name not in self.outgoing_index[node.name]:
            return

        for conn_id in list(self.outgoing_index[node.name][param_name]):
            if conn_id not in self.connections:
                continue

            connection = self.connections[conn_id]
            target_input_types = connection.target_parameter.input_types

            # Check type compatibility
            if new_param.output_type not in target_input_types:
                logger.debug(
                    "Removing incompatible outgoing connection: %s.%s (%s) -> %s.%s (accepts %s)",
                    node.name,
                    param_name,
                    new_param.output_type,
                    connection.target_node.name,
                    connection.target_parameter.name,
                    target_input_types,
                )
                connections_to_delete.append(conn_id)
                continue

            # Type compatible - update the connection's source_parameter reference
            connection.source_parameter = new_param
            logger.debug(
                "Updated outgoing connection parameter reference: %s.%s -> %s.%s",
                node.name,
                param_name,
                connection.target_node.name,
                connection.target_parameter.name,
            )

    def update_parameter_references_after_replacement(self, node: BaseNode, param_names: set[str]) -> None:
        """Update Connection objects to reference new Parameter instances after parameter replacement.

        When parameters are removed and re-added with the same name, Connection objects
        still reference the old Parameter instances. This method updates those references
        to point to the new Parameter instances, removing connections that are no longer
        type-compatible.

        Args:
            node: The node whose parameters were replaced
            param_names: Names of parameters that were removed and re-added
        """
        connections_to_delete = []

        for param_name in param_names:
            # Get the new parameter instance
            new_param = node.get_parameter_by_name(param_name)
            if new_param is None:
                logger.warning("Parameter '%s' not found on node '%s' after replacement", param_name, node.name)
                # Delete all connections for this parameter
                if node.name in self.incoming_index and param_name in self.incoming_index[node.name]:
                    connections_to_delete.extend(self.incoming_index[node.name][param_name])
                if node.name in self.outgoing_index and param_name in self.outgoing_index[node.name]:
                    connections_to_delete.extend(self.outgoing_index[node.name][param_name])
                continue

            # Update incoming and outgoing connections
            self._update_incoming_connections_for_parameter(node, param_name, new_param, connections_to_delete)
            self._update_outgoing_connections_for_parameter(node, param_name, new_param, connections_to_delete)

        # Delete incompatible connections
        for conn_id in connections_to_delete:
            if conn_id in self.connections:
                conn = self.connections[conn_id]
                self._remove_connection(
                    conn_id,
                    conn.source_node.name,
                    conn.source_parameter.name,
                    conn.target_node.name,
                    conn.target_parameter.name,
                )
