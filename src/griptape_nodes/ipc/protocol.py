"""IPC protocol message definitions for library worker communication.

Defines the message envelope and command/result dataclasses exchanged
between the parent engine and library worker subprocesses over WebSocket.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IPCMessage:
    """Envelope for all IPC messages between parent and worker."""

    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    message_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCMessage:
        return cls(
            message_id=data.get("message_id", uuid.uuid4().hex),
            message_type=data.get("message_type", ""),
            payload=data.get("payload", {}),
        )


# --- Parent -> Child Commands ---


@dataclass
class CreateNodeCommand:
    """Command to create a node instance in the worker."""

    node_type: str
    node_name: str
    metadata: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "node_name": self.node_name,
            "metadata": self.metadata,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CreateNodeCommand:
        return cls(
            node_type=payload["node_type"],
            node_name=payload["node_name"],
            metadata=payload.get("metadata"),
        )


@dataclass
class ExecuteNodeCommand:
    """Command to execute a node's aprocess() in the worker."""

    node_name: str
    parameter_values: dict[str, Any] = field(default_factory=dict)
    entry_control_parameter_name: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "parameter_values": self.parameter_values,
            "entry_control_parameter_name": self.entry_control_parameter_name,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ExecuteNodeCommand:
        return cls(
            node_name=payload["node_name"],
            parameter_values=payload.get("parameter_values", {}),
            entry_control_parameter_name=payload.get("entry_control_parameter_name"),
        )


@dataclass
class DestroyNodeCommand:
    """Command to destroy a node instance in the worker."""

    node_name: str

    def to_payload(self) -> dict[str, Any]:
        return {"node_name": self.node_name}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> DestroyNodeCommand:
        return cls(node_name=payload["node_name"])


@dataclass
class CancelNodeCommand:
    """Command to cancel an in-flight node execution."""

    node_name: str

    def to_payload(self) -> dict[str, Any]:
        return {"node_name": self.node_name}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CancelNodeCommand:
        return cls(node_name=payload["node_name"])


@dataclass
class SyncConfigCommand:
    """Command to synchronize config and secrets to the worker."""

    config_data: dict[str, Any] = field(default_factory=dict)
    secrets_data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "config_data": self.config_data,
            "secrets_data": self.secrets_data,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SyncConfigCommand:
        return cls(
            config_data=payload.get("config_data", {}),
            secrets_data=payload.get("secrets_data", {}),
        )


# --- Child -> Parent Results ---


@dataclass
class ParameterSchema:
    """Serialized parameter definition for proxy node construction."""

    name: str
    type: str | None = None
    input_types: list[str] | None = None
    output_type: str | None = None
    allowed_modes: list[str] | None = None
    default_value: Any = None
    tooltip: str = ""
    ui_options: dict[str, Any] | None = None

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
        )


@dataclass
class CreateNodeResult:
    """Result of creating a node in the worker, includes parameter schema."""

    node_name: str
    parameter_schemas: list[ParameterSchema] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "parameter_schemas": [s.to_dict() for s in self.parameter_schemas],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CreateNodeResult:
        return cls(
            node_name=payload["node_name"],
            parameter_schemas=[ParameterSchema.from_dict(s) for s in payload.get("parameter_schemas", [])],
        )


@dataclass
class ExecuteNodeResult:
    """Result of executing a node in the worker."""

    node_name: str
    parameter_output_values: dict[str, Any] = field(default_factory=dict)
    next_control_output_name: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "parameter_output_values": self.parameter_output_values,
            "next_control_output_name": self.next_control_output_name,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ExecuteNodeResult:
        return cls(
            node_name=payload["node_name"],
            parameter_output_values=payload.get("parameter_output_values", {}),
            next_control_output_name=payload.get("next_control_output_name"),
        )


@dataclass
class ExecuteNodeError:
    """Error result from a failed node execution in the worker."""

    node_name: str
    error: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "error": self.error,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ExecuteNodeError:
        return cls(
            node_name=payload["node_name"],
            error=payload.get("error", "Unknown error"),
        )


@dataclass
class EventBroadcast:
    """Forwarded event from the worker for UI display."""

    event_data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"event_data": self.event_data}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EventBroadcast:
        return cls(event_data=payload.get("event_data", {}))


# Message type constants
CREATE_NODE = "create_node"
EXECUTE_NODE = "execute_node"
DESTROY_NODE = "destroy_node"
CANCEL_NODE = "cancel_node"
SYNC_CONFIG = "sync_config"
CREATE_NODE_RESULT = "create_node_result"
EXECUTE_NODE_RESULT = "execute_node_result"
EXECUTE_NODE_ERROR = "execute_node_error"
EVENT_BROADCAST = "event_broadcast"
WORKER_READY = "worker_ready"
