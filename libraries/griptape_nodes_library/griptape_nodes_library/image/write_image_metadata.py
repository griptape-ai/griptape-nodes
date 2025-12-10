from io import BytesIO
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import load_pil_from_url


class WriteImageMetadataNode(SuccessFailureNode):
    """Write custom key-value metadata to images.

    Supports PNG (text chunks), JPEG/TIFF/MPO (EXIF UserComment field).
    Format is automatically detected and appropriate metadata mechanism is used.
    Preserves existing metadata and merges with new values.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add input image parameter
        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact", "str"],
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.INPUT},
                tooltip="Source image to write metadata to",
            )
        )

        # Add output image parameter
        self.add_parameter(
            Parameter(
                name="output_image",
                output_type="ImageUrlArtifact",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Image with metadata written",
            )
        )

        # Add metadata input parameter
        self.add_parameter(
            Parameter(
                name="metadata",
                input_types=["dict"],
                type="dict",
                default_value={},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Dictionary of key-value pairs to write as metadata",
            )
        )

        # Add status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the metadata write operation result",
            result_details_placeholder="Details on the write operation will be presented here.",
        )

    def process(self) -> None:  # noqa: C901, PLR0911, PLR0915
        # Reset execution state
        self._clear_execution_status()

        # Validate image input
        image = self.get_parameter_value("input_image")
        if not image:
            error_msg = f"{self.name}: No input image provided"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
            return

        # Validate metadata input
        metadata_dict = self.get_parameter_value("metadata")
        if not metadata_dict:
            error_msg = f"{self.name}: No metadata provided"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
            return

        if not isinstance(metadata_dict, dict):
            error_msg = f"{self.name}: Metadata must be dict, got {type(metadata_dict).__name__}"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(TypeError(error_msg))
            return

        # Check for reserved gtn_* namespace
        reserved_keys = [key for key in metadata_dict if str(key).startswith("gtn_")]
        if reserved_keys:
            error_msg = (
                f"{self.name}: Cannot write metadata keys starting with 'gtn_' "
                f"(reserved for auto-injected workflow metadata). "
                f"Offending keys: {', '.join(reserved_keys)}"
            )
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
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
                raise TypeError(error_msg)  # noqa: TRY301
        except Exception as e:
            error_msg = f"{self.name}: Failed to load image: {e}"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(e)
            return

        # Get driver for this format
        driver = ImageMetadataDriverRegistry.get_driver_for_format(pil_image.format)
        if driver is None:
            error_msg = f"{self.name}: Unsupported format '{pil_image.format}'. Supported formats: PNG, JPEG, TIFF, MPO"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(error_msg))
            return

        # Write metadata using driver
        try:
            image_bytes = driver.inject_metadata(pil_image, metadata_dict)
        except Exception as e:
            error_msg = f"{self.name}: Failed to write metadata: {e}"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(e)
            return

        # Save output image to static storage
        try:
            # Determine file extension based on format
            format_to_extension = {
                "PNG": "png",
                "JPEG": "jpg",
                "TIFF": "tiff",
                "MPO": "mpo",
            }
            extension = format_to_extension.get(pil_image.format, "png")

            filename = generate_filename(self.name, suffix="_with_metadata", extension=extension)
            static_files_manager = GriptapeNodes.StaticFilesManager()
            saved_url = static_files_manager.save_static_file(image_bytes, filename, skip_metadata_injection=True)

            output_artifact = ImageUrlArtifact(value=saved_url, name=filename)
            self.parameter_output_values["output_image"] = output_artifact
        except Exception as e:
            error_msg = f"{self.name}: Failed to save image: {e}"
            logger.warning(error_msg)
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(e)
            return

        # Success
        success_msg = f"Successfully wrote {len(metadata_dict)} metadata entries to {pil_image.format} image"
        self._set_status_results(was_successful=True, result_details=success_msg)
        logger.info(f"{self.name}: {success_msg}")
