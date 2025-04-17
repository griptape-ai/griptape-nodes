from typing import Any, TypeVar

from griptape.artifacts import ImageArtifact
from griptape.loaders import ImageLoader

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.button import Button
from nodes.griptape_nodes_library.utils.image_utils import dict_to_image_artifact

T = TypeVar("T")


def _ensure_type(obj: Any, expected_type: type[T]) -> T:
    """Ensure object is of expected type, raising TypeError if not."""
    if not isinstance(obj, expected_type):
        actual_type = type(obj).__name__
        error_msg = f"Expected {expected_type.__name__} but got {actual_type}"
        raise TypeError(error_msg)
    return obj


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
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
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
                default_value="griptape_nodes.png",
                tooltip="The output filename with extension (.png, .jpg, etc.)",
                traits={Button(button_type="save")},
            )
        )

    def process(self) -> None:
        image = self.parameter_values.get("image")
        full_output_file = self.parameter_values.get("output_path", "griptape_output.png")

        if not image:
            logger.info("No image provided to save")
            return

        try:
            if isinstance(image, dict):
                image_artifact = dict_to_image_artifact(image)
            else:
                # Already an ImageArtifact
                image_artifact = image

            # Type check to ensure image_artifact is an ImageArtifact
            image_artifact = _ensure_type(image_artifact, ImageArtifact)

            # Use ImageLoader to save the image
            loader = ImageLoader()
            loader.save(full_output_file, image_artifact)

            success_msg = f"Saved image: {full_output_file}"
            logger.info(success_msg)

            # Set output values
            self.parameter_output_values["output_path"] = full_output_file

        except Exception as e:
            error_message = str(e)
            msg = f"Error saving image: {error_message}"
            raise ValueError(msg) from e
