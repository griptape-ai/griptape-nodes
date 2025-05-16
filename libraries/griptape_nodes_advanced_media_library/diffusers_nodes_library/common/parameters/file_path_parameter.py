from pathlib import Path

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode


class FilePathParameter:
    def __init__(self, node: BaseNode, parameter_name: str = "file_path"):
        self._node = node
        self._parameter_name = parameter_name

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                input_types=["str"],
                type="str",
                tooltip="prompt",
            )
        )

    def get_file_path(self) -> Path:
        return Path(self._node.get_parameter_value(self._parameter_name))

    def validate_parameter_values(self) -> None:
        file_path = self.get_file_path()
        if not file_path.exists():
            msg = f"No file at {file_path} exists"
            raise RuntimeError(msg)
