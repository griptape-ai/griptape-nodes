from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.core_types import (
    ControlParameter,
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
    Trait,
)
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_types import (
    LOCAL_EXECUTION,
    get_library_names_with_publish_handlers,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    DeleteConnectionResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AddParameterToNodeResultSuccess,
    RemoveParameterFromNodeRequest,
)
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.exe_types.node_types import BaseNode, Connection

logger = logging.getLogger("griptape_nodes")


class SubflowNodeGroup(BaseNodeGroup):
    """Proxy node that represents a group of nodes during DAG execution.

    This node acts as a single execution unit for a group of nodes that should
    be executed in parallel. When the DAG executor encounters this proxy node,
    it passes the entire NodeGroup to the NodeExecutor which handles parallel
    execution of all grouped nodes.

    The proxy node has parameters that mirror the external connections to/from
    the group, allowing it to seamlessly integrate into the DAG structure.
    """

    _proxy_param_to_connections: dict[str, int]

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)
        self.execution_environment = Parameter(
            name="execution_environment",
            tooltip="Environment that the group should execute in",
            type=ParameterTypeBuiltin.STR,
            allowed_modes={ParameterMode.PROPERTY},
            default_value=LOCAL_EXECUTION,
            traits={Options(choices=get_library_names_with_publish_handlers())},
        )
        self.add_parameter(self.execution_environment)
        # Track mapping from proxy parameter name to (original_node, original_param_name)
        self._proxy_param_to_connections = {}
        if "execution_environment" not in self.metadata:
            self.metadata["execution_environment"] = {}
        self.metadata["execution_environment"]["Griptape Nodes Library"] = {
            "start_flow_node": "StartFlow",
            "parameter_names": {},
        }

        # Don't create subflow in __init__ - it will be created on-demand when nodes are added
        # or restored during deserialization

        # Add parameters from registered StartFlow nodes for each publishing library
        self._add_start_flow_parameters()

    def _create_subflow(self) -> None:
        """Create a dedicated subflow for this NodeGroup's nodes.

        Note: This is called during __init__, so the node may not yet be added to a flow.
        The subflow will be created without a parent initially, and can be reparented later.
        """
        from griptape_nodes.retained_mode.events.flow_events import (
            CreateFlowRequest,
            CreateFlowResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        subflow_name = f"{self.name}_subflow"
        self.metadata["subflow_name"] = subflow_name

        # Get current flow to set as parent so subflow will be serialized with parent
        current_flow = GriptapeNodes.ContextManager().get_current_flow()
        parent_flow_name = current_flow.name if current_flow else None

        request = CreateFlowRequest(flow_name=subflow_name, parent_flow_name=parent_flow_name, set_as_new_context=False)
        result = GriptapeNodes.handle_request(request)

        if not isinstance(result, CreateFlowResultSuccess):
            logger.warning("%s failed to create subflow '%s': %s", self.name, subflow_name, result.result_details)

    def _add_start_flow_parameters(self) -> None:
        """Add parameters from all registered StartFlow nodes to this SubflowNodeGroup.

        For each library that has registered a PublishWorkflowRequest handler with
        a StartFlow node, this method:
        1. Creates a temporary instance of that StartFlow node
        2. Extracts all its parameters
        3. Adds them to this SubflowNodeGroup with a prefix based on the class name
        4. Stores metadata mapping execution environments to their parameters
        """
        from griptape_nodes.retained_mode.events.workflow_events import PublishWorkflowRequest
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Initialize metadata structure for execution environment mappings
        if self.metadata is None:
            self.metadata = {}
        if "execution_environment" not in self.metadata:
            self.metadata["execution_environment"] = {}

        # Get all libraries that have registered PublishWorkflowRequest handlers
        library_manager = GriptapeNodes.LibraryManager()
        event_handlers = library_manager.get_registered_event_handlers(PublishWorkflowRequest)

        # Process each registered library
        for library_name, handler in event_handlers.items():
            self._process_library_start_flow_parameters(library_name, handler)

    def _process_library_start_flow_parameters(self, library_name: str, handler: Any) -> None:
        """Process and add StartFlow parameters from a single library.

        Args:
            library_name: Name of the library
            handler: The registered event handler containing event data
        """
        import logging

        from griptape_nodes.node_library.library_registry import LibraryRegistry
        from griptape_nodes.retained_mode.events.workflow_events import PublishWorkflowRegisteredEventData

        logger = logging.getLogger(__name__)

        registered_event_data = handler.event_data

        if registered_event_data is None:
            return
        if not isinstance(registered_event_data, PublishWorkflowRegisteredEventData):
            return

        # Get the StartFlow node information
        start_flow_node_type = registered_event_data.start_flow_node_type
        start_flow_library_name = registered_event_data.start_flow_node_library_name

        try:
            # Get the library that contains the StartFlow node
            library = LibraryRegistry.get_library(name=start_flow_library_name)
        except KeyError:
            logger.debug(
                "Library '%s' not found when adding StartFlow parameters for '%s'",
                start_flow_library_name,
                library_name,
            )
            return

        try:
            # Create a temporary instance of the StartFlow node to inspect its parameters
            temp_start_flow_node = library.create_node(
                node_type=start_flow_node_type,
                name=f"temp_{start_flow_node_type}",
            )
        except Exception as e:
            logger.debug(
                "Failed to create temporary StartFlow node '%s' from library '%s': %s",
                start_flow_node_type,
                start_flow_library_name,
                e,
            )
            return

        # Get the class name for prefixing (convert to lowercase for parameter naming)
        class_name_prefix = start_flow_node_type.lower()

        # Store metadata for this execution environment
        parameter_names = []

        # Add each parameter from the StartFlow node to this SubflowNodeGroup
        for param in temp_start_flow_node.parameters:
            if isinstance(param, ControlParameter):
                continue

            # Create prefixed parameter name
            prefixed_param_name = f"{class_name_prefix}_{param.name}"
            parameter_names.append(prefixed_param_name)

            # Clone and add the parameter
            self._clone_and_add_parameter(param, prefixed_param_name)

        # Store the mapping in metadata
        self.metadata["execution_environment"][library_name] = {
            "start_flow_node": start_flow_node_type,
            "parameter_names": parameter_names,
        }

    def _clone_and_add_parameter(self, param: Parameter, new_name: str) -> None:
        """Clone a parameter with a new name and add it to this node.

        Args:
            param: The parameter to clone
            new_name: The new name for the cloned parameter
        """
        # Extract traits from parameter children (traits are stored as children of type Trait)
        traits_set: set[type[Trait] | Trait] | None = {child for child in param.children if isinstance(child, Trait)}
        if not traits_set:
            traits_set = None

        # Clone the parameter with the new name
        cloned_param = Parameter(
            name=new_name,
            tooltip=param.tooltip,
            type=param.type,
            allowed_modes=param.allowed_modes,
            default_value=param.default_value,
            traits=traits_set,
            parent_container_name=param.parent_container_name,
            parent_element_name=param.parent_element_name,
        )

        # Add the parameter to this node
        self.add_parameter(cloned_param)

    def _create_proxy_parameter_for_connection(self, original_param: Parameter, *, is_incoming: bool) -> Parameter:
        """Create a proxy parameter on this SubflowNodeGroup for an external connection.

        Args:
            original_param: The parameter from the grouped node
            grouped_node: The node within the group that has the original parameter
            conn_id: The connection ID for uniqueness
            is_incoming: True if this is an incoming connection to the group

        Returns:
            The newly created proxy parameter
        """
        # Clone the parameter with the new name
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        input_types = None
        output_type = None
        if is_incoming:
            input_types = original_param.input_types
        else:
            output_type = original_param.output_type

        request = AddParameterToNodeRequest(
            node_name=self.name,
            parameter_name=original_param.name,
            input_types=input_types,
            output_type=output_type,
            tooltip="",
            mode_allowed_input=True,
            mode_allowed_output=True,
        )
        # Add with a request, because this will handle naming for us.
        result = GriptapeNodes.handle_request(request)
        if not isinstance(result, AddParameterToNodeResultSuccess):
            msg = "Failed to add parameter to node."
            raise TypeError(msg)
        # Retrieve and return the newly created parameter
        proxy_param = self.get_parameter_by_name(result.parameter_name)
        if proxy_param is None:
            msg = f"{self.name} failed to create proxy parameter '{result.parameter_name}'"
            raise RuntimeError(msg)
        if is_incoming:
            if "left_parameters" in self.metadata:
                self.metadata["left_parameters"].append(proxy_param.name)
            else:
                self.metadata["left_parameters"] = [proxy_param.name]
        elif "right_parameters" in self.metadata:
            self.metadata["right_parameters"].append(proxy_param.name)
        else:
            self.metadata["right_parameters"] = [proxy_param.name]

        return proxy_param

    def get_all_nodes(self) -> dict[str, BaseNode]:
        all_nodes = {}
        for node_name, node in self.nodes.items():
            all_nodes[node_name] = node
            if isinstance(node, SubflowNodeGroup):
                all_nodes.update(node.nodes)
        return all_nodes

    def map_external_connection(self, conn: Connection, *, is_incoming: bool) -> bool:
        """Track a connection to/from a node in the group and rewire it through a proxy parameter.

        Args:
            conn: The external connection to track
            conn_id: ID of the connection
            is_incoming: True if connection is coming INTO the group
        """
        if is_incoming:
            grouped_parameter = conn.target_parameter
            # Store the existing connection so it can be recreated if needed.
        else:
            grouped_parameter = conn.source_parameter
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        request = DeleteConnectionRequest(
            conn.source_parameter.name,
            conn.target_parameter.name,
            conn.source_node.name,
            conn.target_node.name,
        )
        result = GriptapeNodes.handle_request(request)
        if not isinstance(result, DeleteConnectionResultSuccess):
            return False
        proxy_parameter = self._create_proxy_parameter_for_connection(grouped_parameter, is_incoming=is_incoming)
        # Create connections for proxy parameter
        self.create_connections_for_proxy(proxy_parameter, conn, is_incoming=is_incoming)
        return True

    def create_connections_for_proxy(
        self, proxy_parameter: Parameter, old_connection: Connection, *, is_incoming: bool
    ) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        create_first_connection = CreateConnectionRequest(
            source_parameter_name=old_connection.source_parameter.name,
            target_parameter_name=proxy_parameter.name,
            source_node_name=old_connection.source_node.name,
            target_node_name=self.name,
            is_node_group_internal=not is_incoming,
        )
        create_second_connection = CreateConnectionRequest(
            source_parameter_name=proxy_parameter.name,
            target_parameter_name=old_connection.target_parameter.name,
            source_node_name=self.name,
            target_node_name=old_connection.target_node.name,
            is_node_group_internal=is_incoming,
        )
        # Store the mapping from proxy parameter to original node/parameter
        # only increment by 1, even though we're making two connections.
        if proxy_parameter.name not in self._proxy_param_to_connections:
            self._proxy_param_to_connections[proxy_parameter.name] = 2
        else:
            self._proxy_param_to_connections[proxy_parameter.name] += 2
        GriptapeNodes.handle_request(create_first_connection)
        GriptapeNodes.handle_request(create_second_connection)

    def unmap_node_connections(self, node: BaseNode, connections: Connections) -> None:  # noqa: C901
        """Remove tracking of an external connection, restore original connection, and clean up proxy parameter.

        Args:
            node: The node to unmap
            connections: The connections object
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # For the node being removed - We need to figure out all of it's connections TO the node group. These connections need to be remapped.
        # If we delete connections from a proxy parameter, and it has no more connections, then the proxy parameter should be deleted unless it's user defined.
        # It will 1. not be in the proxy map. and 2. it will have a value of > 0
        # Get all outgoing connections
        outgoing_connections = connections.get_outgoing_connections_to_node(node, to_node=self)
        # Delete outgoing connections
        for parameter_name, outgoing_connection_list in outgoing_connections.items():
            for outgoing_connection in outgoing_connection_list:
                proxy_parameter = outgoing_connection.target_parameter
                # get old connections first, since this will delete the proxy
                remap_connections = connections.get_outgoing_connections_from_parameter(self, proxy_parameter)
                # Delete the internal connection
                delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                    DeleteConnectionRequest(
                        source_parameter_name=parameter_name,
                        target_parameter_name=proxy_parameter.name,
                        source_node_name=node.name,
                        target_node_name=self.name,
                    )
                )
                if delete_result.failed():
                    msg = f"{self.name}: Failed to delete internal outgoing connection from {node.name}.{parameter_name} to proxy {proxy_parameter.name}: {delete_result.result_details}"
                    raise RuntimeError(msg)

                # Now create the new connection! We need to get the connections from the proxy parameter
                for connection in remap_connections:
                    create_result = GriptapeNodes.FlowManager().on_create_connection_request(
                        CreateConnectionRequest(
                            source_parameter_name=parameter_name,
                            target_parameter_name=connection.target_parameter.name,
                            source_node_name=node.name,
                            target_node_name=connection.target_node.name,
                        )
                    )
                    if create_result.failed():
                        msg = f"{self.name}: Failed to create direct outgoing connection from {node.name}.{parameter_name} to {connection.target_node.name}.{connection.target_parameter.name}: {create_result.result_details}"
                        raise RuntimeError(msg)

        # Get all incoming connections
        incoming_connections = connections.get_incoming_connections_from_node(node, from_node=self)
        # Delete incoming connections
        for parameter_name, incoming_connection_list in incoming_connections.items():
            for incoming_connection in incoming_connection_list:
                proxy_parameter = incoming_connection.source_parameter
                # Get the incoming connections to the proxy parameter
                remap_connections = connections.get_incoming_connections_to_parameter(self, proxy_parameter)
                # Delete the internal connection
                delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                    DeleteConnectionRequest(
                        source_parameter_name=proxy_parameter.name,
                        target_parameter_name=parameter_name,
                        source_node_name=self.name,
                        target_node_name=node.name,
                    )
                )
                if delete_result.failed():
                    msg = f"{self.name}: Failed to delete internal incoming connection from proxy {proxy_parameter.name} to {node.name}.{parameter_name}: {delete_result.result_details}"
                    raise RuntimeError(msg)

                # Now create the new connection! We need to get the connections to the proxy parameter
                for connection in remap_connections:
                    create_result = GriptapeNodes.FlowManager().on_create_connection_request(
                        CreateConnectionRequest(
                            source_parameter_name=connection.source_parameter.name,
                            target_parameter_name=parameter_name,
                            source_node_name=connection.source_node.name,
                            target_node_name=node.name,
                        )
                    )
                    if create_result.failed():
                        msg = f"{self.name}: Failed to create direct incoming connection from {connection.source_node.name}.{connection.source_parameter.name} to {node.name}.{parameter_name}: {create_result.result_details}"
                        raise RuntimeError(msg)

    def _remove_nodes_from_existing_parents(self, nodes: list[BaseNode]) -> None:
        """Remove nodes from their existing parent groups."""
        child_nodes = {}
        for node in nodes:
            if node.parent_group is not None:
                existing_parent_group = node.parent_group
                if isinstance(existing_parent_group, SubflowNodeGroup):
                    child_nodes.setdefault(existing_parent_group, []).append(node)
        for parent_group, node_list in child_nodes.items():
            parent_group.remove_nodes_from_group(node_list)

    def _add_nodes_to_group_dict(self, nodes: list[BaseNode]) -> None:
        """Add nodes to the group's node dictionary."""
        for node in nodes:
            node.parent_group = self
            self.nodes[node.name] = node

    def _cleanup_proxy_parameter(self, proxy_parameter: Parameter, metadata_key: str) -> None:
        """Clean up proxy parameter if it has no more connections.

        Args:
            proxy_parameter: The proxy parameter to potentially clean up
            metadata_key: The metadata key ('left_parameters' or 'right_parameters')
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        if proxy_parameter.name not in self._proxy_param_to_connections:
            return

        self._proxy_param_to_connections[proxy_parameter.name] -= 1
        if self._proxy_param_to_connections[proxy_parameter.name] == 0:
            GriptapeNodes.NodeManager().on_remove_parameter_from_node_request(
                request=RemoveParameterFromNodeRequest(node_name=self.name, parameter_name=proxy_parameter.name)
            )
            del self._proxy_param_to_connections[proxy_parameter.name]
            if metadata_key in self.metadata and proxy_parameter.name in self.metadata[metadata_key]:
                self.metadata[metadata_key].remove(proxy_parameter.name)

    def _remap_outgoing_connections(self, node: BaseNode, connections: Connections) -> None:
        """Remap outgoing connections that go through proxy parameters.

        Args:
            node: The node being added to the group
            connections: Connections object from FlowManager
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        outgoing_connections = connections.get_outgoing_connections_to_node(node, to_node=self)
        for parameter_name, outgoing_connection_list in outgoing_connections.items():
            for outgoing_connection in outgoing_connection_list:
                proxy_parameter = outgoing_connection.target_parameter
                remap_connections = connections.get_outgoing_connections_from_parameter(self, proxy_parameter)
                delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                    DeleteConnectionRequest(
                        source_parameter_name=parameter_name,
                        target_parameter_name=proxy_parameter.name,
                        source_node_name=node.name,
                        target_node_name=self.name,
                    )
                )
                if delete_result.failed():
                    msg = f"{self.name}: Failed to delete internal outgoing connection from {node.name}.{parameter_name} to proxy {proxy_parameter.name}: {delete_result.result_details}"
                    raise RuntimeError(msg)

                for connection in remap_connections:
                    delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                        DeleteConnectionRequest(
                            source_parameter_name=connection.source_parameter.name,
                            target_parameter_name=connection.target_parameter.name,
                            source_node_name=connection.source_node.name,
                            target_node_name=connection.target_node.name,
                        )
                    )
                    if delete_result.failed():
                        msg = f"{self.name}: Failed to delete external connection from proxy {proxy_parameter.name} to {connection.target_node.name}.{connection.target_parameter.name}: {delete_result.result_details}"
                        raise RuntimeError(msg)

                    create_result = GriptapeNodes.FlowManager().on_create_connection_request(
                        CreateConnectionRequest(
                            source_parameter_name=parameter_name,
                            target_parameter_name=connection.target_parameter.name,
                            source_node_name=node.name,
                            target_node_name=connection.target_node.name,
                        )
                    )
                    if create_result.failed():
                        msg = f"{self.name}: Failed to create direct outgoing connection from {node.name}.{parameter_name} to {connection.target_node.name}.{connection.target_parameter.name}: {create_result.result_details}"
                        raise RuntimeError(msg)

                self._cleanup_proxy_parameter(proxy_parameter, "right_parameters")

    def _remap_incoming_connections(self, node: BaseNode, connections: Connections) -> None:
        """Remap incoming connections that go through proxy parameters.

        Args:
            node: The node being added to the group
            connections: Connections object from FlowManager
        """
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        incoming_connections = connections.get_incoming_connections_from_node(node, from_node=self)
        for parameter_name, incoming_connection_list in incoming_connections.items():
            for incoming_connection in incoming_connection_list:
                proxy_parameter = incoming_connection.source_parameter
                remap_connections = connections.get_incoming_connections_to_parameter(self, proxy_parameter)
                delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                    DeleteConnectionRequest(
                        source_parameter_name=proxy_parameter.name,
                        target_parameter_name=parameter_name,
                        source_node_name=self.name,
                        target_node_name=node.name,
                    )
                )
                if delete_result.failed():
                    msg = f"{self.name}: Failed to delete internal incoming connection from proxy {proxy_parameter.name} to {node.name}.{parameter_name}: {delete_result.result_details}"
                    raise RuntimeError(msg)

                for connection in remap_connections:
                    delete_result = GriptapeNodes.FlowManager().on_delete_connection_request(
                        DeleteConnectionRequest(
                            source_parameter_name=connection.source_parameter.name,
                            target_parameter_name=proxy_parameter.name,
                            source_node_name=connection.source_node.name,
                            target_node_name=self.name,
                        )
                    )
                    if delete_result.failed():
                        msg = f"{self.name}: Failed to delete external connection from {connection.source_node.name}.{connection.source_parameter.name} to proxy {proxy_parameter.name}: {delete_result.result_details}"
                        raise RuntimeError(msg)

                    create_result = GriptapeNodes.FlowManager().on_create_connection_request(
                        CreateConnectionRequest(
                            source_parameter_name=connection.source_parameter.name,
                            target_parameter_name=parameter_name,
                            source_node_name=connection.source_node.name,
                            target_node_name=node.name,
                        )
                    )
                    if create_result.failed():
                        msg = f"{self.name}: Failed to create direct incoming connection from {connection.source_node.name}.{connection.source_parameter.name} to {node.name}.{parameter_name}: {create_result.result_details}"
                        raise RuntimeError(msg)

                self._cleanup_proxy_parameter(proxy_parameter, "left_parameters")

    def remap_to_internal(self, nodes: list[BaseNode], connections: Connections) -> None:
        """Remap connections that are now internal after adding nodes to the group.

        When nodes are added to a group, some connections that previously went through
        proxy parameters may now be internal. This method identifies such connections
        and restores direct connections between the nodes.

        Args:
            nodes: List of nodes being added to the group
            connections: Connections object from FlowManager
        """
        for node in nodes:
            self._remap_outgoing_connections(node, connections)
            self._remap_incoming_connections(node, connections)

    def after_outgoing_connection_removed(
        self, source_parameter: Parameter, target_node: BaseNode, target_parameter: Parameter
    ) -> None:
        # Instead of right_parameters, we should check the internal connections
        if target_node.parent_group == self:
            metadata_key = "left_parameters"
        else:
            metadata_key = "right_parameters"
        self._cleanup_proxy_parameter(source_parameter, metadata_key)
        return super().after_outgoing_connection_removed(source_parameter, target_node, target_parameter)

    def after_incoming_connection_removed(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # Instead of left_parameters, we should check the internal connections.
        if source_node.parent_group == self:
            metadata_key = "right_parameters"
        else:
            metadata_key = "left_parameters"
        self._cleanup_proxy_parameter(target_parameter, metadata_key)
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def add_nodes_to_group(self, nodes: list[BaseNode]) -> None:
        """Add nodes to the group and track their connections.

        Args:
            nodes: List of nodes to add to the group
        """
        from griptape_nodes.retained_mode.events.node_events import (
            MoveNodeToNewFlowRequest,
            MoveNodeToNewFlowResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        self._remove_nodes_from_existing_parents(nodes)
        self._add_nodes_to_group_dict(nodes)

        # Create subflow on-demand if it doesn't exist
        subflow_name = self.metadata.get("subflow_name")
        if subflow_name is None:
            self._create_subflow()
            subflow_name = self.metadata.get("subflow_name")

        if subflow_name is not None:
            for node in nodes:
                move_request = MoveNodeToNewFlowRequest(node_name=node.name, target_flow_name=subflow_name)
                move_result = GriptapeNodes.handle_request(move_request)
                if not isinstance(move_result, MoveNodeToNewFlowResultSuccess):
                    msg = "%s failed to move node '%s' to subflow: %s", self.name, node.name, move_result.result_details
                    logger.error(msg)
                    raise RuntimeError(msg)  # noqa: TRY004

        connections = GriptapeNodes.FlowManager().get_connections()
        node_names_in_group = set(self.nodes.keys())
        self.metadata["node_names_in_group"] = list(node_names_in_group)
        self.remap_to_internal(nodes, connections)
        self._map_external_connections_for_nodes(nodes, connections, node_names_in_group)

    def _map_external_connections_for_nodes(
        self, nodes: list[BaseNode], connections: Connections, node_names_in_group: set[str]
    ) -> None:
        """Map external connections for nodes being added to the group.

        Args:
            nodes: List of nodes being added
            connections: Connections object from FlowManager
            node_names_in_group: Set of all node names currently in the group
        """
        for node in nodes:
            outgoing_connections = connections.get_all_outgoing_connections(node)
            for conn in outgoing_connections:
                if conn.target_node.name not in node_names_in_group:
                    self.map_external_connection(
                        conn=conn,
                        is_incoming=False,
                    )

            incoming_connections = connections.get_all_incoming_connections(node)
            for conn in incoming_connections:
                if conn.source_node.name not in node_names_in_group:
                    self.map_external_connection(
                        conn=conn,
                        is_incoming=True,
                    )

    def _validate_nodes_in_group(self, nodes: list[BaseNode]) -> None:
        """Validate that all nodes are in the group."""
        for node in nodes:
            if node.name not in self.nodes:
                msg = f"Node {node.name} is not in node group {self.name}"
                raise ValueError(msg)

    def delete_nodes_from_group(self, nodes: list[BaseNode]) -> None:
        """Delete nodes from the group and untrack their connections.

        Args:
            nodes: List of nodes to delete from the group
        """
        for node in nodes:
            self.nodes.pop(node.name)
        self.metadata["node_names_in_group"] = list(self.nodes.keys())

    def remove_nodes_from_group(self, nodes: list[BaseNode]) -> None:
        """Remove nodes from the group and untrack their connections.

        Args:
            nodes: List of nodes to remove from the group
        """
        from griptape_nodes.retained_mode.events.node_events import (
            MoveNodeToNewFlowRequest,
            MoveNodeToNewFlowResultSuccess,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        self._validate_nodes_in_group(nodes)

        parent_flow_name = None
        try:
            parent_flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(self.name)
        except KeyError:
            logger.warning("%s has no parent flow, cannot move nodes back", self.name)

        connections = GriptapeNodes.FlowManager().get_connections()
        for node in nodes:
            node.parent_group = None
            self.nodes.pop(node.name)

            if parent_flow_name is not None:
                move_request = MoveNodeToNewFlowRequest(node_name=node.name, target_flow_name=parent_flow_name)
                move_result = GriptapeNodes.handle_request(move_request)
                if not isinstance(move_result, MoveNodeToNewFlowResultSuccess):
                    msg = (
                        "%s failed to move node '%s' back to parent flow: %s",
                        self.name,
                        node.name,
                        move_result.result_details,
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)

        for node in nodes:
            self.unmap_node_connections(node, connections)

        self.metadata["node_names_in_group"] = list(self.nodes.keys())

        remaining_nodes = list(self.nodes.values())
        if remaining_nodes:
            node_names_in_group = set(self.nodes.keys())
            self._map_external_connections_for_nodes(remaining_nodes, connections, node_names_in_group)

    async def aprocess(self) -> None:
        """Execute all nodes in the group in parallel.

        This method is called by the DAG executor. It executes all nodes in the
        group concurrently using asyncio.gather and handles propagating input
        values from the proxy to the grouped nodes.
        """
        from griptape_nodes.retained_mode.events.execution_events import StartLocalSubflowRequest
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        subflow = self.metadata.get("subflow_name")
        if subflow is not None and isinstance(subflow, str):
            await GriptapeNodes.FlowManager().on_start_local_subflow_request(
                StartLocalSubflowRequest(flow_name=subflow)
            )

        # After subflow execution, collect output values from internal nodes
        # and set them on the NodeGroup's output (right) proxy parameters
        connections = GriptapeNodes.FlowManager().get_connections()

        # Get all right parameters (output parameters)
        right_params = self.metadata.get("right_parameters", [])
        for proxy_param_name in right_params:
            proxy_param = self.get_parameter_by_name(proxy_param_name)
            if proxy_param is None:
                continue

            # Find the internal node connected to this proxy parameter
            # The internal connection goes: InternalNode -> ProxyParameter
            incoming_connections = connections.get_incoming_connections_to_parameter(self, proxy_param)
            if not incoming_connections:
                continue

            # Get the first connection (there should only be one internal connection)
            for connection in incoming_connections:
                if not connection.is_node_group_internal:
                    continue

                # Get the value from the internal node's output parameter
                internal_node = connection.source_node
                internal_param = connection.source_parameter

                if internal_param.name in internal_node.parameter_output_values:
                    value = internal_node.parameter_output_values[internal_param.name]
                else:
                    value = internal_node.get_parameter_value(internal_param.name)

                # Set the value on the NodeGroup's proxy parameter output
                if value is not None:
                    self.parameter_output_values[proxy_param_name] = value
                break

    def process(self) -> Any:
        """Synchronous process method - not used for proxy nodes."""
