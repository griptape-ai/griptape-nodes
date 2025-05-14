from griptape.drivers.file_manager.local_file_manager_driver import LocalFileManagerDriver
from griptape.tools import FileManagerTool as GtFileManagerTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.tools.base_tool import BaseTool


class FileManager(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="workdir",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="The working directory for the file manager.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)
        workdir = self.parameter_values.get("workdir", "")

        # Create the tool
        tool = GtFileManagerTool(file_manager_driver=LocalFileManagerDriver(workdir=workdir), off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
