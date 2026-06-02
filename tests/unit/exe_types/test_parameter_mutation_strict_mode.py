"""Tests for the parameter-mutation-during-aprocess strict-mode detector.

The detector lives in ``BaseNode.add_parameter`` and
``BaseNode.remove_parameter_element``. It fires when a node mutates its
own parameter list while ``aprocess_scope()`` is active (set only around
``await node.aprocess()``) and the call is not wrapped by the handler-side
``sanctioned_parameter_mutation()`` context.
"""

from __future__ import annotations

import pytest

from griptape_nodes.common.strict_mode import STRICT_MODE, StrictModeScopeKind
from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import aprocess_scope, sanctioned_parameter_mutation
from griptape_nodes.node_library.library_registry import _constructing_node

from .mocks import MockNode


@pytest.fixture
def mock_node() -> MockNode:
    """Return a fresh MockNode for each test."""
    return MockNode(name="detector_test_node")


class TestParameterMutationDetector:
    def test_no_violation_when_no_scope_active(self, mock_node: MockNode) -> None:
        param = Parameter(name="p1", type="str")
        mock_node.add_parameter(param)
        # Outside a strict-mode scope nothing is tracked.
        # The add_parameter call should succeed without raising.

    def test_violation_reported_when_adding_parameter_inside_aprocess_scope(self, mock_node: MockNode) -> None:
        param = Parameter(name="p_added", type="str")
        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=False,
            ) as scope,
            aprocess_scope(),
        ):
            mock_node.add_parameter(param)
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "parameter-mutation-during-aprocess"
        assert "p_added" in violation.message
        assert "add_parameter" in violation.message

    def test_violation_reported_when_removing_parameter_inside_aprocess_scope(self, mock_node: MockNode) -> None:
        param = Parameter(name="p_to_remove", type="str")
        mock_node.add_parameter(param)
        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=False,
            ) as scope,
            aprocess_scope(),
        ):
            mock_node.remove_parameter_element(param)
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.rule_id == "parameter-mutation-during-aprocess"
        assert "p_to_remove" in violation.message
        assert "remove_parameter_element" in violation.message

    def test_no_violation_when_handler_sanctions_add(self, mock_node: MockNode) -> None:
        param = Parameter(name="sanctioned_add", type="str")
        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=False,
            ) as scope,
            aprocess_scope(),
            sanctioned_parameter_mutation(),
        ):
            mock_node.add_parameter(param)
        assert scope.violations == []

    def test_no_violation_when_handler_sanctions_remove(self, mock_node: MockNode) -> None:
        param = Parameter(name="sanctioned_remove", type="str")
        mock_node.add_parameter(param)
        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=False,
            ) as scope,
            aprocess_scope(),
            sanctioned_parameter_mutation(),
        ):
            mock_node.remove_parameter_element(param)
        assert scope.violations == []

    def test_worker_scope_escalates_to_error_severity(self, mock_node: MockNode) -> None:
        param = Parameter(name="worker_add", type="str")
        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=True,
            ) as scope,
            aprocess_scope(),
        ):
            mock_node.add_parameter(param)
        assert len(scope.violations) == 1
        violation = scope.violations[0]
        assert violation.severity.value == "error"

    def test_no_violation_during_hydration_under_runtime_execute(self, mock_node: MockNode) -> None:
        """Hydration runs add_parameter under RUNTIME_EXECUTE without aprocess.

        ``_hydrate_and_run_node_inner`` calls ``set_parameter_value``
        (firing ``before_value_set`` / ``after_value_set``) inside the
        ``RUNTIME_EXECUTE`` scope but before ``await node.aprocess()``.
        Real nodes (e.g. dynamic-pipeline diffuser nodes) call
        ``add_parameter`` from those hooks. The detector must stay silent
        until the framework enters ``aprocess_scope()``.
        """
        param = Parameter(name="hydration_added", type="str")
        with STRICT_MODE.open_scope(
            kind=StrictModeScopeKind.RUNTIME_EXECUTE,
            subject=mock_node.name,
            library_name=None,
            is_worker=True,
        ) as scope:
            mock_node.add_parameter(param)
        assert scope.violations == []

    def test_no_violation_when_add_parameter_called_from_init_under_load_probe(self) -> None:
        """__init__ calls to add_parameter during a LOAD_PROBE scope are not violations.

        LibraryManager._serialize_library_node_schemas instantiates every node
        class inside a LOAD_PROBE scope. Nodes legitimately declare their
        parameters by calling self.add_parameter(...) from __init__, so those
        calls must not report parameter-mutation-during-aprocess. The
        constructor flag suppresses the rule in this case; the
        ``_in_aprocess`` flag is also unset because no aprocess is running.
        """

        class NodeAddsParameterInInit(MockNode):
            def __init__(self, name: str = "probe_node") -> None:
                super().__init__(name=name)
                self.add_parameter(Parameter(name="declared_in_init", type="str"))

        token = _constructing_node.set(True)
        try:
            with STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.LOAD_PROBE,
                subject="NodeAddsParameterInInit",
                library_name="test_library",
                is_worker=True,
            ) as scope:
                NodeAddsParameterInInit(name="__schema_probe__")
        finally:
            _constructing_node.reset(token)
        assert scope.violations == []

    def test_no_violation_for_nested_node_construction_inside_aprocess(self, mock_node: MockNode) -> None:
        """A node constructed inside aprocess can declare params in __init__.

        ``LibraryRegistry.create_node`` sets the is-constructing flag for the
        duration of the inner node's ``__init__``. The detector's constructor
        short-circuit must hold even when ``aprocess_scope()`` is active for
        the outer node, otherwise creating helper nodes from aprocess would
        spuriously trip the rule.
        """

        class InnerNodeWithParam(MockNode):
            def __init__(self, name: str = "inner") -> None:
                super().__init__(name=name)
                self.add_parameter(Parameter(name="inner_p", type="str"))

        with (
            STRICT_MODE.open_scope(
                kind=StrictModeScopeKind.RUNTIME_EXECUTE,
                subject=mock_node.name,
                library_name=None,
                is_worker=False,
            ) as scope,
            aprocess_scope(),
        ):
            token = _constructing_node.set(True)
            try:
                InnerNodeWithParam(name="constructed_during_aprocess")
            finally:
                _constructing_node.reset(token)
        assert scope.violations == []
