"""
Test node demonstrating ParameterMessage with publish_update() method in hooks.

This node demonstrates how to use ParameterMessage with publish_update() in the context
of parameter connection hooks, similar to real nodes in the Griptape library.
It shows dynamic UI updates based on parameter connections and value changes.
"""

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import  BaseNode
from griptape_nodes.traits.options import Options


class ParameterMessageTestNode(BaseNode):
    """Test node that demonstrates ParameterMessage functionality with proper hooks."""

    def __init__(self, **kwargs) -> None:
        """Initialize the test node with parameters and UI messages."""
        # Set default name if not provided
        if 'name' not in kwargs:
            kwargs['name'] = 'ParameterMessageTestNode'
        super().__init__(**kwargs)

        # --- Parameter Definitions ---
        
        # Primary input parameter
        self.add_parameter(
            Parameter(
                name="input_text",
                type="str",
                input_types=["str"],
                output_type="str",
                tooltip="Primary text input for processing",
                default_value="Hello World",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Enter text to process...",
                },
            )
        )

        # Processing mode selection
        self.add_parameter(
            Parameter(
                name="processing_mode",
                type="str",
                input_types=["str"],
                tooltip="Select the processing mode",
                default_value="uppercase",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["uppercase", "lowercase", "reverse", "capitalize"])},
                ui_options={"display_name": "Processing Mode"},
            )
        )

        # Optional configuration parameter
        self.add_parameter(
            Parameter(
                name="config",
                type="dict",
                input_types=["dict", "Config"],
                tooltip="Optional configuration object",
                default_value={},
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Connect a configuration or leave empty"},
            )
        )

        # Output parameter
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                tooltip="Processed output text",
                default_value="",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Processing result"},
            )
        )

        # --- Status Messages ---
        
        # Create status message for general node state
        self.status_message = ParameterMessage(
            variant="info",
            value="Node ready for configuration",
            title="Status",
            name="status_indicator",
            ui_options={
                "collapsible": False,
                "priority": "high",
                "show_timestamp": True,
            }
        )
        self.add_node_element(self.status_message)

        # Create configuration hint message
        self.config_hint = ParameterMessage(
            variant="tip",
            value="Connect parameters to see dynamic updates",
            title="Configuration",
            name="config_hint",
            ui_options={
                "dismissible": True,
                "show_icon": True,
            }
        )
        self.add_node_element(self.config_hint)

        # --- Parameter Groups ---
        
        # Advanced options group (initially hidden)
        with ParameterGroup(name="Advanced Options") as advanced_group:
            Parameter(
                name="enable_logging",
                type="bool",
                default_value=False,
                tooltip="Enable detailed logging",
                allowed_modes={ParameterMode.PROPERTY},
            )
            Parameter(
                name="max_length",
                type="int",
                default_value=1000,
                tooltip="Maximum output length",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"min": 1, "max": 10000},
            )

        advanced_group.ui_options = {"hide": True, "collapsible": True}
        self.add_node_element(advanced_group)

    # --- Helper Methods ---
    
    def _find_message_by_name(self, name: str) -> ParameterMessage | None:
        """Find a ParameterMessage child element by name."""
        element = self.get_element_by_name_and_type(name, ParameterMessage)
        return element if isinstance(element, ParameterMessage) else None

    # --- UI Interaction Hooks ---

    def after_incoming_connection(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        """Handle UI updates when parameters are connected."""
        
        # Update status message when input_text is connected
        if target_parameter.name == "input_text":
            self.status_message.variant = "success"
            self.status_message.value = f"Input connected from {source_node.name}.{source_parameter.name}"
            self.status_message.ui_options = {
                **self.status_message.ui_options,
                "color": "green",
                "icon": "link",
                "connected": True,
            }
            #self.status_message.publish_update()
            
            # Update config hint to show connection made
            self.config_hint.value = "Input connected! Try connecting a configuration next."
            self.config_hint.variant = "success"
            self.config_hint.ui_options = {
                **self.config_hint.ui_options,
                "highlight": True,
            }
            #self.config_hint.publish_update()

        # Handle config parameter connection
        if target_parameter.name == "config":
            # Update parameter to only accept inputs when connected
            target_parameter.allowed_modes = {ParameterMode.INPUT}
            
            # Create a new status message for config connection
            config_status = ParameterMessage(
                variant="info",
                value=f"Configuration connected from {source_parameter.name}",
                title="Config Status",
                name="config_status",
                ui_options={
                    "color": "blue",
                    "icon": "settings",
                    "temporary": True,
                }
            )
            self.add_node_element(config_status)
            #config_status.publish_update()
            
            # Hide the config hint since it's no longer needed
            self.config_hint.ui_options = {
                **self.config_hint.ui_options,
                "hide": True,
            }
            #self.config_hint.publish_update()

        # Handle processing mode connection from external source
        if target_parameter.name == "processing_mode" and source_parameter.name != "processing_mode":
            # Remove the options trait when connected externally
            options_traits = target_parameter.find_elements_by_type(Options)
            if options_traits:
                target_parameter.remove_trait(options_traits[0])
            
            # Update parameter type to match source
            target_parameter.type = source_parameter.type
            target_parameter.allowed_modes = {ParameterMode.INPUT}
            
            # Update UI options
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = f"Processing Mode ({source_parameter.name})"
            ui_options["connected_from"] = source_node.name
            target_parameter.ui_options = ui_options
            
            # Update status message
            self.status_message.variant = "warning"
            self.status_message.value = "Processing mode overridden by external connection"
            self.status_message.ui_options = {
                **self.status_message.ui_options,
                "color": "orange",
                "icon": "override",
            }
            self.status_message.publish_update()

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Handle UI updates when parameter connections are removed."""
        
        # Update status when input_text connection is removed
        if target_parameter.name == "input_text":
            self.status_message.variant = "warning"
            self.status_message.value = "Input disconnected - using property value"
            self.status_message.ui_options = {
                **self.status_message.ui_options,
                "color": "orange",
                "icon": "unlink",
                "connected": False,
            }
            # self.status_message.publish_update()  # Commented out to prevent double emission with tracked parameters
            
            # Show config hint again
            self.config_hint.value = "Input disconnected. Connect parameters to see dynamic updates."
            self.config_hint.variant = "tip"
            self.config_hint.ui_options = {
                **self.config_hint.ui_options,
                "highlight": False,
                "hide": False,
            }
            # self.config_hint.publish_update()  # Commented out to prevent double emission with tracked parameters

        # Handle config parameter disconnection
        if target_parameter.name == "config":
            # Re-enable property mode
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}
            
            # Remove the config status message
            config_status = self._find_message_by_name("config_status")
            if config_status:
                self.remove_node_element(config_status)
            
            # Show config hint again
            self.config_hint.ui_options = {
                **self.config_hint.ui_options,
                "hide": False,
            }
            # self.config_hint.publish_update()  # Commented out to prevent double emission with tracked parameters

        # Handle processing mode disconnection
        if target_parameter.name == "processing_mode":
            # Reset parameter type and modes
            target_parameter.type = "str"
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}
            
            # Re-add the options trait
            target_parameter.add_trait(Options(choices=["uppercase", "lowercase", "reverse", "capitalize"]))
            
            # Reset UI options
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = "Processing Mode"
            ui_options.pop("connected_from", None)
            target_parameter.ui_options = ui_options
            
            # Update status
            self.status_message.variant = "info"
            self.status_message.value = "Processing mode restored to default options"
            self.status_message.ui_options = {
                **self.status_message.ui_options,
                "color": "blue",
                "icon": "restore",
            }
            self.status_message.publish_update()

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle UI updates when parameter values are set/changed."""
        
        # Update status based on processing mode changes
        if parameter.name == "processing_mode":
            mode_descriptions = {
                "uppercase": "Convert text to UPPERCASE",
                "lowercase": "convert text to lowercase", 
                "reverse": "esreveR txet redro",
                "capitalize": "Capitalize First Letter Of Each Word"
            }
            
            description = mode_descriptions.get(value, "Process text")
            
            # Create or update processing mode message
            mode_message = self._find_message_by_name("mode_description") 
            if not mode_message:
                mode_message = ParameterMessage(
                    variant="none",
                    value=description,
                    title="Processing",
                    name="mode_description",
                    ui_options={
                        "italic": True,
                        "small": True,
                    }
                )
                self.add_node_element(mode_message)
            else:
                mode_message.value = description
            
            mode_message.publish_update()
            
            # Also update main status message
            self.status_message.value = f"Processing mode set to: {value}"
            self.status_message.variant = "info"
            self.status_message.ui_options = {
                **self.status_message.ui_options,
                "color": "blue",
                "icon": "settings",
                "mode": value,
            }
            self.status_message.publish_update()

        # Update status for text input changes
        if parameter.name == "input_text":
            text_length = len(str(value)) if value else 0
            
            if text_length == 0:
                variant = "warning"
                message = "No input text provided"
                color = "orange"
            elif text_length > 500:
                variant = "warning"
                message = f"Long input detected ({text_length} characters)"
                color = "orange"
            else:
                variant = "info"
                message = f"Input ready ({text_length} characters)"
                color = "blue"
            
            # Update or create input status message
            input_status = self._find_message_by_name("input_status")
            if not input_status:
                input_status = ParameterMessage(
                    variant=variant,
                    value=message,
                    name="input_status",
                    ui_options={
                        "compact": True,
                        "character_count": text_length,
                        "color": color,
                    }
                )
                self.add_node_element(input_status)
            else:
                input_status.variant = variant
                input_status.value = message
                input_status.ui_options = {
                    **input_status.ui_options,
                    "character_count": text_length,
                    "color": color,
                }
            
            # input_status.publish_update()  # Commented out to prevent double emission with tracked parameters

        # Update status for configuration changes
        if parameter.name == "config":
            if value and isinstance(value, dict) and len(value) > 0:
                config_keys = list(value.keys())
                self.status_message.value = f"Configuration updated with keys: {', '.join(config_keys)}"
                self.status_message.variant = "success"
                self.status_message.ui_options = {
                    **self.status_message.ui_options,
                    "color": "green",
                    "icon": "config",
                    "config_keys": config_keys,
                }
            else:
                self.status_message.value = "Configuration cleared"
                self.status_message.variant = "info"
                self.status_message.ui_options = {
                    **self.status_message.ui_options,
                    "color": "gray",
                    "icon": "clear",
                }
            self.status_message.publish_update()

        # Update for advanced options
        if parameter.name == "enable_logging":
            log_message = self._find_message_by_name("logging_status")
            if not log_message:
                log_message = ParameterMessage(
                    variant="none",
                    value="",
                    name="logging_status",
                    ui_options={"compact": True}
                )
                self.add_node_element(log_message)
            
            if value:
                log_message.value = "Detailed logging enabled"
                log_message.variant = "info"
                log_message.ui_options = {
                    **log_message.ui_options,
                    "color": "blue",
                    "icon": "log"
                }
            else:
                log_message.value = "Standard logging mode"
                log_message.variant = "none"
                log_message.ui_options = {
                    **log_message.ui_options,
                    "color": "gray",
                    "icon": "log-off"
                }
            log_message.publish_update()

        if parameter.name == "max_length":
            length_warning = self._find_message_by_name("length_warning")
            
            if value and value < 100:
                if not length_warning:
                    length_warning = ParameterMessage(
                        variant="warning",
                        value=f"Very short max length set ({value} chars)",
                        name="length_warning",
                        ui_options={
                            "dismissible": True,
                            "icon": "warning"
                        }
                    )
                    self.add_node_element(length_warning)
                else:
                    length_warning.value = f"Very short max length set ({value} chars)"
                
                length_warning.publish_update()
            elif length_warning:
                # Remove warning if length is acceptable
                self.remove_node_element(length_warning)

        return super().after_value_set(parameter, value)

    # --- Processing ---
    def process(self) -> None:
        """Execute the node's main processing logic."""
        
        # Update status to processing
        self.status_message.variant = "info"
        self.status_message.value = "Processing..."
        self.status_message.ui_options = {
            **self.status_message.ui_options,
            "color": "blue",
            "icon": "processing",
            "animated": True,
        }
        self.status_message.publish_update()

        # Get parameter values
        input_text = self.get_parameter_value("input_text") or ""
        processing_mode = self.get_parameter_value("processing_mode") or "uppercase"
        max_length = self.get_parameter_value("max_length") or 1000
        
        # Process the text based on mode
        if processing_mode == "uppercase":
            result = input_text.upper()
        elif processing_mode == "lowercase":
            result = input_text.lower()
        elif processing_mode == "reverse":
            result = input_text[::-1]
        elif processing_mode == "capitalize":
            result = input_text.title()
        else:
            result = input_text
        
        # Apply max length limit
        if len(result) > max_length:
            result = result[:max_length] + "..."
            
            # Show truncation warning
            warning_msg = ParameterMessage(
                variant="warning",
                value=f"Output truncated to {max_length} characters",
                name="truncation_warning",
                ui_options={
                    "dismissible": True,
                    "auto_dismiss": 5000,  # Auto-dismiss after 5 seconds
                }
            )
            self.add_node_element(warning_msg)
            warning_msg.publish_update()
        
        # Set output
        self.set_parameter_value("output", result)
        
        # Update final status
        self.status_message.variant = "success"
        self.status_message.value = f"Processing complete - {len(result)} characters generated"
        self.status_message.ui_options = {
            **self.status_message.ui_options,
            "color": "green",
            "icon": "check",
            "animated": False,
        }
        self.status_message.publish_update()


# Example usage for testing
if __name__ == "__main__":
    # Create the test node
    node = ParameterMessageTestNode()
    
    # Test parameter value changes
    print("Testing parameter value changes...")
    node.set_parameter_value("input_text", "Test Message")
    node.set_parameter_value("processing_mode", "reverse")
    
    # Test processing
    print("Testing processing...")
    result = node.process()
    print(f"Processing result: {result}")
    
    print("ParameterMessage test node demonstration completed!")