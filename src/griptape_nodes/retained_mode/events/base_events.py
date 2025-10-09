from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from griptape.artifacts import BaseArtifact
from griptape.mixins.serializable_mixin import SerializableMixin
from griptape.structures import Structure
from griptape.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import builtins


@dataclass
class ResultDetail:
    """A single detail about an operation result, including logging level and human readable message."""

    level: int
    message: str


@dataclass
class ResultDetails:
    """Container for multiple ResultDetail objects."""

    result_details: list[ResultDetail]

    def __init__(
        self,
        *result_details: ResultDetail,
        message: str | None = None,
        level: int | None = None,
        logger: logging.Logger | str | None = "griptape_nodes",
    ):
        """Initialize with ResultDetail objects or create a single one from message/level.

        Args:
            *result_details: Variable number of ResultDetail objects
            message: If provided, creates a single ResultDetail with this message
            level: Logging level for the single ResultDetail (required if message is provided)
            logger: Logger to use for auto-logging. String for logger name, Logger object, or None to skip
        """
        # Handle single message/level convenience
        if message is not None:
            if level is None:
                err_msg = "level is required when message is provided"
                raise ValueError(err_msg)
            if result_details:
                err_msg = "Cannot provide both result_details and message/level"
                raise ValueError(err_msg)
            self.result_details = [ResultDetail(level=level, message=message)]
        else:
            if not result_details:
                err_msg = "ResultDetails requires at least one ResultDetail or message/level"
                raise ValueError(err_msg)
            self.result_details = list(result_details)

        # Auto-log if logger is provided
        if logger is not None:
            try:
                if isinstance(logger, str):
                    logger = logging.getLogger(logger)

                for detail in self.result_details:
                    # Handle both string and int levels
                    logger.log(detail.level, detail.message)
            except Exception:  # noqa: S110
                # If logging fails for any reason, don't let it break the ResultDetails creation
                pass


# The Payload class is a marker interface
class Payload(ABC):  # noqa: B024
    """Base class for all payload types. Customers will derive from this."""


# Request payload base class with optional request ID
@dataclass(kw_only=True)
class RequestPayload(Payload, ABC):
    request_id: int | None = None


# Result payload base class with abstract succeeded/failed methods, and indicator whether the current workflow was altered.
@dataclass(kw_only=True)
class ResultPayload(Payload, ABC):
    """Base class for all result payloads."""

    result_details: ResultDetails | str
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


class SkipTheLineMixin:
    """Mixin for events that should skip the event queue and be processed immediately.

    Events that implement this mixin will be handled directly without being added
    to the event queue, allowing for priority processing of critical events like
    heartbeats or other time-sensitive operations.
    """


# Success result payload abstract base class
@dataclass(kw_only=True)
class ResultPayloadSuccess(ResultPayload, ABC):
    """Abstract base class for success result payloads."""

    result_details: ResultDetails | str

    def __post_init__(self) -> None:
        """Initialize success result with INFO level default for strings."""
        if isinstance(self.result_details, str):
            self.result_details = ResultDetails(message=self.result_details, level=logging.DEBUG)

    def succeeded(self) -> bool:
        """Returns True as this is a success result.

        Returns:
            bool: Always True
        """
        return True


# Failure result payload abstract base class
@dataclass(kw_only=True)
class ResultPayloadFailure(ResultPayload, ABC):
    """Abstract base class for failure result payloads."""

    result_details: ResultDetails | str
    exception: Exception | None = None

    def __post_init__(self) -> None:
        """Initialize failure result with ERROR level default for strings."""
        if isinstance(self.result_details, str):
            self.result_details = ResultDetails(message=self.result_details, level=logging.ERROR)

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
P = TypeVar("P", bound=RequestPayload)
R = TypeVar("R", bound=ResultPayload)
E = TypeVar("E", bound=ExecutionPayload)
A = TypeVar("A", bound=AppPayload)


class BaseEvent(BaseModel, ABC):
    """Abstract base class for all events."""

    # Instance fields for engine and session identification
    _engine_id: ClassVar[str | None] = None
    _session_id: ClassVar[str | None] = None

    engine_id: str | None = Field(default_factory=lambda: BaseEvent._engine_id)
    session_id: str | None = Field(default_factory=lambda: BaseEvent._session_id)

    # Custom JSON encoder for the payload
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={
            # Use to_dict() methods for Griptape objects
            BaseArtifact: lambda obj: obj.to_dict(),
            BaseTool: lambda obj: obj.to_dict(),
            Structure: lambda obj: obj.to_dict(),
        },
    )

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


class EventRequest[P: Payload](BaseEvent):
    """Request event."""

    request: P
    request_id: str | None = None
    response_topic: str | None = None

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
        return cls(request=request_payload, **event_data)


class EventResult[P: RequestPayload, R: ResultPayload](BaseEvent, ABC):
    """Abstract base class for result events."""

    request: P
    result: R
    request_id: str | None = None
    response_topic: str | None = None
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
    def _create_payload_instance(cls, payload_type: type, payload_data: dict[str, Any]) -> Any:
        """Create a payload instance from data, handling dataclass init=False fields."""
        if is_dataclass(payload_type):
            # Filter out fields that have init=False to avoid TypeError
            init_fields = {f.name for f in fields(payload_type) if f.init}
            filtered_data = {k: v for k, v in payload_data.items() if k in init_fields}
            return payload_type(**filtered_data)
        if issubclass(payload_type, BaseModel):
            return payload_type.model_validate(payload_data)
        instance = payload_type()
        for key, value in payload_data.items():
            setattr(instance, key, value)
        return instance

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
            request_payload = cls._create_payload_instance(req_payload_type, request_data)
        else:
            msg = f"Cannot create {cls.__name__} without a request payload type"
            raise ValueError(msg)

        # Process result payload
        if res_payload_type:
            result_payload = cls._create_payload_instance(res_payload_type, result_data)
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
class ExecutionEvent[E: ExecutionPayload](BaseEvent):
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
class AppEvent[A: AppPayload](BaseEvent):
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


class GriptapeNodeEvent(BaseEvent):
    wrapped_event: EventResult

    def get_request(self) -> Payload:
        """Get the request from the wrapped event."""
        return self.wrapped_event.get_request()


class ExecutionGriptapeNodeEvent(BaseEvent):
    wrapped_event: ExecutionEvent

    def get_request(self) -> Payload:
        """Get the request from the wrapped event."""
        return self.wrapped_event.get_request()


@dataclass
class ProgressEvent:
    value: Any = field()
    node_name: str = field()
    parameter_name: str = field()


# Special internal request for flushing parameter changes
@dataclass(kw_only=True)
class FlushParameterChangesRequest(RequestPayload, WorkflowNotAlteredMixin):
    pass


@dataclass
class FlushParameterChangesResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
class FlushParameterChangesResultFailure(ResultPayloadFailure):
    pass
