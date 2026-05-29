"""Tests for the v0.19.0 ExecutorCliExtraction workflow compatibility check."""

from unittest.mock import MagicMock

import pytest

from griptape_nodes.retained_mode.events.workflow_events import WorkflowStatus
from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_schema_version_problem import (
    WorkflowSchemaVersionProblem,
)
from griptape_nodes.version_compatibility.versions.v0_19_0.executor_cli_extraction import (
    ExecutorCliExtraction,
)


def _make_metadata(schema_version: str) -> MagicMock:
    metadata = MagicMock()
    metadata.schema_version = schema_version
    return metadata


class TestExecutorCliExtractionAppliesToWorkflow:
    """Tests for ExecutorCliExtraction.applies_to_workflow."""

    @pytest.fixture
    def check(self) -> ExecutorCliExtraction:
        return ExecutorCliExtraction()

    def test_applies_to_pre_0_19_workflow(self, check: ExecutorCliExtraction) -> None:
        assert check.applies_to_workflow(_make_metadata("0.18.0")) is True

    def test_applies_to_much_older_workflow(self, check: ExecutorCliExtraction) -> None:
        assert check.applies_to_workflow(_make_metadata("0.14.0")) is True

    def test_does_not_apply_to_0_19_0_workflow(self, check: ExecutorCliExtraction) -> None:
        # Boundary condition: exactly the migration version, no migration needed.
        assert check.applies_to_workflow(_make_metadata("0.19.0")) is False

    def test_does_not_apply_to_post_0_19_workflow(self, check: ExecutorCliExtraction) -> None:
        assert check.applies_to_workflow(_make_metadata("0.20.0")) is False

    def test_does_not_apply_to_unparsable_version(self, check: ExecutorCliExtraction) -> None:
        # Defensive default: treat unparsable as out-of-scope rather than crashing.
        assert check.applies_to_workflow(_make_metadata("not-a-semver")) is False


class TestExecutorCliExtractionCheckWorkflow:
    """Tests for ExecutorCliExtraction.check_workflow."""

    @pytest.fixture
    def check(self) -> ExecutorCliExtraction:
        return ExecutorCliExtraction()

    def test_emits_flawed_issue_for_pre_0_19_workflow(self, check: ExecutorCliExtraction) -> None:
        issues = check.check_workflow(_make_metadata("0.18.0"))

        assert len(issues) == 1
        assert issues[0].severity == WorkflowStatus.FLAWED
        assert isinstance(issues[0].problem, WorkflowSchemaVersionProblem)

    def test_problem_description_references_schema_version(self, check: ExecutorCliExtraction) -> None:
        issues = check.check_workflow(_make_metadata("0.17.0"))

        assert len(issues) == 1
        problem = issues[0].problem
        assert isinstance(problem, WorkflowSchemaVersionProblem)
        assert "0.17.0" in problem.description
        assert "0.19.0" in problem.description

    def test_no_issues_for_current_schema_version(self, check: ExecutorCliExtraction) -> None:
        issues = check.check_workflow(_make_metadata("0.19.0"))

        assert issues == []

    def test_no_issues_for_post_0_19_workflow(self, check: ExecutorCliExtraction) -> None:
        issues = check.check_workflow(_make_metadata("0.20.0"))

        assert issues == []

    def test_no_issues_for_unparsable_version(self, check: ExecutorCliExtraction) -> None:
        # Mirrors applies_to_workflow's defensive default — no issues, no crash.
        issues = check.check_workflow(_make_metadata("not-a-semver"))

        assert issues == []
