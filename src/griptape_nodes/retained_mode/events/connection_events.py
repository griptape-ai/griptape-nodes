from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class CreateConnectionRequest(RequestPayload):
    source_parameter_name: str
    target_parameter_name: str
    # If node name is None, use the Current Context
    source_node_id: str | None = None
    target_node_id: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False
    
    @property
    def source_node_name(self) -> str | None:
        """Get the source node name for backward compatibility with operation_manager.
        
        Returns:
            The name of the source node if source_node_id is provided, otherwise None
        """
        if self.source_node_id is None:
            return None
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        return GriptapeNodes.ObjectManager().get_name_by_id(self.source_node_id)
        
    @property
    def target_node_name(self) -> str | None:
        """Get the target node name for backward compatibility with operation_manager.
        
        Returns:
            The name of the target node if target_node_id is provided, otherwise None
        """
        if self.target_node_id is None:
            return None
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        return GriptapeNodes.ObjectManager().get_name_by_id(self.target_node_id)


@dataclass
@PayloadRegistry.register
class CreateConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class CreateConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionRequest(RequestPayload):
    source_parameter_name: str
    target_parameter_name: str
    # If node id is None, use the Current Context
    source_node_id: str | None = None
    target_node_id: str | None = None
    
    @property
    def source_node_name(self) -> str | None:
        """Get the source node name for backward compatibility with operation_manager.
        
        Returns:
            The name of the source node if source_node_id is provided, otherwise None
        """
        if self.source_node_id is None:
            return None
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        return GriptapeNodes.ObjectManager().get_name_by_id(self.source_node_id)
        
    @property
    def target_node_name(self) -> str | None:
        """Get the target node name for backward compatibility with operation_manager.
        
        Returns:
            The name of the target node if target_node_id is provided, otherwise None
        """
        if self.target_node_id is None:
            return None
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        return GriptapeNodes.ObjectManager().get_name_by_id(self.target_node_id)


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteConnectionResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeRequest(RequestPayload):
    # If node name is None, use the Current Context
    node_id: str | None = None
    
    @property
    def node_name(self) -> str | None:
        """Get the node name for backward compatibility with operation_manager.
        
        Returns:
            The name of the node if node_id is provided, otherwise None
        """
        if self.node_id is None:
            return None
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        return GriptapeNodes.ObjectManager().get_name_by_id(self.node_id)


@dataclass
class IncomingConnection:
    source_node_id: str
    source_parameter_name: str
    target_parameter_name: str


@dataclass
class OutgoingConnection:
    source_parameter_name: str
    target_node_id: str
    target_parameter_name: str


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    incoming_connections: list[IncomingConnection]
    outgoing_connections: list[OutgoingConnection]


@dataclass
@PayloadRegistry.register
class ListConnectionsForNodeResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
