"""Probe-level tests for strict-mode routing in _serialize_library_node_schemas.

Uses a fixture probe detector that calls ``STRICT_MODE.report`` from inside a
node class's ``__init__``. The scope wrapper on the probe loop is then
responsible for excluding violating classes from the returned schema list.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.strict_mode import STRICT_MODE
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
        STRICT_MODE.report(
            rule_id="fixture-probe-rule",
            message="fixture probe violation",
        )


class TestSerializeSchemasStrictMode:
    def _make_library(self, nodes: dict[str, type]) -> MagicMock:
        lib = MagicMock()
        lib.get_registered_nodes.return_value = list(nodes.keys())
        lib.get_node_class.side_effect = lambda name: nodes[name]
        return lib

    def _patch_registry(self, library: MagicMock, nodes: dict[str, type]) -> Any:
        def _create_node(*, node_type: str, name: str, specific_library_name: str | None = None) -> Any:  # noqa: ARG001
            return nodes[node_type](name)

        return patch.multiple(
            "griptape_nodes.retained_mode.managers.library_manager.LibraryRegistry",
            get_library=MagicMock(return_value=library),
            create_node=MagicMock(side_effect=_create_node),
        )

    @pytest.mark.asyncio
    async def test_clean_class_is_included(self) -> None:
        manager = GriptapeNodes.LibraryManager()
        nodes = {"Clean": _CleanProbe}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        assert [s.class_name for s in schemas] == ["Clean"]

    @pytest.mark.asyncio
    async def test_violating_class_is_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        caplog.set_level(logging.DEBUG, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"Violator": _ViolatingProbe, "Clean": _CleanProbe}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        # Violating class dropped from output.
        assert [s.class_name for s in schemas] == ["Clean"]

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("fixture probe violation" in r.getMessage() for r in errors)
        assert any("class=Violator" in r.getMessage() for r in errors)


class _ParamWithConverters:
    """Minimal shim that quacks like a Parameter for the behavior detector."""

    def __init__(
        self,
        *,
        name: str,
        converters: list | None = None,
        validators: list | None = None,
        traits: list | None = None,
    ) -> None:
        self.name = name
        self._type = "str"
        self._input_types: list[str] = []
        self._output_type = ""
        self.default_value = None
        self.tooltip = ""
        self.tooltip_as_input = ""
        self.tooltip_as_property = ""
        self.tooltip_as_output = ""
        self.allowed_modes = set()
        self.user_defined = False
        self.settable = True
        self.serializable = True
        self.private = False
        self.ui_options = None
        self._converters = list(converters or [])
        self._validators = list(validators or [])
        self._traits = list(traits or [])

    def find_elements_by_type(self, _type: type) -> list:
        return list(self._traits)


class _ProbeWithBehaviorParam:
    """Node class whose probe exposes a Parameter with converters attached."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [
            _ParamWithConverters(name="p_with_converter", converters=[lambda v: v]),
        ]


class _ProbeWithCleanParams:
    """Node class whose probe parameters have no converters/validators/traits."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [_ParamWithConverters(name="p_clean")]


class TestParameterBehaviorsDropped:
    """#4472: Parameters carrying converters/validators/traits emit a warn violation."""

    def _make_library(self, nodes: dict[str, type]) -> MagicMock:
        lib = MagicMock()
        lib.get_registered_nodes.return_value = list(nodes.keys())
        lib.get_node_class.side_effect = lambda name: nodes[name]
        return lib

    def _patch_registry(self, library: MagicMock, nodes: dict[str, type]) -> Any:
        def _create_node(*, node_type: str, name: str, specific_library_name: str | None = None) -> Any:  # noqa: ARG001
            return nodes[node_type](name)

        return patch.multiple(
            "griptape_nodes.retained_mode.managers.library_manager.LibraryRegistry",
            get_library=MagicMock(return_value=library),
            create_node=MagicMock(side_effect=_create_node),
        )

    @pytest.mark.asyncio
    async def test_clean_parameters_produce_no_violation(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        caplog.set_level(logging.WARNING, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"Clean": _ProbeWithCleanParams}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        assert [s.class_name for s in schemas] == ["Clean"]
        assert not any("p_clean" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_parameter_with_converter_reports_warning_but_keeps_schema(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        caplog.set_level(logging.WARNING, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"WithBehavior": _ProbeWithBehaviorParam}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        # Warning, not error: the class still yields a schema.
        assert [s.class_name for s in schemas] == ["WithBehavior"]

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("p_with_converter" in r.getMessage() for r in warnings)
        assert any("converters" in r.getMessage() for r in warnings)
        assert any("class=WithBehavior" in r.getMessage() for r in warnings)
