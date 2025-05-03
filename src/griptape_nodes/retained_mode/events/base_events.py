from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from griptape.artifacts import BaseArtifact
from griptape.events import BaseEvent as GtBaseEvent
from griptape.mixins.serializable_mixin import SerializableMixin
from griptape.structures import Structure
from griptape.tools import BaseTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import builtins


# The Payload class is a marker interface
class Payload(ABC):  # noqa: B024
    """Base class for all payload types. Customers will derive from this."""


# Request payload base class with optional request ID
@dataclass(kw_only=True)
class RequestPayload(Payload, ABC):
    request_id: int | None = None


# Result payload base class with abstract succeeded/failed methods, and indicator whether the current workflow was altered.
class ResultPayload(Payload, ABC):
    """Base class for all result payloads."""

    """When set to True, alerts clients that this result made changes to the workflow state.
    Editors can use this to determine if the workflow is dirty and needs to be re-saved, for example."""
    altered_workflow_state: bool = False

    @abstractmethod
    def succeeded(self) -> bool:
        """Returns whether this result represents a success or failure.

        Returns:
            bool: True if success, False if failure
        """

    def failed(self) -> bool:
        return not self.succeeded()


@dataclass
class WorkflowAlteredMixin:
    """Mixin for a ResultPayload that guarantees that a workflow was altered."""

    altered_workflow_state: bool = field(default=True, init=False)


@dataclass
class WorkflowNotAlteredMixin:
    """Mixin for a ResultPayload that guarantees that a workflow was NOT altered."""

    altered_workflow_state: bool = field(default=False, init=False)


# Success result payload abstract base class
class ResultPayloadSuccess(ResultPayload, ABC):
    """Abstract base class for success result payloads."""

    def succeeded(self) -> bool:
        """Returns True as this is a success result.

        Returns:
            bool: Always True
        """
        return True


# Failure result payload abstract base class
class ResultPayloadFailure(ResultPayload, ABC):
    """Abstract base class for failure result payloads."""

    def succeeded(self) -> bool:
        """Returns False as this is a failure result.

        Returns:
            bool: Always False
        """
        return False


class ExecutionPayload(Payload):
    pass


class AppPayload(Payload):
    pass


# Type variables for our generic payloads
P = TypeVar("P", bound=Payload)
R = TypeVar("R", bound=ResultPayload)
E = TypeVar("E", bound=ExecutionPayload)
A = TypeVar("A", bound=AppPayload)


class BaseEvent(BaseModel, ABC):
    """Abstract base class for all events."""

    # Keeping here instead of in GriptapeNodes to avoid circular import hell.
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/848
    _session_id: ClassVar[str | None] = None

    # Instance variable with a default_factory that references the class variable
    session_id: str | None = Field(default_factory=lambda: BaseEvent._session_id)

    # Custom JSON encoder for the payload
    class Config:
        """Pydantic configuration for the BaseEvent class."""

        arbitrary_types_allowed = True
        json_encoders: ClassVar[dict] = {
            # Use to_dict() methods for Griptape objects
            BaseArtifact: lambda obj: obj.to_dict(),
            BaseTool: lambda obj: obj.to_dict(),
            Structure: lambda obj: obj.to_dict(),
        }

    def dict(self, *args, **kwargs) -> dict[str, Any]:
        """Override dict to handle payload serialization and add event_type."""
        result = super().dict(*args, **kwargs)

        # Add event type based on class name
        result["event_type"] = self.__class__.__name__

        # Include payload type information in serialized output
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, Payload):
                result[f"{field_name}_type"] = field_value.__class__.__name__

        return result

    def json(self, **kwargs) -> str:
        """Serialize to JSON string."""

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/906
        def default_encoder(obj: Any) -> Any:
            """Custom JSON encoder for various object types.

            Attempts the following encodings in order:
            1. If the object is a SerializableMixin, call to_dict()
            2. If the object is a Pydantic model, call model_dump()
            3. Attempt to use the default JSON encoder
            4. If all else fails, return the string representation of the object

            Args:
                obj: The object to encode


            """
            if isinstance(obj, SerializableMixin):
                return obj.to_dict()
            if isinstance(obj, BaseModel):
                return obj.model_dump()
            try:
                return json.JSONEncoder().default(obj)
            except TypeError:
                return str(obj)

        return json.dumps(self.dict(), default=default_encoder, **kwargs)

    @abstractmethod
    def get_request(self) -> Payload:
        """Get the request payload for this event.

        Returns:
            Payload: The request payload
        """


