from typing import Any

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.image_utils import load_pil_image_from_artifact


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

        # Add metadata output parameter (hidden - individual parameters are displayed instead)
        self.add_parameter(
            Parameter(
                name="metadata",
                type="dict",
                output_type="dict",
                default_value={},
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Dictionary of all metadata key-value pairs",
                ui_options={"hide": True},
            )
        )

        # Add status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the metadata read operation result",
            result_details_placeholder="Details on the read operation will be presented here.",
        )

        # Track dynamically created parameter groups and parameters
        self._dynamic_groups: dict[str, ParameterGroup] = {}
        self._dynamic_parameters: list[str] = []

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

    def _extract_prefix(self, key: str) -> str | None:
        """Extract prefix from metadata key (first segment before underscore).

        Args:
            key: Metadata key (e.g., "gtn_workflow_name", "GPS_Latitude", "Make")

        Returns:
            Prefix string (e.g., "gtn", "GPS"), or None if no prefix
        """
        if "_" not in key:
            return None

        return key.split("_", 1)[0]

    def _group_metadata_by_prefix(self, metadata: dict[str, str]) -> dict[str | None, dict[str, str]]:
        """Group metadata keys by their prefix.

        Args:
            metadata: Full metadata dictionary

        Returns:
            Dictionary mapping prefix (or None) to metadata subset
        """
        grouped: dict[str | None, dict[str, str]] = {}

        for key, value in metadata.items():
            prefix = self._extract_prefix(key)
            if prefix not in grouped:
                grouped[prefix] = {}
            grouped[prefix][key] = value

        return grouped

    def _remove_dynamic_parameters(self) -> None:
        """Remove all dynamically created parameters and groups."""
        # Remove all dynamic parameters
        for param_name in self._dynamic_parameters:
            self.remove_parameter_element_by_name(param_name)
        self._dynamic_parameters.clear()

        # Remove all dynamic groups
        for group_name in self._dynamic_groups:
            self.remove_parameter_element_by_name(group_name)
        self._dynamic_groups.clear()

    def _create_dynamic_parameters(self, metadata: dict[str, str]) -> None:
        """Create individual parameters for each metadata key, organized by prefix.

        Args:
            metadata: Full metadata dictionary
        """
        # Group metadata by prefix
        grouped = self._group_metadata_by_prefix(metadata)

        # Sort prefixes: None (Other) last, rest alphabetically
        sorted_prefixes: list[str | None] = []
        sorted_prefixes.extend(sorted([p for p in grouped if p is not None], key=str.lower))
        if None in grouped:
            sorted_prefixes.append(None)

        # Create groups and parameters
        for prefix in sorted_prefixes:
            metadata_subset = grouped[prefix]

            # Determine group name
            if prefix is None:
                group_name = "Other"
            else:
                group_name = prefix

            # Create ParameterGroup
            param_group = ParameterGroup(name=group_name, ui_options={"collapsed": True})

            # Create parameters within the group context
            with param_group:
                for key in sorted(metadata_subset.keys()):
                    # Create parameter inside context - it will auto-link to the group
                    Parameter(
                        name=key,
                        type="str",
                        output_type="str",
                        default_value="",
                        allowed_modes={ParameterMode.OUTPUT},
                        tooltip=f"Metadata value for '{key}'",
                    )
                    self._dynamic_parameters.append(key)

                    # Set the output value
                    self.parameter_output_values[key] = metadata_subset[key]

            # Add the group to the node
            self.add_node_element(param_group)
            self._dynamic_groups[group_name] = param_group

    def _read_and_populate_metadata(self, image: Any) -> None:
        """Read metadata from image and populate output parameter.

        This method is called both from process() and after_value_set() to enable
        automatic processing when the image parameter receives a value.

        Args:
            image: Image value (ImageUrlArtifact, ImageArtifact, str, or None)
        """
        # Clear metadata output first
        self.parameter_output_values["metadata"] = {}

        # Remove dynamic parameters when clearing
        self._remove_dynamic_parameters()

        # Handle None/empty case - clear output and return
        if not image:
            self._set_status_results(was_successful=False, result_details="No image provided")
            return

        # Load PIL image
        try:
            pil_image = load_pil_image_from_artifact(image, self.name)
        except (TypeError, ValueError) as e:
            self._set_status_results(was_successful=False, result_details=str(e))
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

        # Remove previous dynamic parameters and groups
        self._remove_dynamic_parameters()

        # Create new dynamic parameters for current metadata
        if metadata:
            self._create_dynamic_parameters(metadata)

        count = len(metadata)
        if count > 0:
            success_msg = f"Successfully read {count} metadata entries"
        else:
            success_msg = "No metadata found in image"

        self._set_status_results(was_successful=True, result_details=success_msg)
        logger.info(f"{self.name}: {success_msg}")
