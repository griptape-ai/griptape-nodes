from io import BytesIO
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.image_utils import load_pil_from_url


class ReadImageMetadataNode(SuccessFailureNode):
    """Read metadata from images.

    Supports reading all available metadata from JPEG/TIFF/MPO (EXIF) and PNG formats.
    Delegates to format-specific drivers for extraction.
    Outputs the metadata as a dictionary.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add image input parameter
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Image to read metadata from",
            )
        )

        # Add metadata output parameter
        self.add_parameter(
            Parameter(
                name="metadata",
                type="dict",
                output_type="dict",
                default_value={},
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Dictionary of all metadata key-value pairs",
            )
        )

        # Add status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the metadata read operation result",
            result_details_placeholder="Details on the read operation will be presented here.",
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Automatically process metadata when image parameter receives a value.

        Args:
            parameter: The parameter that was updated
            value: The new value for the parameter
        """
        if parameter.name == "image":
            self._read_and_populate_metadata(value)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the image metadata read operation.

        Gets the image parameter value and delegates to _read_and_populate_metadata().
        Handles failure exceptions for control flow routing.
        """
        # Reset execution state
        self._clear_execution_status()

        # Get image parameter value
        image = self.get_parameter_value("image")

        # Delegate to helper method
        self._read_and_populate_metadata(image)

        # Handle failure exception for control flow routing if operation failed
        if self._execution_succeeded is False:
            self._handle_failure_exception(ValueError("Failed to read image metadata"))

    def _read_and_populate_metadata(self, image: Any) -> None:
        """Read metadata from image and populate output parameter.

        This method is called both from process() and after_value_set() to enable
        automatic processing when the image parameter receives a value.

        Args:
            image: Image value (ImageUrlArtifact, ImageArtifact, str, or None)
        """
        # Clear metadata output first
        self.parameter_output_values["metadata"] = {}

        # Handle None/empty case - clear output and return
        if not image:
            self._set_status_results(was_successful=False, result_details="No image provided")
            return

        # Load PIL image
        try:
            if isinstance(image, ImageUrlArtifact):
                pil_image = load_pil_from_url(image.value)
            elif isinstance(image, ImageArtifact):
                pil_image = Image.open(BytesIO(image.value))
            elif isinstance(image, str):
                pil_image = load_pil_from_url(image)
            else:
                error_msg = f"{self.name}: Unsupported image type: {type(image).__name__}"
                logger.warning(error_msg)
                self._set_status_results(was_successful=False, result_details=error_msg)
                return
        except Exception as e:
            error_msg = f"{self.name}: Failed to load image: {e}"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            return

        # Detect format
        image_format = pil_image.format
        if not image_format:
            error_msg = f"{self.name}: Could not detect image format"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            return

        # Read metadata using driver
        driver = ImageMetadataDriverRegistry.get_driver_for_format(image_format)
        if driver is None:
            # Format doesn't support metadata, return empty dict
            metadata = {}
        else:
            try:
                metadata = driver.extract_metadata(pil_image)
            except Exception as e:
                error_msg = f"{self.name}: Failed to read metadata: {e}"
                logger.warning(error_msg)
                self._set_status_results(was_successful=False, result_details=error_msg)
                return

        # Success - set outputs
        self.parameter_output_values["metadata"] = metadata

        count = len(metadata)
        if count == 0:
            success_msg = "No metadata found in image"
        else:
            success_msg = f"Successfully read {count} metadata entries"

        self._set_status_results(was_successful=True, result_details=success_msg)
        logger.info(f"{self.name}: {success_msg}")