class EventRequest(BaseEvent, Generic[P]):
    """Request event."""

    request: P

    def __init__(self, **data) -> None:
        """Initialize an EventRequest, inferring the generic type if needed."""
        # Call the parent class initializer
        super().__init__(**data)

    def dict(self, *args, **kwargs) -> dict[str, Any]:
        """Override dict to handle payload serialization."""
        result = super().dict(*args, **kwargs)

        if hasattr(self.request, "__dict__"):
            result["request"] = self.request.__dict__
        elif is_dataclass(self.request):
            result["request"] = asdict(self.request)
        else:
            # Handle other object types if needed
            result["request"] = str(self.request)

        return result

    def get_request(self) -> P:
        """Get the request payload for this event.

        Returns:
            P: The request payload
        """
        return self.request

    @classmethod
    def from_dict(cls, data: builtins.dict[str, Any], payload_type: type[P]) -> EventRequest:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Create an event from a dictionary."""
        # Make a copy to avoid modifying the input
        event_data = data.copy()

        # Extract payload data
        request_data = event_data.pop("request", {})

        # Create and attach the request payload
        if payload_type:
            if is_dataclass(payload_type):
                # Create dataclass instance
                request_payload = payload_type(**request_data)
            elif issubclass(payload_type, BaseModel):
                # Handle Pydantic models
                request_payload = payload_type.model_validate(request_data)
            else:
                # For regular classes, create an instance and set attributes
                request_payload = payload_type()
                for key, value in request_data.items():
                    setattr(request_payload, key, value)
        else:
            msg = "Cannot create EventRequest without a payload type"
            raise ValueError(msg)

        # Create the event instance with the payload
        return cls(request=request_payload)


class EventResult(BaseEvent, Generic[P, R], ABC):
    """Abstract base class for result events."""

    request: P
    result: R
    retained_mode: str | None = None

    def __init__(self, **data) -> None:
        """Initialize an EventResult, inferring the generic types if needed."""
        # Call the parent class initializer
        super().__init__(**data)

    def dict(self, *args, **kwargs) -> dict[str, Any]:
        """Override dict to handle payload serialization."""
        result = super().dict(*args, **kwargs)

        if hasattr(self.request, "__dict__"):
            result["request"] = self.request.__dict__
        elif is_dataclass(self.request):
            result["request"] = asdict(self.request)
        else:
            result["request"] = str(self.request)

        # Handle result payload
        if is_dataclass(self.result):
            try:
                result["result"] = asdict(self.result)
            except TypeError:
                result["result"] = self.result.__dict__
        elif hasattr(self.result, "__dict__"):
            result["result"] = self.result.__dict__
        else:
            result["result"] = str(self.result)
        if self.retained_mode:
            result["retained_mode"] = self.retained_mode

        return result

    def get_request(self) -> P:
        """Get the request payload for this event.

        Returns:
            P: The request payload
        """
        return self.request

    def get_result(self) -> R:
        """Get the result payload for this event.

        Returns:
            R: The result payload
        """
        return self.result

    @abstractmethod
    def succeeded(self) -> bool:
        """Returns whether this result represents a success or failure.

        Returns:
            bool: True if success, False if failure
        """

    @classmethod
    def from_dict(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls, data: builtins.dict[str, Any], req_payload_type: type[P], res_payload_type: type[R]
    ) -> EventResult:
        """Create an event from a dictionary."""
        # Make a copy to avoid modifying the input
        event_data = data.copy()

        # Extract payload data
        request_data = event_data.pop("request", {})
        result_data = event_data.pop("result", {})

        # Process request payload
        if req_payload_type:
            if is_dataclass(req_payload_type):
                request_payload = req_payload_type(**request_data)
            elif issubclass(req_payload_type, BaseModel):
                request_payload = req_payload_type.model_validate(request_data)
            else:
                request_payload = req_payload_type()
                for key, value in request_data.items():
                    setattr(request_payload, key, value)
        else:
            msg = f"Cannot create {cls.__name__} without a request payload type"
            raise ValueError(msg)

        # Process result payload
        if res_payload_type:
            if is_dataclass(res_payload_type):
                result_payload = res_payload_type(**result_data)
            elif issubclass(res_payload_type, BaseModel):
                result_payload = res_payload_type.model_validate(result_data)
            else:
                result_payload = res_payload_type()
                for key, value in result_data.items():
                    setattr(result_payload, key, value)
        else:
            msg = f"Cannot create {cls.__name__} without a result payload type"
            raise ValueError(msg)

        # Create the event instance with all required fields
        return cls(request=request_payload, result=result_payload)


class EventResultSuccess(EventResult[P, R]):
    """Success result event."""

    def succeeded(self) -> bool:
        """Returns True as this is a success result.

        Returns:
            bool: Always True
        """
        return True


class EventResultFailure(EventResult[P, R]):
    """Failure result event."""

    def succeeded(self) -> bool:
        """Returns False as this is a failure result.

        Returns:
            bool: Always False
        """
        return False


# Helper function to deserialize event from JSON
def deserialize_event(json_data: str | dict | Any) -> BaseEvent:
    """Deserialize an event from JSON or dict, using the payload type information embedded in the data.

    Args:
        json_data: JSON string or dictionary representing an event

    Returns:
        The deserialized event with the correct payload
    """
    from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

    # Parse the data if it's a string, otherwise use as is
    if isinstance(json_data, str):
        data = json.loads(json_data)
    elif isinstance(json_data, dict):
        data = json_data
    else:
        msg = "Expected json_data to be str or dict"
        raise TypeError(msg)

    event_type = data.get("event_type")

    # Get payload types from embedded type information
    request_type_name = data.get("request_type")
    result_type_name = data.get("result_type")

    # Look up the actual payload types
    request_type = PayloadRegistry.get_type(request_type_name) if request_type_name else None
    result_type = PayloadRegistry.get_type(result_type_name) if result_type_name else None

    # Determine the event class based on event_type and deserialize
    if event_type == "EventRequest":
        if request_type:
            return EventRequest.from_dict(data, request_type)
        msg = f"Cannot deserialize EventRequest: unknown payload type '{request_type_name}'"
        raise ValueError(msg)
    if event_type == "EventResultSuccess":
        if request_type and result_type:
            return EventResultSuccess.from_dict(data, request_type, result_type)
        msg = f"Cannot deserialize EventResultSuccess: unknown payload types request={request_type_name}, result={result_type_name}"
        raise ValueError(msg)
    if event_type == "EventResultFailure":
        if request_type and result_type:
            return EventResultFailure.from_dict(data, request_type, result_type)
        msg = f"Cannot deserialize EventResultFailure: unknown payload types request={request_type_name}, result={result_type_name}"
        raise ValueError(msg)
    msg = f"Unknown/unsupported event type '{event_type}' encountered."
    raise TypeError(msg)


# EXECUTION EVENT BASE (this event type is used for the execution of a Griptape Nodes flow)
class ExecutionEvent(BaseEvent, Generic[E]):
    payload: E

    def __init__(self, **data) -> None:
        """Initialize an ExecutionEvent, inferring the generic type if needed."""
        # Call the parent class initializer
        super().__init__(**data)

    def dict(self, *args, **kwargs) -> dict[str, Any]:
        """Override dict to handle payload serialization."""
        result = super().dict(*args, **kwargs)

        # Convert Payload object to dict
        if hasattr(self.payload, "__dict__"):
            result["payload"] = self.payload.__dict__
        elif is_dataclass(self.payload):
            result["payload"] = asdict(self.payload)
        else:
            # Handle other object types if needed
            result["payload"] = str(self.payload)
        return result

    def get_request(self) -> E:
        """Get the payload for this event.

        Returns:
            E: The execution payload
        """
        return self.payload

    @classmethod
    def from_dict(cls, data: builtins.dict[str, Any], payload_type: type[E]) -> ExecutionEvent:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Create an event from a dictionary."""
        # Make a copy to avoid modifying the input
        event_data = data.copy()

        # Extract payload data
        payload_data = event_data.pop("payload", {})

        # Create and attach the payload
        if payload_type:
            if is_dataclass(payload_type):
                # Create dataclass instance
                event_payload = payload_type(**payload_data)
            elif issubclass(payload_type, BaseModel):
                # Handle Pydantic models
                event_payload = payload_type.model_validate(payload_data)
            else:
                # For regular classes, create an instance and set attributes
                event_payload = payload_type()
                for key, value in payload_data.items():
                    setattr(event_payload, key, value)
        else:
            msg = "Cannot create ExecutionEvent without a payload type"
            raise ValueError(msg)

        # Create the event instance with the payload
        return cls(payload=event_payload, **event_data)


