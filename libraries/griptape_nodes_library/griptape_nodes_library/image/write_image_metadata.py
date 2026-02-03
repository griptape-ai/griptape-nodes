from typing import Any

from griptape.artifacts import ImageUrlArtifact
from PIL import Image

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.file_utils import generate_filename
from griptape_nodes_library.utils.image_utils import load_pil_image_from_artifact

# Image format to file extension mapping
IMAGE_FORMAT_TO_EXTENSION = {
    "PNG": "png",
    "JPG": "jpg",
    "JPEG": "jpg",
    "TIFF": "tiff",
    "MPO": "mpo",
    "WEBP": "webp",
}


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

    def process(self) -> None:
        """Process the image metadata write operation."""
        # Reset execution state
        self._clear_execution_status()

        try:
            # Validate inputs
            image, metadata_dict = self._validate_inputs()

            # Validate metadata keys
            self._validate_metadata_keys(metadata_dict)

            # Load PIL image
            pil_image = load_pil_image_from_artifact(image, self.name)

            # Write metadata
            image_bytes = self._write_metadata_to_image(pil_image, metadata_dict)

            # Save to storage
            output_artifact = self._save_image_to_storage(image_bytes, pil_image)

            # Success
            self.parameter_output_values["output_image"] = output_artifact
            success_msg = f"Successfully wrote {len(metadata_dict)} metadata entries to {pil_image.format} image"
            self._set_status_results(was_successful=True, result_details=success_msg)
            logger.info(f"{self.name}: {success_msg}")
        except (TypeError, ValueError) as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(e)

    def _validate_inputs(self) -> tuple[Any, dict]:
        """Validate image and metadata inputs.

        Returns:
            Tuple of (image, metadata_dict) if valid

        Raises:
            ValueError: If inputs are invalid
            TypeError: If metadata is not a dict
        """
        # Validate image input
        image = self.get_parameter_value("input_image")
        if not image:
            error_msg = f"{self.name}: No input image provided"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        # Validate metadata input
        metadata_dict = self.get_parameter_value("metadata")
        if not metadata_dict:
            error_msg = f"{self.name}: No metadata provided"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        if not isinstance(metadata_dict, dict):
            error_msg = f"{self.name}: Metadata must be dict, got {type(metadata_dict).__name__}"
            logger.warning(error_msg)
            raise TypeError(error_msg)

        return (image, metadata_dict)

    def _validate_metadata_keys(self, metadata_dict: dict) -> None:
        """Validate metadata keys don't use reserved namespace.

        Args:
            metadata_dict: Metadata dictionary to validate

        Raises:
            ValueError: If metadata contains reserved 'gtn_' prefix keys
        """
        reserved_keys = [key for key in metadata_dict if str(key).startswith("gtn_")]
        if reserved_keys:
            error_msg = (
                f"{self.name}: Cannot write metadata keys starting with 'gtn_' "
                f"(reserved for auto-injected workflow metadata). "
                f"Offending keys: {', '.join(reserved_keys)}"
            )
            logger.warning(error_msg)
            raise ValueError(error_msg)

    def _write_metadata_to_image(self, pil_image: Image.Image, metadata_dict: dict) -> bytes:
        """Write metadata to image using appropriate driver.

        Args:
            pil_image: PIL Image to write metadata to
            metadata_dict: Metadata to write

        Returns:
            Image bytes with metadata

        Raises:
            ValueError: If image format cannot be detected or is unsupported
            Exception: If metadata injection fails
        """
        # Check format is available
        if not pil_image.format:
            error_msg = f"{self.name}: Could not detect image format"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        # Get driver for this format
        driver = ImageMetadataDriverRegistry.get_driver_for_format(pil_image.format)
        if driver is None:
            error_msg = f"{self.name}: Unsupported format '{pil_image.format}'. Supported formats: PNG, JPEG, TIFF, MPO"
            logger.warning(error_msg)
            raise ValueError(error_msg)

        # Write metadata using driver
        try:
            return driver.inject_metadata(pil_image, metadata_dict)
        except Exception as e:
            error_msg = f"{self.name}: Failed to write metadata: {e}"
            logger.warning(error_msg)
            raise

    def _save_image_to_storage(self, image_bytes: bytes, pil_image: Image.Image) -> ImageUrlArtifact:
        """Save image bytes to static storage.

        Args:
            image_bytes: Image data to save
            pil_image: PIL Image (for format detection)

        Returns:
            ImageUrlArtifact with saved URL

        Raises:
            Exception: If save operation fails
        """
        try:
            # Use format if available, otherwise default to png
            image_format = pil_image.format if pil_image.format else "PNG"
            extension = IMAGE_FORMAT_TO_EXTENSION.get(image_format, "png")
            filename = generate_filename(self.name, suffix="_with_metadata", extension=extension)
            static_files_manager = GriptapeNodes.StaticFilesManager()

            # Skip metadata injection since image bytes already contain the metadata we just wrote.
            # This prevents circular injection of workflow metadata on top of user-specified metadata.
            saved_url = static_files_manager.save_static_file(
                image_bytes, filename, skip_metadata_injection=True, use_direct_save=True
            )

            return ImageUrlArtifact(value=saved_url, name=filename)
        except Exception as e:
            error_msg = f"{self.name}: Failed to save image: {e}"
            logger.warning(error_msg)
            raise
