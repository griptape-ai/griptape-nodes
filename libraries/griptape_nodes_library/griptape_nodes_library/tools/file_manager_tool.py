from typing import Any, cast

import httpx
from griptape.drivers.file_manager.griptape_cloud import GriptapeCloudFileManagerDriver
from griptape.drivers.file_manager.local import LocalFileManagerDriver
from griptape.tools import FileManagerTool as GtFileManagerTool

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.tools.base_tool import BaseTool

LOCATIONS = ["Workspace Directory", "GriptapeCloud"]

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
BASE_URL = "https://cloud.griptape.ai/api"


class FileManager(BaseTool):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        self.bucket_list = self.get_bucket_list()
        self.bucket_map = dict(self.bucket_list)
        self.workdir = GriptapeNodes.ConfigManager().get_config_value("workspace_directory")

        self.update_tool_info(
            value=f"""The FileManager tool can be given to an agent to help it perform file operations and uses your Workspace Directory by default.\n
({self.workdir}).""",
            title="FileManager Tool",
        )

        # TODO: (jason) Add back when GriptapeCloudFileManagerDriver is working https://github.com/griptape-ai/griptape-nodes/issues/1416
        self.add_parameter(
            Parameter(
                name="file_location",
                type="str",
                tooltip="The location of the files to be used by the tool.",
                default_value=LOCATIONS[0],
                traits={Options(choices=LOCATIONS)},
                ui_options={"hide": True},
            )
        )
        """
        self.add_parameter(
             Parameter(
                 name="bucket_id",
                 type="str",
                 tooltip="The location of the files to be used by the tool.",
                 default_value=self.bucket_list[0][0] if self.bucket_list else "",
                 traits={Options(choices=[name for name, _ in self.bucket_list])},
                 ui_options={"hide": True},
             )
         )
        self.swap_elements("tool", "bucket_id")
        """
        self.hide_parameter_by_name("off_prompt")

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "file_location":
            if value == LOCATIONS[1]:
                self.show_parameter_by_name("bucket_id")
            else:
                self.hide_parameter_by_name("bucket_id")

        return super().after_value_set(parameter, value)

    def get_bucket_list(self) -> list[tuple[str, str]]:
        """Get the list of buckets from Griptape Cloud API.

        Returns:
            list[tuple[str, str]]: List of tuples containing (bucket_name, bucket_id)
        """
        try:
            response = httpx.get(f"{BASE_URL}/buckets", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10)
            response.raise_for_status()
            data = response.json()
            return [(bucket["name"], bucket["bucket_id"]) for bucket in data["buckets"]]
        except httpx.HTTPStatusError as e:
            msg = f"Failed to fetch buckets from Griptape Cloud: {e}"
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Error fetching buckets: {e}"
            raise RuntimeError(msg) from e

    def process(self) -> None:
        off_prompt = self.parameter_values.get("off_prompt", True)
        file_location = cast("str", self.parameter_values.get("file_location"))

        if file_location == LOCATIONS[0]:
            # Get the setting for Workspace Directory
            workdir = GriptapeNodes.ConfigManager().get_config_value("workspace_directory")
            driver = LocalFileManagerDriver(workdir=workdir)
        elif file_location == LOCATIONS[1]:
            bucket_name = cast("str", self.parameter_values.get("bucket_id"))
            bucket_id = self.bucket_map.get(bucket_name)
            if not bucket_id:
                msg = f"Invalid bucket name: {bucket_name}"
                raise ValueError(msg)
            driver = GriptapeCloudFileManagerDriver(api_key=self.api_key, bucket_id=bucket_id)  # type: ignore[arg-type]
        else:
            msg = f"Invalid file location: {file_location}"
            raise ValueError(msg)

        # Create the tool
        tool = GtFileManagerTool(file_manager_driver=driver, off_prompt=off_prompt)

        # Set the output
        self.parameter_output_values["tool"] = tool