# Events sent as part of the lifecycle of the Griptape Nodes application.
class AppEvent(BaseEvent, Generic[A]):
    payload: A

    def __init__(self, **data) -> None:
        """Initialize an AppEvent, inferring the generic type if needed."""
        # Call the parent class initializer
        super().__init__(**data)

    def dict(self, *args, **kwargs) -> dict[str, Any]:
        """Override dict to handle payload serialization."""
        result = super().dict(*args, **kwargs)

        if isinstance(self.payload, list) and all(hasattr(item, "__dict__") for item in self.payload):
            result["payload"] = [
                {k: v for k, v in item.__dict__.items() if not k.startswith("_")} for item in self.payload
            ]
        elif hasattr(self.payload, "__dict__"):
            result["payload"] = self.payload.__dict__
        else:
            # Handle other object types if needed
            result["payload"] = str(self.payload)
        return result

    def get_request(self) -> A:
        """Get the payload for this event.

        Returns:
            A: The app event payload
        """
        return self.payload

    @classmethod
    def from_dict(cls, data: builtins.dict[str, Any], payload_type: type[E]) -> AppEvent:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Create an event from a dictionary."""
        # Make a copy to avoid modifying the input
        event_data = data.copy()

        # Extract payload data
        payload_data = event_data.pop("payload", {})

        # Create and attach the payload
        if payload_type:
            if is_dataclass(payload_type):
                # Create dataclass instance
                event_payload = payload_type(**payload_data)
            elif issubclass(payload_type, BaseModel):
                # Handle Pydantic models
                event_payload = payload_type.model_validate(payload_data)
            else:
                # For regular classes, create an instance and set attributes
                event_payload = payload_type()
                for key, value in payload_data.items():
                    setattr(event_payload, key, value)
        else:
            msg = "Cannot create AppEvent without a payload type"
            raise ValueError(msg)

        # Create the event instance with the payload
        return cls(payload=event_payload, **event_data)


@dataclass
class GriptapeNodeEvent(GtBaseEvent):
    wrapped_event: EventResult


@dataclass
class ExecutionGriptapeNodeEvent(GtBaseEvent):
    wrapped_event: ExecutionEvent = field()


@dataclass
class ProgressEvent(GtBaseEvent):
    value: Any = field()
    node_name: str = field()
    parameter_name: str = field()
