import json
from io import BytesIO
from typing import Any

from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.image_utils import load_pil_from_url

# EXIF tag IDs
EXIF_USERCOMMENT_TAG = 0x9286
EXIF_GPSINFO_TAG = 0x8825  # 34853

# GPS coordinate tuple length
GPS_COORD_TUPLE_LENGTH = 3


class ReadImageMetadataNode(SuccessFailureNode):
    """Read custom metadata from images.

    Supports reading EXIF metadata from JPEG/TIFF/MPO and PNG text chunks from PNG.
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

    def _read_and_populate_metadata(self, image: Any) -> None:  # noqa: C901, PLR0912
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

        # Read metadata based on format
        try:
            if image_format in ["JPEG", "TIFF", "MPO"]:
                metadata = self._read_exif_metadata(pil_image)
            elif image_format == "PNG":
                metadata = self._read_png_metadata(pil_image)
            else:
                # Format doesn't support metadata, return empty dict
                metadata = {}
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

    def _exif_value_to_string(self, value: Any) -> str:
        """Convert EXIF value to readable string format.

        Args:
            value: EXIF value (can be bytes, tuple, list, int, etc.)

        Returns:
            String representation of the value
        """
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="ignore").strip("\x00")
            except Exception:
                return str(value)
        elif isinstance(value, (tuple, list)):
            return ", ".join(str(v) for v in value)
        return str(value)

    def _format_gps_coordinate(self, coord_tuple: tuple) -> str:
        """Format GPS coordinate tuple to decimal degrees string.

        Args:
            coord_tuple: Tuple of (degrees, minutes, seconds) as rational numbers

        Returns:
            Decimal degrees as string
        """
        if not coord_tuple or len(coord_tuple) != GPS_COORD_TUPLE_LENGTH:
            return str(coord_tuple)

        try:
            degrees = float(coord_tuple[0])
            minutes = float(coord_tuple[1])
            seconds = float(coord_tuple[2])

            decimal_degrees = degrees + (minutes / 60.0) + (seconds / 3600.0)
        except Exception:
            return self._exif_value_to_string(coord_tuple)
        else:
            return f"{decimal_degrees:.6f}"

    def _read_exif_metadata(self, pil_image: Image.Image) -> dict[str, str]:
        """Read all EXIF metadata including standard tags and custom UserComment.

        Args:
            pil_image: PIL Image to read metadata from

        Returns:
            Dictionary of metadata key-value pairs, or empty dict if none found
        """
        exif_data = pil_image.getexif()
        if not exif_data:
            return {}

        metadata = {}

        # Read all EXIF tags
        for tag_id, value in exif_data.items():
            # Get tag name
            tag_name = TAGS.get(tag_id, f"Tag_{tag_id}")

            # Skip UserComment and GPSInfo, we'll handle them separately
            if tag_id in (EXIF_USERCOMMENT_TAG, EXIF_GPSINFO_TAG):
                continue

            # Convert value to string
            metadata[tag_name] = self._exif_value_to_string(value)

        # Read GPS metadata (if present)
        self._extract_gps_metadata(exif_data, metadata)

        # Read custom UserComment metadata (if present)
        self._extract_custom_metadata(exif_data, metadata)

        return metadata

    def _extract_gps_metadata(self, exif_data: Any, metadata: dict[str, str]) -> None:
        """Extract GPS metadata from EXIF data.

        Args:
            exif_data: EXIF data object
            metadata: Dictionary to populate with GPS metadata
        """
        gps_ifd = exif_data.get_ifd(EXIF_GPSINFO_TAG)
        if not gps_ifd:
            return

        for gps_tag_id, gps_value in gps_ifd.items():
            gps_tag_name = GPSTAGS.get(gps_tag_id, f"GPSTag_{gps_tag_id}")

            # Format GPS coordinate values specially
            if gps_tag_id in (1, 2, 3, 4):  # GPSLatitudeRef, GPSLatitude, GPSLongitudeRef, GPSLongitude
                if gps_tag_id in (2, 4):  # Latitude or Longitude tuple
                    metadata[f"GPS_{gps_tag_name}"] = self._format_gps_coordinate(gps_value)
                else:
                    metadata[f"GPS_{gps_tag_name}"] = str(gps_value)
            else:
                metadata[f"GPS_{gps_tag_name}"] = self._exif_value_to_string(gps_value)

    def _extract_custom_metadata(self, exif_data: Any, metadata: dict[str, str]) -> None:
        """Extract custom metadata from EXIF UserComment.

        Args:
            exif_data: EXIF data object
            metadata: Dictionary to populate with custom metadata
        """
        user_comment = exif_data.get(EXIF_USERCOMMENT_TAG)
        if not user_comment:
            return

        try:
            # Pillow handles the character code prefix, but might return bytes or string
            if isinstance(user_comment, bytes):
                comment_str = user_comment.decode("utf-8", errors="ignore").strip("\x00")
            else:
                comment_str = str(user_comment)

            custom_metadata = json.loads(comment_str)
            if isinstance(custom_metadata, dict):
                # Merge custom metadata (prefix with "Custom_" to avoid conflicts)
                for key, value in custom_metadata.items():
                    metadata[f"Custom_{key}"] = str(value)
        except Exception:  # noqa: S110
            pass

    def _read_png_metadata(self, pil_image: Image.Image) -> dict[str, str]:
        """Read metadata from PNG text chunks.

        Args:
            pil_image: PIL Image to read metadata from

        Returns:
            Dictionary of metadata key-value pairs, or empty dict if none found
        """
        # PIL unpacks PNG text chunks directly into pil_image.info
        # Extract only string metadata (skip binary data like icc_profile)
        metadata = {}

        for key, value in pil_image.info.items():
            # Only include string/simple values (PNG text chunks)
            if isinstance(value, str):
                metadata[key] = value
            elif isinstance(value, (int, float, bool)):
                metadata[key] = str(value)

        return metadata
