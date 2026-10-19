from dataclasses import dataclass
from typing import ClassVar

import pytest

from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.request_handlers import RequestScope, handles


@dataclass(kw_only=True)
class _PingRequest(RequestPayload):
    pass


@dataclass(kw_only=True)
class _PongRequest(RequestPayload):
    pass


class _Base:
    request_scope: ClassVar[RequestScope] = RequestScope.HOST

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
    request_scope: ClassVar[RequestScope] = RequestScope.HOST

    @handles(_PingRequest)
    @handles(_PongRequest)
    def on_either(self, request: RequestPayload) -> None:
        pass


class _Static:
    request_scope: ClassVar[RequestScope] = RequestScope.HOST

    @staticmethod
    @handles(_PingRequest)
    def on_ping(request: _PingRequest) -> None:
        pass

    @classmethod
    @handles(_PongRequest)
    def on_pong(cls, request: _PongRequest) -> None:
        pass


class _MixedScopes:
    request_scope: ClassVar[RequestScope] = RequestScope.WORKFLOW

    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest) -> None:
        pass

    @handles(_PongRequest, scope=RequestScope.HOST)
    def on_pong(self, request: _PongRequest) -> None:
        pass


class _OnlyHandlerScopes:
    @handles(_PingRequest, scope=RequestScope.OPTIONAL_WORKFLOW)
    def on_ping(self, request: _PingRequest) -> None:
        pass


class _UndeclaredScope:
    @handles(_PingRequest)
    def on_ping(self, request: _PingRequest) -> None:
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

    def test_two_different_scopes_on_one_handler_raise(self) -> None:
        with pytest.raises(TypeError, match="two different scopes"):

            class _Conflicting:
                @handles(_PingRequest, scope=RequestScope.HOST)
                @handles(_PongRequest, scope=RequestScope.WORKFLOW)
                def on_either(self, request: RequestPayload) -> None:
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

    def test_owner_scope_is_the_default_and_a_handler_scope_overrides_it(self) -> None:
        event_manager = EventManager()

        event_manager.register_request_handlers(_MixedScopes())

        assert event_manager.scope_for(_PingRequest) is RequestScope.WORKFLOW
        assert event_manager.scope_for(_PongRequest) is RequestScope.HOST

    def test_handler_scopes_stand_in_for_an_owner_that_declares_none(self) -> None:
        event_manager = EventManager()

        event_manager.register_request_handlers(_OnlyHandlerScopes())

        assert event_manager.scope_for(_PingRequest) is RequestScope.OPTIONAL_WORKFLOW

    def test_a_handler_with_no_scope_on_an_owner_with_none_raises(self) -> None:
        event_manager = EventManager()

        with pytest.raises(TypeError, match="declares no request_scope"):
            event_manager.register_request_handlers(_UndeclaredScope())

        assert event_manager.get_manager_for_request_type(_PingRequest) is None

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
