"""The node bookkeeping a workflow keeps: which flow each node is in."""

import pytest

from griptape_nodes.retained_mode.runtime.nodes import WorkflowNodes


class TestWorkflowNodes:
    def test_parent_flow_name_of_a_known_node(self) -> None:
        nodes = WorkflowNodes()
        nodes.name_to_parent_flow_name["node"] = "flow"

        assert nodes.parent_flow_name("node") == "flow"

    def test_parent_flow_name_of_an_unknown_node_names_the_node(self) -> None:
        with pytest.raises(KeyError, match="ghost"):
            WorkflowNodes().parent_flow_name("ghost")

    def test_rename_node_keeps_its_flow(self) -> None:
        nodes = WorkflowNodes()
        nodes.name_to_parent_flow_name["old"] = "flow"

        nodes.rename_node("old", "new")

        assert nodes.name_to_parent_flow_name == {"new": "flow"}

    def test_rename_flow_moves_only_its_nodes(self) -> None:
        nodes = WorkflowNodes()
        nodes.name_to_parent_flow_name.update({"a": "old_flow", "b": "other_flow"})

        nodes.rename_flow("old_flow", "new_flow")

        assert nodes.name_to_parent_flow_name == {"a": "new_flow", "b": "other_flow"}
