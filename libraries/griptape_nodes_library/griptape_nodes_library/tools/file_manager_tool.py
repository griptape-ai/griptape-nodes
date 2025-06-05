from griptape.drivers.file_manager.local import LocalFileManagerDriver
from griptape.tools import FileManagerTool as GtFileManagerTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tools.base_tool import BaseTool

LOCATIONS = ["Local", "GriptapeCloud"]


class FileManager(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.update_tool_info(
            value="The FileManager tool can be given to an agent to help it perform file operations.",
            title="FileManager Tool",
        )

        self.add_parameter(
            Parameter(
                name="file_location",
                type="str",
                tooltip="The location of the files to be used by the tool.",
                default_value=LOCATIONS[0],
                traits={Options(choices=LOCATIONS)},
            )
        )
        self.swap_parameters("file_location", "tool")
        self.hide_parameter_by_name("off_prompt")

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)
        file_location = self.parameter_values.get("file_location")

        # Get the setting for Workspace Directory
        workdir = GriptapeNodes.ConfigManager().get_config_value("workspace_directory")

        # gtc_driver = GriptapeCloudFileManagerDriver()
        local_driver = LocalFileManagerDriver(workdir=workdir)
        # Create the tool
        tool = GtFileManagerTool(file_manager_driver=local_driver, off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
