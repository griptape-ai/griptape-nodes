from pathlib import Path
from typing import Any

from griptape.artifacts import ImageArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button
from nodes.griptape_nodes_library.utils.image_utils import dict_to_image_artifact

DEFAULT_FILENAME = "griptape_nodes.png"


def to_image_artifact(image: ImageArtifact | dict) -> ImageArtifact:
    if isinstance(image, dict):
        return dict_to_image_artifact(image)
    return image


class SaveImage(ControlNode):
    """Save an image to a file."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add image input parameter
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "dict"],
                type="ImageArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="The image to save to file",
            )
        )

        # Add output path parameter
        self.add_parameter(
            Parameter(
                name="output_path",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=DEFAULT_FILENAME,
                tooltip="The output filename with extension (.png, .jpg, etc.)",
                traits={Button(button_type="save")},
            )
        )

    def process(self) -> None:
        config_manager = GriptapeNodes.ConfigManager()
        workspace_path = Path(config_manager.workspace_path)

        image = self.parameter_values.get("image")

        if not image:
            logger.info("No image provided to save")
            return

        output_file = self.parameter_values.get("output_path", DEFAULT_FILENAME)

        # Set output values BEFORE transforming to workspace-relative
        self.parameter_output_values["output_path"] = output_file

        full_output_file = str(workspace_path / output_file)

        try:
            image_artifact = to_image_artifact(image)

            # Use ImageLoader to save the image
            loader = ImageLoader()
            loader.save(full_output_file, image_artifact)

            success_msg = f"Saved image: {full_output_file}"
            logger.info(success_msg)

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving image: {error_message}"
            raise ValueError(msg) from e
