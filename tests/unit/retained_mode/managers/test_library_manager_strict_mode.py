"""Probe-level tests for strict-mode routing in _serialize_library_node_schemas.

Uses a fixture probe detector that calls ``STRICT_MODE.report`` from inside a
node class's ``__init__``. The scope wrapper on the probe loop is then
responsible for excluding violating classes from the returned schema list.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.strict_mode import STRICT_MODE
from griptape_nodes.exe_types.core_types import Parameter, Trait
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class _CleanProbe:
    """Node class whose __init__ does nothing interesting."""

    parameters: list = []  # noqa: RUF012

    def __init__(self, name: str) -> None:
        self.name = name


class _ViolatingProbe:
    """Node class whose __init__ triggers a correctness-class violation.

    Uses ``unknown-payload-type`` because it is registered with
    ``correctness=True``; the LOAD_PROBE skip-on-correctness gate uses
    that flag to decide whether to drop the class from the schema.
    """

    parameters: list = []  # noqa: RUF012

    def __init__(self, name: str) -> None:
        self.name = name
        STRICT_MODE.report(
            rule_id="unknown-payload-type",
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


class _DummyTrait(Trait):
    """Minimal concrete Trait used to exercise the trait-detection path."""

    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["dummy"]


class _ProbeWithConverterParam:
    """Node class whose probe exposes a Parameter with a user-attached converter."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [
            Parameter(name="p_with_converter", converters=[lambda v: v]),
        ]


class _ProbeWithValidatorParam:
    """Node class whose probe exposes a Parameter with a user-attached validator."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [
            Parameter(name="p_with_validator", validators=[lambda _p, _v: None]),
        ]


class _ProbeWithTraitParam:
    """Node class whose probe exposes a Parameter with a real Trait child."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [
            Parameter(name="p_with_trait", traits={_DummyTrait()}),
        ]


class _ProbeWithCleanParams:
    """Node class whose probe parameter has no converters/validators/traits."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.parameters = [Parameter(name="p_clean")]


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
        caplog.set_level(logging.WARNING, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"WithBehavior": _ProbeWithConverterParam}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        # Warning, not error: the class still yields a schema.
        assert [s.class_name for s in schemas] == ["WithBehavior"]

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("p_with_converter" in r.getMessage() for r in warnings)
        assert any("converters" in r.getMessage() for r in warnings)
        assert any("class=WithBehavior" in r.getMessage() for r in warnings)

    @pytest.mark.asyncio
    async def test_parameter_with_validator_reports_warning_but_keeps_schema(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"WithValidator": _ProbeWithValidatorParam}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        assert [s.class_name for s in schemas] == ["WithValidator"]
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("p_with_validator" in r.getMessage() for r in warnings)
        assert any("validators" in r.getMessage() for r in warnings)

    @pytest.mark.asyncio
    async def test_parameter_with_trait_reports_warning_but_keeps_schema(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="griptape_nodes.strict_mode")
        manager = GriptapeNodes.LibraryManager()
        nodes = {"WithTrait": _ProbeWithTraitParam}
        library = self._make_library(nodes)

        with self._patch_registry(library, nodes):
            schemas = await manager._serialize_library_node_schemas("libA")

        assert [s.class_name for s in schemas] == ["WithTrait"]
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("p_with_trait" in r.getMessage() for r in warnings)
        assert any("traits" in r.getMessage() for r in warnings)
