"""Tests for the engine-role log filter and handler in app.py."""

from __future__ import annotations

import logging
import re

import pytest
from rich.table import Table
from rich.text import Text

from griptape_nodes.app.app import _EngineRoleFilter, _EngineRoleHandler, _prefix_to_color


def _make_record(prefix: str = "", msg: str = "test message") -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    record.engine_prefix = prefix  # type: ignore[attr-defined]
    return record


class TestPrefixToColor:
    def test_returns_hex_color_string(self) -> None:
        color = _prefix_to_color("Orchestrator")

        assert re.match(r"^#[0-9a-f]{6}$", color)

    def test_is_deterministic(self) -> None:
        assert _prefix_to_color("Worker-abc") == _prefix_to_color("Worker-abc")

    def test_different_prefixes_produce_different_colors(self) -> None:
        assert _prefix_to_color("Orchestrator") != _prefix_to_color("Worker-abc123")

    def test_empty_prefix_returns_hex_color(self) -> None:
        color = _prefix_to_color("")

        assert re.match(r"^#[0-9a-f]{6}$", color)


class TestEngineRoleFilter:
    def test_default_prefix_is_empty_string(self) -> None:
        f = _EngineRoleFilter()

        assert f.prefix == ""

    def test_filter_sets_engine_prefix_on_record(self) -> None:
        f = _EngineRoleFilter()
        f.prefix = "Orchestrator"
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="hi", args=(), exc_info=None
        )

        f.filter(record)

        assert record.engine_prefix == "Orchestrator"  # type: ignore[attr-defined]

    def test_filter_returns_true(self) -> None:
        f = _EngineRoleFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="hi", args=(), exc_info=None
        )

        assert f.filter(record) is True

    def test_filter_reflects_prefix_change(self) -> None:
        f = _EngineRoleFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0, msg="hi", args=(), exc_info=None
        )
        f.prefix = "Worker-xyz"

        f.filter(record)

        assert record.engine_prefix == "Worker-xyz"  # type: ignore[attr-defined]


class TestEngineRoleHandlerRender:
    @pytest.fixture
    def handler(self) -> _EngineRoleHandler:
        return _EngineRoleHandler(show_time=True, show_path=False, markup=True, rich_tracebacks=True)

    def test_render_without_prefix_returns_a_value(self, handler: _EngineRoleHandler) -> None:
        record = _make_record(prefix="")

        result = handler.render(record=record, traceback=None, message_renderable=Text("hello"))

        assert result is not None

    def test_render_with_prefix_returns_table(self, handler: _EngineRoleHandler) -> None:
        record = _make_record(prefix="Orchestrator")

        result = handler.render(record=record, traceback=None, message_renderable=Text("hello"))

        assert isinstance(result, Table)

    def test_render_with_prefix_and_no_traceback_returns_table(self, handler: _EngineRoleHandler) -> None:
        record = _make_record(prefix="Worker-abc12345")

        result = handler.render(record=record, traceback=None, message_renderable=Text("error"))

        assert isinstance(result, Table)

    def test_render_with_prefix_and_traceback_returns_table(self, handler: _EngineRoleHandler) -> None:
        # The render method uses `traceback: object` and cast() is a no-op at runtime,
        # so any ConsoleRenderable (e.g. Text) is valid as a stand-in for a real Traceback.
        record = _make_record(prefix="Worker-abc12345")

        result = handler.render(record=record, traceback=Text("traceback text"), message_renderable=Text("error"))

        assert isinstance(result, Table)
