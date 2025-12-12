import logging
from typing import Any

from griptape.artifacts import AudioArtifact, ImageArtifact, ImageUrlArtifact

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
    ParameterType,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes.retained_mode.events.connection_events import DeleteConnectionRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.three_d.three_d_artifact import ThreeDArtifact, ThreeDUrlArtifact
from griptape_nodes_library.utils.audio_utils import is_audio_url_artifact
from griptape_nodes_library.utils.video_utils import is_video_url_artifact


class DisplayList(ControlNode):
    """DisplayList Node that takes a list and creates output parameters for each item in the list.

    This node takes a list as input and creates a new output parameter for each item in the list.
    Each output parameter is individually typed based on its specific item, allowing for mixed-type
    lists where different items can have different types.

    Features:
    - Individual type detection: Each item's type is detected independently
    - Automatic connection validation: Incompatible connections are removed when types change
    - Type-specific UI options: Images get proper display, dicts get multiline, etc.
    - Complete type information: Each parameter has type, output_type, and input_types set

    Supported types: str, int, float, bool, dict, ImageUrlArtifact/ImageArtifact
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        # Add input list parameter
        self.items = Parameter(
            name="items",
            tooltip="List of items to create output parameters for",
            input_types=["list"],
            output_type="list",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.items)
        # Spot that will display the list.
        self.items_list = ParameterList(
            name="display_list",
            tooltip="Output list. Your values will propagate in these inputs here.",
            type=ParameterTypeBuiltin.ANY.value,
            output_type=ParameterTypeBuiltin.ALL.value,
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            ui_options={"hide_property": False},
        )
        self.add_parameter(self.items_list)
        # Track whether we're already updating to prevent duplicate calls
        self._updating_display_list = False
        # We'll create output parameters dynamically during processing

    def process(self) -> None:
        # During process, we want to clean up parameters if the list is too long
        self._update_display_list(delete_excess_parameters=True)

    def _update_display_list(self, *, delete_excess_parameters: bool = False) -> None:
        """Update the display list parameters based on current input values.

        Args:
            delete_excess_parameters: If True, delete parameters when list is shorter than parameter count.
                                    If False, keep existing parameters even when list is shorter.
        """
        # Prevent duplicate calls
        if self._updating_display_list:
            logger.debug(
                "DisplayList._update_display_list(): Already updating for node %s, skipping duplicate call",
                self.name,
            )
            return

        self._updating_display_list = True

        # Try to get the list of items from the input parameter
        try:
            list_values = self.get_parameter_value("items")
        except Exception:
            self._clear_list()
            # If we can't get the parameter value (e.g., connected node not resolved yet),
            # just clear and return - we'll update again when values are available
            self._updating_display_list = False
            return

        # Prepare ui_options update in one go to avoid multiple change events
        new_ui_options = self.items_list.ui_options.copy()

        # If it's None or not a list...
        if not isinstance(list_values, list):
            if "display" in new_ui_options:
                # Remove display from the ui_options so non-image parameters will properly display.
                del new_ui_options["display"]
            self.items_list.ui_options = new_ui_options
            self._updating_display_list = False
            return

        # Regenerate parameters for each item in the list
        if len(list_values) == 0:
            # If we're empty, be empty.
            self._clear_list()
            self.items_list.ui_options = new_ui_options
            self._updating_display_list = False
            return

        new_ui_options["hide"] = False
        item_type = self._determine_item_type(list_values[0])
        self._configure_list_type_and_ui(item_type, new_ui_options)
        # Only delete excess parameters if explicitly requested (e.g., during process())
        if delete_excess_parameters:
            self.delete_excess_parameters(list_values)
        for i, item in enumerate(list_values):
            item_specific_type = self._determine_item_type(item)
            if i < len(self.items_list):
                self._update_existing_parameter(self.items_list[i], item, item_specific_type)
            else:
                self._create_new_parameter(item, item_specific_type)
        self._updating_display_list = False

    def _update_existing_parameter(self, parameter: Parameter, item: Any, item_specific_type: str) -> None:
        """Update an existing parameter with new value and type.

        Args:
            parameter: The parameter to update
            item: The item value to set
            item_specific_type: The detected type of the item
        """
        # Update all type fields for this parameter
        if item_specific_type == ParameterTypeBuiltin.ANY.value:
            new_output_type = ParameterTypeBuiltin.ALL.value
        else:
            new_output_type = item_specific_type

        parameter.type = item_specific_type
        parameter.output_type = new_output_type
        parameter.input_types = [item_specific_type]

        # Set UI options based on type
        if item_specific_type == "ImageUrlArtifact":
            parameter.ui_options = {"display": "image"}
        elif item_specific_type in ["VideoUrlArtifact", "VideoArtifact"]:
            parameter.ui_options = {"display": "video"}
        elif item_specific_type in ["AudioUrlArtifact", "AudioArtifact"]:
            parameter.ui_options = {"display": "audio"}
        elif item_specific_type in ["ThreeDUrlArtifact", "ThreeDArtifact", "GLTFUrlArtifact", "GLTFArtifact"]:
            parameter.ui_options = {"display": "3d"}
        elif item_specific_type == "dict":
            parameter.ui_options = {"multiline": True}

        # Validate and remove incompatible connections
        self._validate_and_remove_incompatible_connections(parameter.name, new_output_type)

        self.set_parameter_value(parameter.name, item)
        # Using to ensure updates are being propagated
        self.publish_update_to_parameter(parameter.name, item)
        self.parameter_output_values[parameter.name] = item

    def _create_new_parameter(self, item: Any, item_specific_type: str) -> None:
        """Create a new child parameter for a list item.

        Args:
            item: The item value to set
            item_specific_type: The detected type of the item
        """
        new_child = self.items_list.add_child_parameter()
        # Set all type fields for the new child parameter
        if item_specific_type == ParameterTypeBuiltin.ANY.value:
            new_output_type = ParameterTypeBuiltin.ALL.value
        else:
            new_output_type = item_specific_type

        new_child.type = item_specific_type
        new_child.output_type = new_output_type
        new_child.input_types = [item_specific_type]

        # Set UI options based on type
        if item_specific_type == "ImageUrlArtifact":
            new_child.ui_options = {"display": "image"}
        elif item_specific_type in ["VideoUrlArtifact", "VideoArtifact"]:
            new_child.ui_options = {"display": "video"}
        elif item_specific_type in ["AudioUrlArtifact", "AudioArtifact"]:
            new_child.ui_options = {"display": "audio"}
        elif item_specific_type in ["ThreeDUrlArtifact", "ThreeDArtifact", "GLTFUrlArtifact", "GLTFArtifact"]:
            new_child.ui_options = {"display": "3d"}
        elif item_specific_type == "dict":
            new_child.ui_options = {"multiline": True}

        # Validate and remove incompatible connections for new parameters too
        self._validate_and_remove_incompatible_connections(new_child.name, new_output_type)

        # Set the parameter value
        self.set_parameter_value(new_child.name, item)

    def delete_excess_parameters(self, list_values: list) -> None:
        """Delete parameters when list is shorter than parameter count."""
        length_of_items_list = len(self.items_list)
        while length_of_items_list > len(list_values):
            # Remove the parameter value - this will also handle parameter_output_values
            if self.items_list[length_of_items_list - 1].name in self.parameter_values:
                self.remove_parameter_value(self.items_list[length_of_items_list - 1].name)
            if self.items_list[length_of_items_list - 1].name in self.parameter_output_values:
                del self.parameter_output_values[self.items_list[length_of_items_list - 1].name]
            # Remove the parameter from the list
            self.items_list.remove_child(self.items_list[length_of_items_list - 1])
            length_of_items_list = len(self.items_list)

    def _clear_list(self) -> None:
        """Clear all dynamically-created parameters from the node."""
        for child in self.items_list.find_elements_by_type(Parameter):
            # Remove the parameter value - this will also handle parameter_output_values
            # We are suppressing the error, which will be raised if the parameter is not in parameter_values.
            # This is ok, because we are just trying to remove the parameter value IF it exists.
            if child.name in self.parameter_values:
                self.remove_parameter_value(child.name)
            if child.name in self.parameter_output_values:
                del self.parameter_output_values[child.name]
            # Remove the parameter from the list
        self.items_list.clear_list()

    def _configure_list_type_and_ui(self, item_type: str, ui_options: dict[str, Any]) -> None:
        """Configure the items_list parameter type and UI options based on item type.

        Args:
            item_type: The type string for list items
            ui_options: Dictionary of UI options to configure
        """
        # Configure UI options for dict display
        if item_type == "dict":
            ui_options["multiline"] = True
            ui_options["placeholder_text"] = "The dictionary content will be displayed here."
        elif item_type == "ImageUrlArtifact":
            ui_options["display"] = "image"
        elif item_type in ["VideoUrlArtifact", "VideoArtifact"]:
            ui_options["display"] = "video"
        elif item_type in ["AudioUrlArtifact", "AudioArtifact"]:
            ui_options["display"] = "audio"
        elif item_type in ["ThreeDUrlArtifact", "ThreeDArtifact", "GLTFUrlArtifact", "GLTFArtifact"]:
            ui_options["display"] = "3d"

        # We have to change all three because parameters are created with all three initialized.
        self.items_list.type = item_type
        if item_type == ParameterTypeBuiltin.ANY.value:
            self.items_list.output_type = ParameterTypeBuiltin.ALL.value
        else:
            self.items_list.output_type = item_type
        self.items_list.input_types = [item_type]
        self.items_list.ui_options = ui_options

    def _determine_item_type(self, item: Any) -> str:
        """Determine the type of an item for parameter type assignment."""
        # Builtin types - use type mapping for efficiency
        builtin_type_map = {
            bool: ParameterTypeBuiltin.BOOL.value,
            str: ParameterTypeBuiltin.STR.value,
            int: ParameterTypeBuiltin.INT.value,
            float: ParameterTypeBuiltin.FLOAT.value,
            dict: "dict",
        }
        item_type = type(item)
        if item_type in builtin_type_map:
            return builtin_type_map[item_type]

        # Artifact types - check in order of likelihood
        result = ParameterTypeBuiltin.ANY.value

        # Image artifacts (most common)
        if isinstance(item, (ImageUrlArtifact, ImageArtifact)):
            result = "ImageUrlArtifact"
        # Video artifacts
        elif is_video_url_artifact(item):
            result = "VideoUrlArtifact"
        # Audio artifacts
        elif is_audio_url_artifact(item) or isinstance(item, AudioArtifact):
            result = "AudioUrlArtifact"
        # 3D artifacts
        elif isinstance(item, (ThreeDUrlArtifact, ThreeDArtifact)):
            result = "ThreeDUrlArtifact"
        # GLTF artifacts - check class name (handles different implementations)
        elif hasattr(item, "__class__"):
            class_name = item.__class__.__name__
            if "GLTFUrlArtifact" in class_name:
                result = "GLTFUrlArtifact"
            elif "GLTFArtifact" in class_name:
                result = "GLTFArtifact"

        return result

    def _validate_and_remove_incompatible_connections(self, parameter_name: str, new_output_type: str) -> None:
        """Validate and remove incompatible outgoing connections when output type changes.

        Args:
            parameter_name: The name of the parameter whose type changed
            new_output_type: The new output type that was set
        """
        node_logger = logging.getLogger("griptape_nodes")

        # Get outgoing connections from the specific parameter
        connections = GriptapeNodes.FlowManager().get_connections()
        outgoing_for_node = connections.outgoing_index.get(self.name, {})
        connection_ids = outgoing_for_node.get(parameter_name, [])

        if not connection_ids:
            return

        # Validate type compatibility and remove incompatible connections
        for connection_id in connection_ids:
            if connection_id not in connections.connections:
                continue

            connection = connections.connections[connection_id]
            target_param = connection.target_parameter
            target_node = connection.target_node

            # Check if target parameter accepts the new output type
            is_compatible = any(
                ParameterType.are_types_compatible(new_output_type, input_type)
                for input_type in target_param.input_types
            )

            if not is_compatible:
                node_logger.info(
                    "Removing incompatible connection: %s '%s' %s (%s) to '%s.%s' (accepts: %s)",
                    self.__class__.__name__,
                    self.name,
                    parameter_name,
                    new_output_type,
                    target_node.name,
                    target_param.name,
                    target_param.input_types,
                )

                # Remove the incompatible connection
                delete_result = GriptapeNodes.handle_request(
                    DeleteConnectionRequest(
                        source_node_name=self.name,
                        source_parameter_name=parameter_name,
                        target_node_name=target_node.name,
                        target_parameter_name=target_param.name,
                    )
                )

                if not delete_result.succeeded():
                    node_logger.error(
                        "Failed to delete incompatible connection from %s.%s to %s.%s: %s",
                        self.name,
                        parameter_name,
                        target_node.name,
                        target_param.name,
                        delete_result.result_details,
                    )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update display list when a value is assigned to the items parameter."""
        # Only update if the value was set on our items parameter
        if parameter == self.items:
            logger.debug(
                f"DisplayList.after_value_set(): Items parameter updated for node {self.name}, triggering display list update"
            )
            self._update_display_list()
        return super().after_value_set(parameter, value)

    def after_incoming_connection_removed(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        self._update_display_list()
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)
