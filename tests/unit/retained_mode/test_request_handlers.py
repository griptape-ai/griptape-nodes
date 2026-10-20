from dataclasses import dataclass

import pytest

from griptape_nodes.app.worker_routing import RemoteHandler
from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.request_handlers import RequestScope, handles
from griptape_nodes.retained_mode.runtime.workflow_runtime import WorkflowRuntime


@dataclass(kw_only=True)
class _PingRequest(RequestPayload):
    pass


@dataclass(kw_only=True)
class _PongRequest(RequestPayload):
    pass


class _Base:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest) -> None:
        pass


class _Child(_Base):
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest) -> None:
        pass

    @handles(_PongRequest)
    def on_pong(self, request: _PongRequest) -> None:
        pass


class _UnmarkedOverride(_Base):
    def on_ping(self, request: _PingRequest) -> None:
        pass


class _RemarkedOverride(_Base):
    @handles(_PongRequest)
    def on_ping(self, request: RequestPayload) -> None:
        pass


class _Stacked:
    @handles(_PingRequest)
    @handles(_PongRequest)
    def on_either(self, request: RequestPayload) -> None:
        pass


class _Static:
    @staticmethod
    @handles(_PingRequest)
    def on_ping(request: _PingRequest) -> None:
        pass

    @classmethod
    @handles(_PongRequest)
    def on_pong(cls, request: _PongRequest) -> None:
        pass


class _TakesNoWorkflow:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest) -> None:
        pass


class _TakesWorkflow:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest, workflow: WorkflowRuntime) -> None:
        pass

    @handles(_PongRequest)
    def on_pong(self, request: _PongRequest, workflow: WorkflowRuntime | None = None) -> None:
        pass


class _OptionalAnnotationWithoutDefault:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest, workflow: WorkflowRuntime | None) -> None:
        pass


class _NonNoneDefault:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest, workflow: WorkflowRuntime = "main") -> None:  # type: ignore[assignment]
        pass


class _HidesItsSignature:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest, **kwargs: object) -> None:
        pass


class TestHandles:
    def test_bare_decorator_raises(self) -> None:
        with pytest.raises(TypeError, match="takes one or more request types"):

            class _Bare:
                @handles  # type: ignore[arg-type]
                def on_ping(self, request: _PingRequest) -> None:
                    pass

    def test_above_staticmethod_raises(self) -> None:
        with pytest.raises(TypeError, match="directly above `def`"):

            class _Misordered:
                @handles(_PingRequest)
                @staticmethod
                def on_ping(request: _PingRequest) -> None:
                    pass


class TestRegisterRequestHandlers:
    def test_registers_bound_methods_for_each_marked_type(self) -> None:
        event_manager = EventManager()
        owner = _Stacked()

        event_manager.register_request_handlers(owner)

        assert event_manager._request_type_to_manager[_PingRequest] == owner.on_either
        assert event_manager._request_type_to_manager[_PongRequest] == owner.on_either

    def test_subclass_override_registers_once(self) -> None:
        event_manager = EventManager()
        owner = _Child()

        event_manager.register_request_handlers(owner)

        assert event_manager._request_type_to_manager[_PingRequest] == owner.on_ping
        assert event_manager._request_type_to_manager[_PongRequest] == owner.on_pong

    def test_unmarked_override_inherits_parent_mark(self) -> None:
        event_manager = EventManager()
        owner = _UnmarkedOverride()

        event_manager.register_request_handlers(owner)

        assert event_manager._request_type_to_manager[_PingRequest] == owner.on_ping

    def test_remarked_override_replaces_parent_marks(self) -> None:
        event_manager = EventManager()
        owner = _RemarkedOverride()

        event_manager.register_request_handlers(owner)

        assert _PingRequest not in event_manager._request_type_to_manager
        assert event_manager._request_type_to_manager[_PongRequest] == owner.on_ping

    def test_registers_staticmethod_and_classmethod_handlers(self) -> None:
        event_manager = EventManager()
        owner = _Static()

        event_manager.register_request_handlers(owner)

        assert event_manager._request_type_to_manager[_PingRequest] == owner.on_ping
        assert event_manager._request_type_to_manager[_PongRequest] == owner.on_pong

    def test_second_owner_for_same_type_raises(self) -> None:
        event_manager = EventManager()
        event_manager.register_request_handlers(_Base())

        with pytest.raises(ValueError, match="already assigned"):
            event_manager.register_request_handlers(_Base())

    def test_a_handler_that_takes_no_workflow_is_host(self) -> None:
        event_manager = EventManager()

        event_manager.register_request_handlers(_TakesNoWorkflow())

        assert event_manager.scope_for(_PingRequest) is RequestScope.HOST

    def test_scope_for_an_unhandled_type_raises(self) -> None:
        event_manager = EventManager()

        with pytest.raises(TypeError, match="No manager found"):
            event_manager.scope_for(_PingRequest)

    def test_removing_a_handler_forgets_its_scope(self) -> None:
        event_manager = EventManager()
        event_manager.register_request_handlers(_Base())

        event_manager.remove_manager_from_request_type(_PingRequest)

        with pytest.raises(TypeError, match="No manager found"):
            event_manager.scope_for(_PingRequest)


class TestWorkflowParameter:
    def test_a_workflow_parameter_declares_the_scope(self) -> None:
        event_manager = EventManager()

        event_manager.register_request_handlers(_TakesWorkflow())

        assert event_manager.scope_for(_PingRequest) is RequestScope.WORKFLOW
        assert event_manager.scope_for(_PongRequest) is RequestScope.OPTIONAL_WORKFLOW

    def test_the_default_decides_not_the_annotation(self) -> None:
        event_manager = EventManager()

        event_manager.register_request_handlers(_OptionalAnnotationWithoutDefault())

        assert event_manager.scope_for(_PingRequest) is RequestScope.WORKFLOW

    def test_a_default_other_than_none_raises(self) -> None:
        event_manager = EventManager()

        with pytest.raises(TypeError, match="defaults to 'main'"):
            event_manager.register_request_handlers(_NonNoneDefault())

    def test_a_handler_that_hides_its_signature_raises(self) -> None:
        event_manager = EventManager()

        with pytest.raises(TypeError, match=r"accepts \*\*kwargs"):
            event_manager.register_request_handlers(_HidesItsSignature())

    def test_replacing_a_handler_keeps_its_scope(self) -> None:
        event_manager = EventManager()
        owner = _TakesWorkflow()
        event_manager.register_request_handlers(owner)

        event_manager.replace_manager_for_request_type(
            _PingRequest, RemoteHandler(original=owner.on_ping, event_manager=event_manager)
        )

        assert event_manager.scope_for(_PingRequest) is RequestScope.WORKFLOW
        assert _PingRequest in event_manager._request_types_taking_workflow

    def test_a_remote_handler_takes_a_workflow_when_the_handler_it_replaced_does(self) -> None:
        event_manager = EventManager()
        owner = _TakesWorkflow()

        takes = RemoteHandler(original=owner.on_ping, event_manager=event_manager)
        ignores = RemoteHandler(original=_Base().on_ping, event_manager=event_manager)

        assert takes.takes_workflow is True
        assert ignores.takes_workflow is False
