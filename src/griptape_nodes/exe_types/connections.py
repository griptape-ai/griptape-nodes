from dataclasses import dataclass

from griptape.events import EventBus

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, Connection, NodeResolutionState
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    NodeUnresolvedEvent,
)


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
        if self.connection_allowed(source_node, source_parameter, source=True) and self.connection_allowed(
            target_node, target_parameter, source=False
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

    def connection_allowed(self, node: BaseNode, parameter: Parameter, *, source: bool) -> bool:
        # True if allowed, false if not
        # Here are the rules:
        # A Control Parameter can have multiple connections as an input, but only one output.
        # A Data Parameter can have one connection as input, but multiple outputs.
        if source and parameter.is_outgoing_type_allowed(target_type=ParameterTypeBuiltin.CONTROL_TYPE.value):
            connections = self.outgoing_index
            connections_from_node = connections.get(node.name, {})
            connection_id = connections_from_node.get(parameter.name, [])
            return len(connection_id) <= 0
        if not source and not parameter.is_incoming_type_allowed(incoming_type=ParameterTypeBuiltin.CONTROL_TYPE.value):
            connections = self.incoming_index
            connections_from_node = connections.get(node.name, {})
            connection_id = connections_from_node.get(parameter.name, [])
            return len(connection_id) <= 0
        return True

    def get_connected_node(self, node: BaseNode, parameter: Parameter) -> tuple[BaseNode, Parameter] | None:
        # Check to see if we should be getting the next connection or the previous connection based on the parameter.
        if parameter.is_outgoing_type_allowed(target_type=ParameterTypeBuiltin.CONTROL_TYPE.value):
            connections = self.outgoing_index
        else:
            connections = self.incoming_index
        connections_from_node = connections.get(node.name, {})

        connection_id = connections_from_node.get(parameter.name, [])
        # TODO(griptape): Add more verbose error handling here. Or connection management.
        if not len(connection_id):
            return None
        if len(connection_id) > 1:
            msg = "There should not be more than one connection here."
            raise ValueError(msg)
        connection_id = connection_id[0]
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            if parameter.is_outgoing_type_allowed(target_type=ParameterTypeBuiltin.CONTROL_TYPE.value):
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
        except Exception as e:
            print(f"Cannot remove connection that does not exist: {e}")
            return False
        for connection_id in outgoing_parameter_connections:
            if connection_id not in self.connections:
                print("Cannot remove connection does not exist")
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
            # If it is a data connection and has an OUTPUT mode
            if (
                ParameterMode.OUTPUT in parameter.allowed_modes
                and not parameter.is_outgoing_type_allowed(ParameterTypeBuiltin.CONTROL_TYPE.value)
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
                            target_node.state = NodeResolutionState.UNRESOLVED
                            # Send an event to the GUI so it knows this node is now unresolved. Execution event bc this happens bc of executions
                            EventBus.publish_event(
                                ExecutionGriptapeNodeEvent(
                                    wrapped_event=ExecutionEvent(
                                        payload=NodeUnresolvedEvent(node_name=target_node.name)
                                    )
                                )
                            )
                            self.unresolve_future_nodes(target_node)
