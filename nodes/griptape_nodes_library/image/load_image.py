import shutil
from pathlib import Path
from typing import Any

from griptape.artifacts import ImageUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode


class LoadImage(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Image"
        self.description = "Load an image"

        self.add_parameter(
            Parameter(
                name="file_path",
                input_types=["str"],
                type="str",
                output_type="str",
                tooltip="The file path to the image.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "BlobArtifact", "ImageUrlArtifact"],
                type="ImageUrlArtifact",
                output_type="ImageArtifact",
                ui_options={"clickable_file_browser": True, "expander": True},
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                tooltip="The image that has been generated.",
            )
        )

    def copy_to_static_file(self, orig_file_path: str) -> str:
        # Copy the file to a static location
        from griptape_nodes.app.app import STATIC_SERVER_HOST, STATIC_SERVER_PORT, STATIC_SERVER_URL

        # filename
        filename = Path(orig_file_path).name
        output_path = ""
        try:
            output_path = Path(
                self.config_manager.workspace_path / self.config_manager.user_config["static_files_directory"]
            )
            if not output_path.exists():
                output_path.mkdir(parents=True, exist_ok=True)

            # Copy the file to the static directory
            output_path = output_path / Path(orig_file_path).name
            shutil.copy(orig_file_path, output_path)
            # Return the url to the file
            static_url = f"http://{STATIC_SERVER_HOST}:{STATIC_SERVER_PORT}{STATIC_SERVER_URL}/{filename}"
        except Exception as e:
            msg = f"Failed to save file {orig_file_path} to {output_path}"
            raise RuntimeError(msg) from e

        return static_url

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        if parameter.name == "file_path" and value.strip() is not None:
            # If the file_path is set, we're going to update the image parameter to be
            # the url

            # Move the image to the static directory
            static_url = self.copy_to_static_file(value)
            # Set the image parameter to be the url
            self.parameter_values["image"] = ImageUrlArtifact(value=static_url)

        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        image = self.parameter_values["image"]

        # if isinstance(image, ImageUrlArtifact):
        #     image_artifact = ImageLoader().parse(image.to_bytes())
        # else:
        #     # Convert to ImageArtifact
        #     image_artifact = dict_to_image_artifact(image)

        self.parameter_output_values["image"] = image
