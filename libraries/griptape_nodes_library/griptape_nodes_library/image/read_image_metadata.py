from typing import Any, ClassVar

from griptape_nodes.drivers.image_metadata.image_metadata_driver_registry import (
    ImageMetadataDriverRegistry,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterGroupToNodeRequest,
    AddParameterToNodeRequest,
    RemoveParameterFromNodeRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.image_utils import load_pil_image_from_artifact


class ReadImageMetadataNode(SuccessFailureNode):
    """Read metadata from images.

    Supports reading all available metadata from JPEG/TIFF/MPO (EXIF) and PNG formats.
    Delegates to format-specific drivers for extraction.
    Outputs the metadata as a dictionary.
    """

    # Fixed parameter group names that should not be removed when syncing
    FIXED_GROUPS: ClassVar[set[str]] = {"STATUS"}

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
        # Note: Must use direct method during __init__ - node not registered yet
        self.add_parameter(
            Parameter(
                name="metadata",
                type="dict",
                output_type="dict",
                default_value={},
                allowed_modes={ParameterMode.OUTPUT},
                hide_property=True,
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
        """
        self._clear_execution_status()

        image = self.get_parameter_value("image")

        self._read_and_populate_metadata(image)

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
        """Remove all dynamically created parameters and groups by scanning current state."""
        # Get all current parameter groups (excluding fixed groups)
        fixed_groups = self.FIXED_GROUPS  # Known fixed group names

        # Find all dynamic groups (metadata groups like "GPS", "Griptape Nodes", "Other")
        all_groups = self.root_ui_element.find_elements_by_type(ParameterGroup)
        dynamic_groups = [group for group in all_groups if group.name not in fixed_groups and group.user_defined]

        # Remove all user-defined parameters in dynamic groups
        for group in dynamic_groups:
            parameters = group.find_elements_by_type(Parameter)
            for param in parameters:
                # Only remove user-defined parameters
                if param.user_defined:
                    result = GriptapeNodes.handle_request(
                        RemoveParameterFromNodeRequest(node_name=self.name, parameter_name=param.name)
                    )
                    if result.failed():
                        logger.warning(f"{self.name}: Failed to remove parameter {param.name}: {result.result_details}")

        # Remove the dynamic groups themselves (already filtered to user_defined above)
        for group in dynamic_groups:
            result = GriptapeNodes.handle_request(
                RemoveParameterFromNodeRequest(node_name=self.name, parameter_name=group.name)
            )
            if result.failed():
                logger.warning(f"{self.name}: Failed to remove group {group.name}: {result.result_details}")

    def _remove_group_if_empty(self, group_name: str) -> None:
        """Remove a parameter group if it has no remaining parameters.

        Args:
            group_name: Name of the group to check and potentially remove
        """
        group = self.get_group_by_name_or_element_id(group_name)
        if group is None:
            return

        parameters = group.find_elements_by_type(Parameter)

        if len(parameters) == 0:
            result = GriptapeNodes.handle_request(
                RemoveParameterFromNodeRequest(node_name=self.name, parameter_name=group_name)
            )
            if result.failed():
                logger.warning(f"{self.name}: Failed to remove empty group {group_name}: {result.result_details}")

    def _get_or_create_group(self, group_name: str) -> None:
        """Get existing group or create new one.

        Args:
            group_name: Name of the parameter group
        """
        param_group = self.get_group_by_name_or_element_id(group_name)
        if param_group is None:
            # Create ParameterGroup using request API
            result = GriptapeNodes.handle_request(
                AddParameterGroupToNodeRequest(
                    node_name=self.name, group_name=group_name, ui_options={"collapsed": True}, is_user_defined=True
                )
            )
            if result.failed():
                logger.warning(f"{self.name}: Failed to create group {group_name}: {result.result_details}")

    def _get_or_create_parameter(self, key: str, group_name: str, value: str) -> None:
        """Get existing parameter or create new one, setting its value.

        Args:
            key: Parameter name
            group_name: Name of parent parameter group
            value: Value to set for the parameter
        """
        existing_param = self.get_parameter_by_name(key)
        if existing_param is None:
            # Create new parameter
            result = GriptapeNodes.handle_request(
                AddParameterToNodeRequest(
                    node_name=self.name,
                    parameter_name=key,
                    type="str",
                    output_type="str",
                    default_value="",
                    mode_allowed_input=False,
                    mode_allowed_property=False,
                    mode_allowed_output=True,
                    tooltip=f"Metadata value for '{key}'",
                    parent_element_name=group_name,
                    is_user_defined=True,
                )
            )
            if result.failed():
                logger.warning(f"{self.name}: Failed to create parameter {key}: {result.result_details}")
            else:
                # Set the output value
                self.parameter_output_values[key] = value
        else:
            # Parameter already exists, just update its value
            self.parameter_output_values[key] = value

    def _sync_dynamic_parameters(self, new_metadata: dict[str, str]) -> None:
        """Sync dynamic parameters with new metadata - add, update, or remove as needed.

        Args:
            new_metadata: New metadata dictionary to sync with
        """
        # Get current dynamic parameters by scanning
        current_dynamic_params = self._get_current_dynamic_parameters()
        old_keys = {p.name for p in current_dynamic_params}
        new_keys = set(new_metadata.keys())

        keys_to_remove = old_keys - new_keys
        groups_to_check = set()

        for key in keys_to_remove:
            param = self.get_parameter_by_name(key)
            if param and param.parent_element_name:
                groups_to_check.add(param.parent_element_name)

            result = GriptapeNodes.handle_request(
                RemoveParameterFromNodeRequest(node_name=self.name, parameter_name=key)
            )
            if result.failed():
                logger.warning(f"{self.name}: Failed to remove parameter {key}: {result.result_details}")

        for group_name in groups_to_check:
            self._remove_group_if_empty(group_name)

        self._create_dynamic_parameters(new_metadata)

    def _get_current_dynamic_parameters(self) -> list[Parameter]:
        """Get all current dynamically created metadata parameters by scanning state.

        Returns:
            List of user-defined parameters that are in dynamic metadata groups
        """
        fixed_groups = self.FIXED_GROUPS
        dynamic_params = []

        all_groups = self.root_ui_element.find_elements_by_type(ParameterGroup)
        for group in all_groups:
            if group.name not in fixed_groups and group.user_defined:
                # Only include user-defined parameters
                parameters = group.find_elements_by_type(Parameter)
                dynamic_params.extend([p for p in parameters if p.user_defined])

        return dynamic_params

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
            elif prefix == "gtn":
                group_name = "Griptape Nodes"
            else:
                group_name = prefix

            # Get or create the parameter group
            self._get_or_create_group(group_name)

            # Create parameters and add them to the group
            for key in sorted(metadata_subset.keys()):
                self._get_or_create_parameter(key, group_name, metadata_subset[key])

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
            error_msg = "No image provided"
            self._remove_dynamic_parameters()
            self._set_status_results(was_successful=False, result_details=error_msg)
            return

        # Load PIL image
        try:
            pil_image = load_pil_image_from_artifact(image, self.name)
        except (TypeError, ValueError) as e:
            logger.warning(f"{self.name}: Failed to load image: {e}")
            self._remove_dynamic_parameters()
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return

        # Detect format
        image_format = pil_image.format
        if not image_format:
            error_msg = "Could not detect image format"
            logger.warning(f"{self.name}: {error_msg}")
            self._remove_dynamic_parameters()
            self._set_status_results(was_successful=False, result_details=error_msg)
            self._handle_failure_exception(ValueError(f"{self.name}: {error_msg}"))
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
                error_msg = f"Failed to read metadata: {e}"
                logger.warning(f"{self.name}: {error_msg}")
                self._remove_dynamic_parameters()
                self._set_status_results(was_successful=False, result_details=error_msg)
                self._handle_failure_exception(ValueError(f"{self.name}: {error_msg}"))
                return

        # Success - set outputs
        self.parameter_output_values["metadata"] = metadata

        # Sync dynamic parameters intelligently (add, update, or remove as needed)
        self._sync_dynamic_parameters(metadata)

        count = len(metadata)
        if count > 0:
            success_msg = f"Successfully read {count} metadata entries"
        else:
            success_msg = "No metadata found in image"

        self._set_status_results(was_successful=True, result_details=success_msg)
        logger.info(f"{self.name}: {success_msg}")
