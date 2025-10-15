from pathlib import Path

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.file_system_picker import FileSystemPicker


class FilePathParameter:
    def __init__(
        self,
        node: BaseNode,
        parameter_name: str = "file_path",
        file_types: list[str] | None = None,
        initial_path: str | None = None,
    ):
        self._node = node
        self._parameter_name = parameter_name
        self._file_types = file_types
        self._initial_path = initial_path or str(GriptapeNodes.ConfigManager().workspace_path)

    def add_input_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name=self._parameter_name,
                input_types=["str"],
                type="str",
                tooltip="Path to a local lora file",
                traits={
                    FileSystemPicker(
                        allow_files=True,
                        allow_directories=False,
                        multiple=False,
                        file_types=self._file_types,
                        initial_path=self._initial_path,
                    )
                },
            )
        )

    def get_file_path(self) -> Path:
        return Path(self._node.get_parameter_value(self._parameter_name))

    def validate_parameter_values(self) -> None:
        file_path = self.get_file_path()
        if not file_path.exists():
            msg = f"No file at {file_path} exists"
            raise RuntimeError(msg)
