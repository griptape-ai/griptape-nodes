"""Probe-level tests for strict-mode routing in _serialize_library_node_schemas.

Uses a fixture probe detector that calls ``report_violation`` from inside a
node class's ``__init__``. The scope wrapper on the probe loop is then
responsible for excluding violating classes from the returned schema list.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.strict_mode import report_violation
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class _CleanProbe:
    """Node class whose __init__ does nothing interesting."""

    parameters: list = []  # noqa: RUF012

    def __init__(self, name: str) -> None:
        self.name = name


class _ViolatingProbe:
    """Node class whose __init__ triggers a fixture strict-mode violation."""

    parameters: list = []  # noqa: RUF012

    def __init__(self, name: str) -> None:
        self.name = name
        report_violation(
            rule_id="fixture-probe-rule",
            message="fixture probe violation",
        )


class TestSerializeSchemasStrictMode:
    def _make_library(self, nodes: dict[str, type]) -> MagicMock:
        lib = MagicMock()
        lib.get_registered_nodes.return_value = list(nodes.keys())
        lib._node_types = nodes
        return lib

    @pytest.mark.asyncio
    async def test_clean_class_is_included(self) -> None:
        manager = GriptapeNodes.LibraryManager()
        library = self._make_library({"Clean": _CleanProbe})

        with patch(
            "griptape_nodes.retained_mode.managers.library_manager.LibraryRegistry.get_library",
            return_value=library,
        ):
            schemas = await manager._serialize_library_node_schemas("libA")

        assert [s.class_name for s in schemas] == ["Clean"]

    @pytest.mark.asyncio
    async def test_violating_class_is_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        caplog.set_level(logging.DEBUG, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        library = self._make_library({"Violator": _ViolatingProbe, "Clean": _CleanProbe})

        with patch(
            "griptape_nodes.retained_mode.managers.library_manager.LibraryRegistry.get_library",
            return_value=library,
        ):
            schemas = await manager._serialize_library_node_schemas("libA")

        # Violating class dropped from output.
        assert [s.class_name for s in schemas] == ["Clean"]

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("fixture probe violation" in r.getMessage() for r in errors)
        assert any("class=Violator" in r.getMessage() for r in errors)
