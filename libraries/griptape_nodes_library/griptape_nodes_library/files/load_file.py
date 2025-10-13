import logging
from pathlib import Path
from typing import Any

from griptape_nodes.exe_types.core_types import (
    NodeMessageResult,
    Parameter,
    ParameterMessage,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.context_events import (
    GetWorkflowContextRequest,
    GetWorkflowContextSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_provider import (
    ArtifactProvider,
    FileLocation,
    URLFileLocation,
)
from griptape_nodes_library.files.providers.image.image_provider import ImageProvider

logger = logging.getLogger("griptape_nodes")


class LoadFile(SuccessFailureNode):
    """Clean, streamlined universal file loader with provider instances."""

    AUTOMATIC_DETECTION = "Automatic Detection"

    def __init__(self, **kwargs) -> None:
        # Current provider instance
        self._current_provider: ArtifactProvider | None = None
        # Dynamic parameters added by current provider
        self._dynamic_parameters: list[Parameter] = []
        # Track current file location (for copy button, display)
        self._current_location: FileLocation | None = None
        # Prevents infinite loops during atomic parameter synchronization
        # When a core parameter changes, we atomically update all related parameters (file location, artifact, dynamic params)
        # This lock holds the name of the parameter that triggered the sync to prevent cascading change handlers
        # Example: user sets the file location parameter → lock="file_location", updates the parameter, then updates the artifact without causing separate set_parameter_value calls
        self._triggering_parameter_lock: str | None = None

        super().__init__(**kwargs)

        # Core parameters
        self.file_location_parameter = Parameter(
            name="file_location",
            type="str",
            default_value="",
            tooltip="Path to file or URL.",
            ui_options={"display_name": "File Location"},
            traits={
                FileSystemPicker(
                    allow_files=True,
                    allow_directories=False,
                    workspace_only=False,
                    file_extensions=[],
                )
            },
        )

        self.artifact_parameter = Parameter(
            name="artifact",
            type=ParameterTypeBuiltin.ANY.value,
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            tooltip="The loaded file artifact",
            ui_options={"expander": True, "display_name": "File Contents"},
            allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
        )

        self.provider_parameter = Parameter(
            name="provider_type",
            type="str",
            default_value=LoadFile.AUTOMATIC_DETECTION,
            tooltip="File type provider to use for loading",
            ui_options={"display_name": "File Type"},
        )
        self.provider_parameter.add_trait(Options(choices=self._get_provider_choices()))

        self.add_parameter(self.provider_parameter)

        # File status info message (hidden by default)
        # Shows for: external files (with copy button), errors, or URL downloads
        # Copy to Project button is added as trait
        copy_button = Button(
            label="Copy to Project", variant="secondary", size="default", on_click=self._on_copy_to_project_clicked
        )
        self.file_status_info_message = ParameterMessage(
            variant="info",
            value="",
            name="file_status_info",
            ui_options={"hide": True},
            button_text=None,
            button_link=None,
            traits={copy_button},
        )
        self.add_node_element(self.file_status_info_message)

        self.add_parameter(self.file_location_parameter)
        self.add_parameter(self.artifact_parameter)

        # Add status parameters
        self._create_status_parameters(
            result_details_tooltip="Details about the file loading operation result",
            result_details_placeholder="Details on the load attempt will be presented here.",
        )

    def set_parameter_value(
        self,
        param_name: str,
        value: Any,
        *,
        initial_setup: bool = False,
        emit_change: bool = True,
        skip_before_value_set: bool = False,
    ) -> None:
        """Override to handle parameter changes."""
        # Set the parameter value first
        super().set_parameter_value(
            param_name,
            value,
            initial_setup=initial_setup,
            emit_change=emit_change,
            skip_before_value_set=skip_before_value_set,
        )

        # Skip handling during initial setup
        if initial_setup:
            return

        # Skip if we're already in a sync operation to prevent infinite loops
        if self._triggering_parameter_lock is not None:
            return

        # Acquire lock - this parameter is triggering the atomic sync
        self._triggering_parameter_lock = param_name

        try:
            # Handle parameter changes
            if param_name == self.provider_parameter.name:
                self._handle_provider_change(value)
            elif param_name == self.file_location_parameter.name:
                self._handle_file_location_change(value)
        finally:
            # Always clear the triggering parameter lock
            self._triggering_parameter_lock = None

    def process(self) -> None:
        """Process file at execution time: revalidate and update if needed."""
        self._clear_execution_status()

        # Get current state
        artifact = self.get_parameter_value(self.artifact_parameter.name)
        file_location_value = self.get_parameter_value(self.file_location_parameter.name)

        # Assume failure until proven successful
        was_successful = False
        result_details = ""

        # Cascade through failure cases
        if not self._current_provider:
            result_details = (
                f"Failed to load file '{file_location_value}'. No file type handler available for this file format."
            )
        elif not self._current_location:
            if file_location_value:
                result_details = (
                    f"Failed to access file path: '{file_location_value}'. File path could not be determined or parsed."
                )
            else:
                result_details = "Failed to load file. No file path specified."
        elif not artifact:
            result_details = f"Failed to load file '{file_location_value}'. The file may be invalid or corrupted for the expected file type."
        else:
            # All checks passed - delegate to provider for revalidation
            current_values = self._get_current_parameter_values()
            result = self._current_provider.revalidate_for_execution(
                location=self._current_location,
                current_artifact=artifact,
                current_parameter_values=current_values,
            )

            if result.was_successful:
                # Always update artifact to ensure OUTPUT parameters are set for execution
                self.set_parameter_value(self.artifact_parameter.name, result.artifact)
                self.publish_update_to_parameter(self.artifact_parameter.name, result.artifact)

                # Update dynamic parameters (e.g., masks)
                for param_name, value in result.dynamic_parameter_updates.items():
                    self.set_parameter_value(param_name, value)
                    self.publish_update_to_parameter(param_name, value)

                was_successful = True
                result_details = result.result_details
            else:
                # Provider failed - pass through error message
                result_details = result.result_details

        # Set final status
        self._set_status_results(was_successful=was_successful, result_details=result_details)

    def _handle_provider_change(self, provider_value: str) -> None:
        """Switch between automatic detection and specific provider."""
        if provider_value == LoadFile.AUTOMATIC_DETECTION:
            self._switch_to_automatic_detection()
        else:
            self._switch_to_specific_provider(provider_value)

    def _handle_file_location_change(self, file_location_value: str) -> None:
        """Load file from file location (path or URL), detecting provider if needed."""
        # An empty file location is valid; clear everything.
        if not file_location_value:
            self._reset_all_parameters()
            return

        # If no current provider, try automatic detection
        if not self._current_provider:
            candidate_providers = self._get_candidate_providers_for_file_location_input(file_location_value)
            if candidate_providers:
                self._try_providers_for_file_location_input(
                    candidate_providers=candidate_providers,
                    file_location_input=file_location_value,
                )
            else:
                self._set_status_results(
                    was_successful=False, result_details="No suitable provider found for this file type"
                )
            return

        # Use current provider
        self._load_file_location_with_current_provider(file_location_input=file_location_value)

    def _switch_to_automatic_detection(self) -> None:
        """Enable automatic provider detection for all input types."""
        # Configure artifact for maximum flexibility
        self.artifact_parameter.type = ParameterTypeBuiltin.ANY.value
        self.artifact_parameter.output_type = ParameterTypeBuiltin.ALL.value
        self.artifact_parameter.input_types = [ParameterTypeBuiltin.ANY.value]
        self.artifact_parameter.ui_options["display_name"] = "File Contents"

        # Remove current provider
        self._clear_current_provider()

    def _switch_to_specific_provider(self, provider_name: str) -> None:
        """Configure node to use a specific provider."""
        provider_instance = self._create_provider_instance(provider_name)
        if not provider_instance:
            self._set_status_results(was_successful=False, result_details=f"Provider '{provider_name}' not found")
            return

        self._set_current_provider(provider_instance)

        # Process existing file location with the new provider
        current_file_location = self.file_location_parameter.default_value
        if current_file_location:
            self._load_file_location_with_current_provider(file_location_input=current_file_location)

    def _get_candidate_providers_for_file_location_input(self, file_location_input: str) -> list[ArtifactProvider]:
        """Find providers capable of loading from this file location."""
        candidates = []
        providers = self._get_all_providers()

        for provider in providers:
            if provider.can_handle_file_location(file_location_input):
                candidates.append(provider)  # noqa: PERF401

        return candidates

    def _try_providers_for_file_location_input(
        self,
        *,
        candidate_providers: list[ArtifactProvider],
        file_location_input: str,
    ) -> None:
        """Attempt loading with each provider until success."""
        for provider in candidate_providers:
            # Get parameter values specific to this provider
            current_values = self._get_current_parameter_values(provider=provider)
            result = provider.attempt_load_from_file_location(file_location_input, current_values)

            if result.was_successful:
                # Success! Set this provider as current and apply the result
                self._set_current_provider(provider)
                self._apply_validation_result(result)
                return

        # All providers failed
        self._set_status_results(
            was_successful=False, result_details="No provider could successfully process this file location input"
        )

    def _load_file_location_with_current_provider(self, *, file_location_input: str) -> None:
        """Process file location using the configured provider."""
        if not self._current_provider:
            return

        current_values = self._get_current_parameter_values()
        result = self._current_provider.attempt_load_from_file_location(file_location_input, current_values)
        self._apply_validation_result(result)

    def _apply_validation_result(self, result: Any) -> None:
        """Update node parameters from provider result."""
        if not self._current_provider:
            msg = "_apply_validation_result called without a current provider"
            raise RuntimeError(msg)

        if result.was_successful:
            self._current_location = result.location

            self.set_parameter_value(self.artifact_parameter.name, result.artifact)
            self.publish_update_to_parameter(self.artifact_parameter.name, result.artifact)

            # Lock provider selection when artifact is successfully loaded
            self.provider_parameter.settable = False

            file_location_str = self._current_provider.get_source_path(result.location) if result.location else ""
            self._update_file_location_display(file_location_str, result.location, self._current_provider)

            for param_name, value in result.dynamic_parameter_updates.items():
                param = self.get_parameter_by_name(param_name)
                if param is None:
                    msg = f"Provider attempted to update non-existent parameter '{param_name}'"
                    raise RuntimeError(msg)
                self.set_parameter_value(param_name, value)
                self.publish_update_to_parameter(param_name, value)

            # Show/hide info box based on file location
            if self._current_provider.is_location_external_to_project(result.location):
                detail = self._current_provider.get_location_display_detail(result.location)
                self.file_status_info_message.variant = "info"

                # Special handling for URLs to show "Downloaded from"
                if isinstance(result.location, URLFileLocation):
                    self.file_status_info_message.value = f"Downloaded from {detail}"
                else:
                    self.file_status_info_message.value = f"File not in project: {detail}"

                # Workaround: Set button_text on ParameterMessage to sync with Button trait label
                # TODO(https://github.com/griptape-ai/griptape-nodes/issues/2645): Fix button syncing
                self.file_status_info_message.button_text = "Copy to Project"
                self.show_message_by_name(self.file_status_info_message.name)
            else:
                self.hide_message_by_name(self.file_status_info_message.name)

            self._set_status_results(was_successful=True, result_details=result.result_details)
        else:
            self._current_location = None

            # Clear artifact on failure
            self.set_parameter_value(self.artifact_parameter.name, None)
            self.publish_update_to_parameter(self.artifact_parameter.name, None)

            # Unlock provider selection when artifact is cleared due to error
            self.provider_parameter.settable = True

            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = result.result_details
            self.file_status_info_message.ui_options = {"hide": False}

            self._set_status_results(was_successful=False, result_details=result.result_details)

    def _update_file_location_display(
        self, file_location_str: str, location: FileLocation | None, provider: ArtifactProvider
    ) -> None:
        """Update file location parameter value and tooltip based on location."""
        if location is None:
            display_value = file_location_str
            tooltip = file_location_str
        else:
            display_value = provider.get_display_path(location)
            tooltip = provider.get_source_path(location)

        self.set_parameter_value(self.file_location_parameter.name, display_value)
        self.publish_update_to_parameter(self.file_location_parameter.name, display_value)
        self.file_location_parameter.tooltip = tooltip

    def _generate_filename(self, source_location: FileLocation) -> str:
        """Generate collision-resistant filename using standard naming convention.

        Format: {workflow}_{node_name}_{parameter_name}_{original_base_name}{extension}

        Includes workflow name to prevent collisions when multiple workflows share
        the same project directory and copy files with the same name.

        Args:
            source_location: Source file location to extract original filename from

        Returns:
            Generated filename

        Raises:
            RuntimeError: If filename cannot be determined or workflow context unavailable
            ValueError: If file has no extension
        """
        # Get workflow name from context
        result = GriptapeNodes.handle_request(GetWorkflowContextRequest())
        if not isinstance(result, GetWorkflowContextSuccess):
            msg = f"Cannot generate filename: workflow context unavailable ({result.result_details})"
            raise RuntimeError(msg)  # noqa: TRY004

        if not result.workflow_name:
            msg = "Cannot generate filename: no workflow context set"
            raise RuntimeError(msg)

        workflow_name = result.workflow_name

        # Get original filename from location
        try:
            original_filename = source_location.get_filename()
        except (ValueError, NotImplementedError) as e:
            msg = f"Cannot determine filename from location: {e}"
            raise RuntimeError(msg) from e

        # Extract base name and extension
        base_name = Path(original_filename).stem
        extension = Path(original_filename).suffix

        if not extension:
            msg = f"Cannot generate filename without extension: {original_filename}"
            raise ValueError(msg)

        # Generate filename: {workflow}_{node_name}_{parameter_name}_{file_name}
        return f"{workflow_name}_{self.name}_{self.file_location_parameter.name}_{base_name}{extension}"

    def _on_copy_to_project_clicked(
        self,
        button: Button,
        button_details: Any,  # noqa: ARG002
    ) -> NodeMessageResult:
        """Handle Copy to Project button click with proper state management."""
        if not self._current_provider:
            return NodeMessageResult(success=False, details="No provider available", altered_workflow_state=False)

        if not self._current_location:
            return NodeMessageResult(success=False, details="No file location to copy", altered_workflow_state=False)

        # Set button to loading state
        button.state = "loading"
        button.loading_label = "Copying..."
        # Workaround: Set button_text on ParameterMessage to sync with Button trait label
        # TODO(https://github.com/griptape-ai/griptape-nodes/issues/2645): Fix button syncing
        self.file_status_info_message.button_text = "Copying..."

        # Generate destination location in inputs/
        try:
            filename = self._generate_filename(self._current_location)
            destination_location = ArtifactProvider.generate_workflow_file_location(
                subdirectory="inputs", filename=filename
            )
        except Exception as e:
            button.state = "normal"
            return NodeMessageResult(
                success=False, details=f"Failed to generate destination: {e}", altered_workflow_state=False
            )

        # Copy file to project
        try:
            artifact = self.get_parameter_value(self.artifact_parameter.name)
            project_location = self._current_provider.copy_file_location_to_disk(
                source_location=self._current_location,
                destination_location=destination_location,
                artifact=artifact,
            )
        except Exception as e:
            button.state = "normal"
            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = f"Copy failed: {e}"
            logger.exception("Copy to project failed")
            return NodeMessageResult(success=False, details=f"Copy failed: {e}", altered_workflow_state=False)

        # Update current location to the new project location
        self._current_location = project_location

        # Update file location parameter - this will trigger _handle_file_location_change
        # which will call _apply_validation_result and handle message visibility
        file_location_str = self._current_provider.get_source_path(project_location)
        self.set_parameter_value(self.file_location_parameter.name, file_location_str)
        self.publish_update_to_parameter(self.file_location_parameter.name, file_location_str)

        # Reset button state
        button.state = "normal"

        return NodeMessageResult(
            success=True, details=f"File copied to project: {file_location_str}", altered_workflow_state=True
        )

    def _set_current_provider(self, provider: ArtifactProvider) -> None:
        """Install provider and configure its dynamic parameters."""
        # Remove old provider parameters
        self._clear_current_provider()

        # Set new provider
        self._current_provider = provider

        # Update provider dropdown to reflect the selected provider
        self.set_parameter_value(self.provider_parameter.name, provider.provider_name)
        self.publish_update_to_parameter(self.provider_parameter.name, provider.provider_name)

        # Configure artifact parameter for this provider
        details = provider.get_artifact_parameter_details()
        self.artifact_parameter.type = details.type
        self.artifact_parameter.output_type = details.output_type
        self.artifact_parameter.input_types = details.input_types

        # Update ui_options using the pattern from other nodes - reassign the entire dict
        ui_options = self.artifact_parameter.ui_options

        provider_ui_options = provider.get_artifact_ui_options()
        ui_options.update(provider_ui_options)

        # Reassign the entire dict - this is the key step other nodes do
        self.artifact_parameter.ui_options = ui_options

        # Add provider-specific parameters
        for param in provider.get_additional_parameters():
            self.add_parameter(param)
            self._dynamic_parameters.append(param)

    def _clear_current_provider(self) -> None:
        """Remove current provider and clean up dynamic parameters."""
        # Remove dynamic parameters
        for param in self._dynamic_parameters[:]:
            try:
                self.remove_parameter_element_by_name(param.name)
                self._dynamic_parameters.remove(param)
            except KeyError as e:
                # This indicates inconsistent internal state - should not happen
                msg = f"Dynamic parameter '{param.name}' not found during cleanup - internal state inconsistency"
                raise RuntimeError(msg) from e

        self._current_provider = None

    def _reset_all_parameters(self) -> None:
        """Clear file inputs and dynamic parameter values."""
        self.artifact_parameter.default_value = None
        self.file_location_parameter.default_value = ""

        # Unlock provider selection when artifact is cleared
        self.provider_parameter.settable = True

        # Clear dynamic parameter values
        for param in self._dynamic_parameters:
            param.default_value = None

    def _get_current_parameter_values(self, *, provider: ArtifactProvider | None = None) -> dict[str, Any]:
        """Collect parameter values for provider processing.

        Only collects values for the provider's dynamic parameters to avoid sending unnecessary data.

        Args:
            provider: Optional specific provider to get values for. If not provided, uses self._current_provider.
        """
        values = {}
        target_provider = provider or self._current_provider
        if target_provider:
            # Only get values for the provider's dynamic parameters
            for param in target_provider.get_additional_parameters():
                values[param.name] = self.get_parameter_value(param.name)
        return values

    def _get_provider_choices(self) -> list[str]:
        """Build list of selectable provider names."""
        choices = [LoadFile.AUTOMATIC_DETECTION]
        providers = self._get_all_providers()
        choices.extend(provider.provider_name for provider in providers)
        return choices

    def _create_provider_instance(self, provider_name: str) -> ArtifactProvider | None:
        """Instantiate provider matching the given name."""
        providers = self._get_all_providers()
        for provider in providers:
            if provider.provider_name == provider_name:
                return provider
        return None

    def _get_all_providers(self) -> list[ArtifactProvider]:
        """Create instances of all supported providers."""
        # Explicit provider list - add new providers here
        return [
            ImageProvider(node=self, path_parameter=self.file_location_parameter),
        ]
