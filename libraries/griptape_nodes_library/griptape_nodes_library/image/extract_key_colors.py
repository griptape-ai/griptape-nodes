import hashlib
import io
import logging

import numpy as np
from griptape.artifacts import ImageArtifact, ImageUrlArtifact
from PIL import Image
from sklearn.cluster import KMeans  # type: ignore[import-untyped]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.color_picker import ColorPicker
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider
from griptape_nodes_library.utils.image_utils import dict_to_image_url_artifact

logger = logging.getLogger(__name__)

__all__ = ["ExtractKeyColors"]

# Constants
DEBUG_ID_LENGTH = 50  # Maximum length for debug image IDs


class ExtractKeyColors(DataNode):
    """A node that extracts dominant colors from images using Pylette's KMeans algorithm.

    This node analyzes an input image and extracts the most prominent colors,
    creating dynamic color picker parameters for each extracted color. The colors
    are provided in both RGB and hexadecimal formats for easy use in design workflows.

    Features:
    - Supports ImageArtifact and ImageUrlArtifact inputs
    - Configurable number of colors to extract (2-12)
    - Dynamic color picker parameters for each extracted color
    - Pretty-printed color output for inspection
    - Automatic parameter cleanup between runs
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the ExtractKeyColors node with input parameters.

        Sets up the node with:
        - input_image: Parameter for the source image
        - num_colors: Parameter for the target number of colors to extract
        - number_of_color_params: Internal counter for dynamic parameters

        Args:
            **kwargs: Additional keyword arguments passed to the parent DataNode
        """
        super().__init__(**kwargs)

        self.number_of_color_params = 0  # Internal counter for dynamic parameters

        self.add_parameter(
            Parameter(
                name="input_image",
                tooltip="The image to extract key colors from",
                type="ImageUrlArtifact",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                ui_options={
                    "display_name": "Input Image",
                    "clickable_file_browser": True,
                    "file_browser_options": {
                        "extensions": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "ico", "webp"],
                        "allow_multiple": False,
                        "allow_directories": False,
                    },
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="num_colors",
                tooltip="Target number of colors to extract",
                type=ParameterTypeBuiltin.INT.value,
                traits={Slider(min_val=2, max_val=12)},
                default_value=3,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Target Number of Colors"},
            )
        )

        self.add_parameter(
            Parameter(
                name="algorithm",
                tooltip="Algorithm to use for color extraction",
                type=ParameterTypeBuiltin.STR.value,
                default_value="kmeans",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["kmeans", "median_cut"])},
                ui_options={
                    "display_name": "Algorithm",
                },
            )
        )

    def _image_to_bytes(self, image_artifact: ImageArtifact | ImageUrlArtifact | dict) -> bytes:
        """Convert ImageArtifact, ImageUrlArtifact, or dict representation to bytes.

        Args:
            image_artifact: ImageArtifact, ImageUrlArtifact, or dict representation

        Returns:
            Image data as bytes

        Raises:
            ValueError: If image artifact is invalid or unsupported
        """
        if not image_artifact:
            msg = "No input image provided"
            raise ValueError(msg)

        try:
            # Handle dictionary format (serialized artifacts)
            if isinstance(image_artifact, dict):
                # Convert dict to ImageUrlArtifact first
                image_url_artifact = dict_to_image_url_artifact(image_artifact)
                return image_url_artifact.to_bytes()
            # Handle artifact objects directly
            if isinstance(image_artifact, (ImageArtifact, ImageUrlArtifact)):
                return image_artifact.to_bytes()
            # Try to convert to bytes if it's a different artifact type
            return image_artifact.to_bytes()

        except Exception as e:
            msg = f"Failed to extract image data: {e!s}"
            raise ValueError(msg) from e

    def _find_largest_bucket(self, buckets: list[np.ndarray]) -> int:
        """Find the bucket with the largest color range.

        Args:
            buckets: List of color buckets (numpy arrays of pixels)

        Returns:
            Index of the bucket with the largest range, or -1 if none can be split
        """
        largest_range = -1
        largest_bucket_idx = -1

        for idx, bucket in enumerate(buckets):
            if len(bucket) <= 1:
                continue

            # Calculate range for each color channel
            ranges = np.ptp(bucket, axis=0)  # ptp = peak to peak (max - min)
            total_range = np.sum(ranges)

            if total_range > largest_range:
                largest_range = total_range
                largest_bucket_idx = idx

        return largest_bucket_idx

    def _split_bucket(self, buckets: list[np.ndarray], idx: int) -> list[np.ndarray]:
        """Split a bucket at its median along the largest range channel.

        Args:
            buckets: List of color buckets
            idx: Index of bucket to split

        Returns:
            Updated list of buckets with the specified bucket split into two
        """
        bucket_to_split = buckets[idx]

        # Find the channel with the largest range
        ranges = np.ptp(bucket_to_split, axis=0)
        channel = np.argmax(ranges)

        # Sort pixels by the selected channel
        sorted_pixels = bucket_to_split[bucket_to_split[:, channel].argsort()]

        # Split at median
        median_idx = len(sorted_pixels) // 2

        # Replace the old bucket with two new buckets
        buckets[idx] = sorted_pixels[:median_idx]
        buckets.append(sorted_pixels[median_idx:])

        return buckets

    def _split_buckets_mmcq(self, pixels: np.ndarray, num_colors: int) -> list[np.ndarray]:
        """Split color buckets using Modified Median Cut Quantization.

        Args:
            pixels: Array of all pixels in the image (Nx3)
            num_colors: Target number of color buckets

        Returns:
            List of color buckets
        """
        buckets = [pixels]

        # Iteratively split buckets until we have the desired number
        while len(buckets) < num_colors:
            largest_bucket_idx = self._find_largest_bucket(buckets)

            # If no bucket can be split, stop
            if largest_bucket_idx == -1:
                break

            # Split the largest bucket
            buckets = self._split_bucket(buckets, largest_bucket_idx)

        return buckets

    def _buckets_to_colors(self, buckets: list[np.ndarray], total_pixels: int) -> list[tuple[int, int, int]]:
        """Convert buckets to RGB colors sorted by prominence.

        Args:
            buckets: List of color buckets
            total_pixels: Total number of pixels in the image

        Returns:
            List of RGB tuples sorted by prominence
        """
        color_data = []
        for bucket in buckets:
            if len(bucket) > 0:
                avg_color = np.mean(bucket, axis=0)
                color_data.append((len(bucket), avg_color))

        # Sort by bucket size (descending) for consistent ordering
        color_data.sort(key=lambda x: x[0], reverse=True)

        # Extract colors as RGB tuples
        selected_colors = []
        for count, color in color_data:
            r, g, b = color
            selected_colors.append((int(r), int(g), int(b)))
            logger.debug(
                "Median Cut color: RGB(%3d, %3d, %3d) - pixels: %d (%.2f%%)",
                int(r),
                int(g),
                int(b),
                count,
                (count / total_pixels) * 100,
            )

        return selected_colors

    def _extract_colors_median_cut(self, image_bytes: bytes, num_colors: int) -> list[tuple[int, int, int]]:
        """Extract colors using Median Cut algorithm (MMCQ variant).

        This implements the Modified Median Cut Quantization (MMCQ) algorithm,
        which iteratively splits color space buckets until reaching the desired
        number of colors. Always splits the bucket with the largest color range.

        Args:
            image_bytes: Raw image data as bytes
            num_colors: Number of colors to extract

        Returns:
            List of RGB tuples ordered by bucket size (most prominent first)

        Raises:
            ValueError: If image processing fails
        """
        try:
            # Convert bytes to PIL Image
            image_io = io.BytesIO(image_bytes)
            pil_image = Image.open(image_io)

            # Convert to RGB if necessary
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Convert image to numpy array and get all pixels
            image_array = np.array(pil_image)
            pixels = image_array.reshape(-1, 3)

            # Split buckets using MMCQ algorithm
            buckets = self._split_buckets_mmcq(pixels, num_colors)

            # Calculate average colors and sort by prominence
            return self._buckets_to_colors(buckets, len(pixels))

        except Exception as e:
            msg = f"Median Cut color extraction failed: {e!s}"
            raise ValueError(msg) from e

    def _extract_colors_kmeans(self, image_bytes: bytes, num_colors: int) -> list[tuple[int, int, int]]:
        """Extract colors using KMeans clustering algorithm.

        Args:
            image_bytes: Raw image data as bytes
            num_colors: Number of colors to extract

        Returns:
            List of RGB tuples ordered by cluster size (most prominent first)

        Raises:
            ValueError: If image processing or clustering fails
        """
        try:
            # Convert bytes to PIL Image
            image_io = io.BytesIO(image_bytes)
            pil_image = Image.open(image_io)

            # Convert to RGB if necessary
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Convert image to numpy array and reshape to list of pixels
            image_array = np.array(pil_image)
            pixels = image_array.reshape(-1, 3)

            # Perform KMeans clustering
            kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init="auto")
            kmeans.fit(pixels)

            # Get cluster centers (the dominant colors)
            centers = kmeans.cluster_centers_

            # Count pixels in each cluster to get prominence
            labels = kmeans.labels_
            if labels is None:
                msg = "KMeans clustering failed to assign labels"
                raise ValueError(msg)  # noqa: TRY301
            unique_labels, counts = np.unique(labels, return_counts=True)

            # Sort clusters by count (most prominent first)
            sorted_indices = np.argsort(-counts)

            # Extract colors as RGB tuples
            selected_colors = []
            for idx in sorted_indices:
                r, g, b = centers[unique_labels[idx]]
                selected_colors.append((int(r), int(g), int(b)))
                logger.debug(
                    "KMeans color: RGB(%3d, %3d, %3d) - pixels: %d (%.2f%%)",
                    int(r),
                    int(g),
                    int(b),
                    counts[idx],
                    (counts[idx] / len(pixels)) * 100,
                )

        except Exception as e:
            msg = f"KMeans color extraction failed: {e!s}"
            raise ValueError(msg) from e
        else:
            return selected_colors

    def _get_colors_by_prominence(
        self, image_bytes: bytes, num_colors: int, algorithm: str = "kmeans"
    ) -> list[tuple[int, int, int]]:
        """Extract colors using the specified algorithm, ordered by prominence.

        This method dispatches to the appropriate color extraction algorithm
        based on the algorithm parameter.

        Args:
            image_bytes: Raw image data as bytes
            num_colors: Number of colors to extract
            algorithm: Algorithm to use ("kmeans" or "median_cut")

        Returns:
            List of RGB tuples ordered by prominence (most prominent first)

        Raises:
            ValueError: If image processing fails or algorithm is invalid
        """
        if algorithm == "kmeans":
            return self._extract_colors_kmeans(image_bytes, num_colors)
        if algorithm == "median_cut":
            return self._extract_colors_median_cut(image_bytes, num_colors)
        msg = f"Unknown algorithm: {algorithm}"
        raise ValueError(msg)

    def _clear_color_picker_parameters(self) -> None:
        """Clear all dynamically created color picker parameters.

        This method removes all previously created color parameters (color_1, color_2, etc.)
        to prevent duplicate parameter errors when the node runs again with different
        numbers of colors. It also resets the internal parameter counter.

        The method safely checks for parameter existence before attempting removal
        to avoid errors if parameters don't exist.
        """
        # Clear all color parameters that might exist (up to 15 since we extract max 15)
        for i in range(1, 16):  # Clear up to color_15 to be safe
            param_name = f"color_{i}"
            if self.get_parameter_by_name(param_name) is not None:
                logger.debug("Removing existing parameter: %s", param_name)
                # Clear parameter values first
                if param_name in self.parameter_values:
                    del self.parameter_values[param_name]
                if param_name in self.parameter_output_values:
                    del self.parameter_output_values[param_name]
                # Remove the parameter itself
                self.remove_parameter_element_by_name(param_name)

        self.number_of_color_params = 0

    def process(self) -> None:
        """Main processing method that extracts colors from the input image.

        This method performs the following steps:
        1. Clears any existing color parameters from previous runs
        2. Retrieves the input image, target number of colors, and algorithm choice
        3. Converts the image artifact to bytes for processing
        4. Uses the selected algorithm (KMeans or Median Cut) to extract dominant colors
        5. Colors are automatically ordered by prominence (most prominent first)
        6. Creates dynamic color picker parameters for each extracted color
        7. Logs color information for inspection

        The supported algorithms are:
        - KMeans: Uses sklearn's KMeans clustering to identify dominant colors
        - Median Cut: Recursively divides color space to find representative colors

        The selected colors are made available as dynamic output parameters
        named color_1, color_2, etc., each containing the hexadecimal color value
        and featuring a color picker UI component.

        Raises:
            ValueError: If image processing fails or no colors can be extracted
            Exception: If color extraction encounters an error
        """
        self._clear_color_picker_parameters()

        input_image = self.get_parameter_value("input_image")
        num_colors = self.get_parameter_value("num_colors")
        algorithm = self.get_parameter_value("algorithm")

        # Debug: Log image artifact information to detect caching issues
        if hasattr(input_image, "value"):
            image_value = str(input_image.value)
            image_id = image_value[:DEBUG_ID_LENGTH] + "..." if len(image_value) > DEBUG_ID_LENGTH else image_value
            logger.debug("Processing image: %s", image_id)
        elif isinstance(input_image, dict):
            image_value = str(input_image.get("value", "unknown"))
            image_id = image_value[:DEBUG_ID_LENGTH] + "..." if len(image_value) > DEBUG_ID_LENGTH else image_value
            logger.debug("Processing image dict: %s", image_id)
        else:
            logger.debug("Processing image of type: %s", type(input_image))

        logger.debug("Extracting %d colors from input image using %s algorithm", num_colors, algorithm)
        image_bytes = self._image_to_bytes(input_image)

        # Debug: Create hash to detect if the same image data is being processed
        # Note: MD5 is used here only for debug logging, not for security
        image_hash = hashlib.md5(image_bytes, usedforsecurity=False).hexdigest()[:8]
        logger.debug("Image data hash: %s (size: %d bytes)", image_hash, len(image_bytes))

        # Extract colors ordered by actual prominence in the image
        selected_colors = self._get_colors_by_prominence(image_bytes, num_colors, algorithm)
        selected_count = len(selected_colors)

        logger.debug("Extracted %d colors ordered by prominence", selected_count)
        self.number_of_color_params = selected_count

        for i, color in enumerate(selected_colors, 1):
            r, g, b = color
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            logger.debug("  Color %d: RGB(%3d, %3d, %3d) | Hex: %s", i, r, g, b, hex_color)

            param_name = f"color_{i}"
            logger.debug("Creating parameter %s with value %s", param_name, hex_color)

            self.add_parameter(
                Parameter(
                    name=param_name,
                    default_value=hex_color,
                    allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                    type="str",
                    tooltip="Hex color",
                    traits={ColorPicker(format="hex")},
                    settable=False,
                )
            )
