from griptape.tools import FileManagerTool as GtFileManagerTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.tools.base_tool import BaseTool


class FileManager(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="workdir",
                type="str",
                default_value=".",
                tooltip="The working directory for the file manager.",
            )
        )

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # TODO(jason): Get the workspace directory better after https://github.com/griptape-ai/griptape-nodes/issues/1109
        workdir = GriptapeNodes.ConfigManager().get_config_value("workspace_directory")  # noqa: F841
        # Create the tool
        tool = GtFileManagerTool(
            off_prompt=off_prompt,
            # TODO(jason): Add support for file manager driver https://github.com/griptape-ai/griptape-nodes/issues/1106
            # file_manager_driver=LocalFileManagerDriver(workdir=workdir),  # noqa: ERA001
        )

        # Set the output
        self.parameter_output_values["tool"] = tool.to_dict()
