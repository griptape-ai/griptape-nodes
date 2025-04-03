from griptape_nodes_library.dyna_node import DynaNode


class TestDynaNode:
    def test_dyna_node(self) -> None:
        node = DynaNode(
            name="test_node",
            metadata={
                "library_node_metadata": {
                    "module": "griptape.tasks.prompt_task",
                    "class": "PromptTask",
                    "method": "run",
                }
            },
        )

        assert len(node.parameters) == 23
