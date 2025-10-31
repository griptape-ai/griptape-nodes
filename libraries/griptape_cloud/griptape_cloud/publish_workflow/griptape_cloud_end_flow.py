from typing import Any

from griptape_nodes.exe_types.node_types import EndNode


class GriptapeCloudEndFlow(EndNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        if metadata is None:
            metadata = {}
        metadata["showaddparameter"] = True
        super().__init__(name, metadata)

    def process(self) -> None:
        super().process()

    @classmethod
    def get_default_node_parameter_names(cls) -> list[str]:
        """Get the names of the parameters configured on the node by default."""
        # Execution Status Component parameters
        params = ["was_successful", "result_details"]
        # Control parameters
        params.extend(["exec_in", "failed"])
        # Default node parameters
        params.extend(["execution_environment"])
        return params
