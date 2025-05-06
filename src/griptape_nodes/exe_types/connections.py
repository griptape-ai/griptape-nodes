import logging
from dataclasses import dataclass

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, Connection, NodeResolutionState

logger = logging.getLogger("griptape_nodes")


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

    def get_connected_node(self, node: BaseNode, parameter: Parameter) -> tuple[BaseNode, Parameter] | None:
        # Check to see if we should be getting the next connection or the previous connection based on the parameter.
        if ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
            connections = self.outgoing_index
        else:
            connections = self.incoming_index
        connections_from_node = connections.get(node.name, {})

        connection_id = connections_from_node.get(parameter.name, [])
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/859
        if not len(connection_id):
            return None
        if len(connection_id) > 1:
            msg = "There should not be more than one connection here."
            raise ValueError(msg)
        connection_id = connection_id[0]
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            if ParameterTypeBuiltin.CONTROL_TYPE.value == parameter.output_type:
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
