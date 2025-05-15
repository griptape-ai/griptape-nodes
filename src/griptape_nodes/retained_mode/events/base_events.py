from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping  # noqa: TC003
from dataclasses import field
from typing import Any, ClassVar, Generic, TypeVar

from griptape.events import BaseEvent as GtBaseEvent
from pydantic import BaseModel, ConfigDict, Field, model_serializer
from pydantic.dataclasses import dataclass


class Payload(BaseModel):
    """Base class for all payload types. Customers will derive from this."""

    @model_serializer()
    def _serialize(self) -> Mapping[str, Any]:
        from griptape.mixins.serializable_mixin import SerializableMixin

        def encode(obj: Any) -> Any:
            if isinstance(obj, SerializableMixin):
                return obj.to_dict()
            if isinstance(obj, BaseModel):
                return obj.model_dump()
            return obj

        return {name: encode(value) for name, value in self.__dict__.items()}


# Request payload base class with optional request ID
class RequestPayload(Payload, ABC):
    request_id: str | None = None


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


class WorkflowAlteredMixin:
    """Mixin for a ResultPayload that guarantees that a workflow was altered."""

    altered_workflow_state: bool = field(default=True, init=False)


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
P = TypeVar("P", bound=RequestPayload)
R = TypeVar("R", bound=ResultPayload)
E = TypeVar("E", bound=ExecutionPayload)
A = TypeVar("A", bound=AppPayload)


class BaseEvent(BaseModel, ABC):
    """Abstract base class for all events."""

    _session_id: ClassVar[str | None] = None

    event_type: str | None = None
    session_id: str | None = Field(
        default_factory=lambda: BaseEvent._session_id,
        description="SSE session identifier propagated to every event",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if self.event_type is None:
            self.event_type = self.__class__.__name__

    @model_serializer(mode="wrap")
    def _serialize(self, val, handler) -> Mapping[str, Any]:
        from griptape.mixins.serializable_mixin import SerializableMixin

        def encode(obj: Any) -> Any:
            if isinstance(obj, SerializableMixin):
                return obj.to_dict()
            if isinstance(obj, BaseModel):
                return obj.model_dump()
            return handler(obj)

        return {name: encode(value) for name, value in val.__dict__.items()}

    @abstractmethod
    def get_request(self) -> Payload:
        """Get the request payload for this event.

        Returns:
            Payload: The request payload
        """


class EventRequest(BaseEvent, Generic[P]):
    """Request event."""

    request: P
    request_type: str | None = None

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if self.request_type is None:
            self.request_type = self.request.__class__.__name__

    def get_request(self) -> P:
        """Get the request payload for this event.

        Returns:
            P: The request payload
        """
        return self.request


class EventResult(BaseEvent, Generic[P, R], ABC):
    """Abstract base class for result events."""

    request: P
    result: R
    retained_mode: str | None = None
    request_type: str | None = None
    result_type: str | None = None

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if self.request_type is None:
            self.request_type = self.request.__class__.__name__

        if self.result_type is None:
            self.result_type = self.result.__class__.__name__

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


# EXECUTION EVENT BASE (this event type is used for the execution of a Griptape Nodes flow)
class ExecutionEvent(BaseEvent, Generic[E]):
    payload: E
    payload_type: str | None = None

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if self.payload_type is None:
            self.payload_type = self.payload.__class__.__name__

    def get_request(self) -> E:
        """Get the payload for this event.

        Returns:
            E: The execution payload
        """
        return self.payload


# Events sent as part of the lifecycle of the Griptape Nodes application.
class AppEvent(BaseEvent, Generic[A]):
    payload: A

    def get_request(self) -> A:
        """Get the payload for this event.

        Returns:
            A: The app event payload
        """
        return self.payload


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
