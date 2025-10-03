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
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.file_system_picker import FileSystemPicker
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_load_provider import (
    ArtifactLoadProvider,
    ExternalFileLocation,
    FileLocation,
)
from griptape_nodes_library.files.providers.image.image_loader import ImageLoadProvider

logger = logging.getLogger("griptape_nodes")


class LoadFile(SuccessFailureNode):
    """Clean, streamlined universal file loader with provider instances."""

    AUTOMATIC_DETECTION = "Automatic Detection"

    def __init__(self, **kwargs) -> None:
        # Current provider instance
        self._current_provider: ArtifactLoadProvider | None = None
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
            input_types=[ParameterTypeBuiltin.ANY.value],
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
            ui_options={"display_name": "Provider Type"},
        )
        self.provider_parameter.add_trait(Options(choices=self._get_provider_choices()))

        self.add_parameter(self.provider_parameter)

        # File status info message (hidden by default)
        # Shows for: external files (with copy button), errors, or future URL downloads
        # Copy to Workspace button is added as trait
        copy_button = Button(
            label="Copy to Workspace", variant="secondary", size="default", on_click=self._on_copy_to_workspace_clicked
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
            elif param_name == self.artifact_parameter.name:
                self._handle_artifact_change(value)
        finally:
            # Always clear the triggering parameter lock
            self._triggering_parameter_lock = None

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

    def _handle_artifact_change(self, artifact_value: Any) -> None:
        """Process artifact input, detecting provider if needed."""
        if artifact_value is None:
            self._reset_all_parameters()
            return

        # If no current provider, try automatic detection
        if not self._current_provider:
            candidate_providers = self._get_candidate_providers_for_artifact_input(artifact_value)
            if candidate_providers:
                self._try_providers_for_artifact_input(
                    candidate_providers=candidate_providers, artifact_input=artifact_value
                )
            else:
                self._set_status_results(
                    was_successful=False, result_details="No suitable provider found for this artifact type"
                )
            return

        # Use current provider
        self._load_artifact_with_current_provider(artifact_input=artifact_value)

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

        # Process existing inputs with the new provider
        current_file_location = self.file_location_parameter.default_value
        current_artifact = self.artifact_parameter.default_value

        if current_file_location:
            self._load_file_location_with_current_provider(file_location_input=current_file_location)
        elif current_artifact:
            self._load_artifact_with_current_provider(artifact_input=current_artifact)

    def _get_candidate_providers_for_file_location_input(self, file_location_input: str) -> list[ArtifactLoadProvider]:
        """Find providers capable of loading from this file location."""
        candidates = []
        providers = self._get_all_providers()

        for provider in providers:
            if provider.can_handle_file_location(file_location_input):
                candidates.append(provider)  # noqa: PERF401

        return candidates

    def _get_candidate_providers_for_artifact_input(self, artifact_input: Any) -> list[ArtifactLoadProvider]:
        """Find providers capable of processing this artifact."""
        candidates = []
        providers = self._get_all_providers()

        for provider in providers:
            if provider.can_handle_artifact(artifact_input):
                candidates.append(provider)  # noqa: PERF401

        return candidates

    def _try_providers_for_file_location_input(
        self,
        *,
        candidate_providers: list[ArtifactLoadProvider],
        file_location_input: str,
    ) -> None:
        """Attempt loading with each provider until success."""
        current_values = self._get_current_parameter_values()

        for provider in candidate_providers:
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

    def _try_providers_for_artifact_input(
        self, *, candidate_providers: list[ArtifactLoadProvider], artifact_input: Any
    ) -> None:
        """Attempt processing with each provider until success."""
        current_values = self._get_current_parameter_values()

        for provider in candidate_providers:
            result = provider.attempt_load_from_artifact(artifact_input, current_values)
            if result.was_successful:
                # Success! Set this provider as current and apply the result
                self._set_current_provider(provider)
                self._apply_validation_result(result)
                return

        # All providers failed
        self._set_status_results(
            was_successful=False, result_details="No provider could successfully process this artifact input"
        )

    def _load_file_location_with_current_provider(self, *, file_location_input: str) -> None:
        """Process file location using the configured provider."""
        if not self._current_provider:
            return

        current_values = self._get_current_parameter_values()
        result = self._current_provider.attempt_load_from_file_location(file_location_input, current_values)
        self._apply_validation_result(result)

    def _load_artifact_with_current_provider(self, *, artifact_input: Any) -> None:
        """Process artifact input using the configured provider."""
        if not self._current_provider:
            return

        current_values = self._get_current_parameter_values()
        result = self._current_provider.attempt_load_from_artifact(artifact_input, current_values)
        self._apply_validation_result(result)

    def _apply_validation_result(self, result: Any) -> None:
        """Update node parameters from provider result."""
        if result.was_successful:
            self._current_location = result.location

            self.set_parameter_value(self.artifact_parameter.name, result.artifact)
            self.publish_update_to_parameter(self.artifact_parameter.name, result.artifact)

            self._update_file_location_display(
                result.location.get_source_path() if result.location else "", result.location
            )

            for param_name, value in result.dynamic_parameter_updates.items():
                param = self.get_parameter_by_name(param_name)
                if param is None:
                    msg = f"Provider attempted to update non-existent parameter '{param_name}'"
                    raise RuntimeError(msg)
                self.set_parameter_value(param_name, value)
                self.publish_update_to_parameter(param_name, value)

            if isinstance(result.location, ExternalFileLocation):
                self.file_status_info_message.variant = "info"
                self.file_status_info_message.value = "File outside workspace."
                self.file_status_info_message.ui_options = {"hide": False}
            else:
                self.file_status_info_message.ui_options = {"hide": True}

            self._set_status_results(was_successful=True, result_details=result.result_details)
        else:
            self._current_location = None

            # Clear artifact on failure
            self.set_parameter_value(self.artifact_parameter.name, None)
            self.publish_update_to_parameter(self.artifact_parameter.name, None)

            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = result.result_details
            self.file_status_info_message.ui_options = {"hide": False}

            self._set_status_results(was_successful=False, result_details=result.result_details)

    def _update_file_location_display(self, file_location_str: str, location: FileLocation | None) -> None:
        """Update file location parameter value and tooltip based on location."""
        if location is None:
            display_value = file_location_str
            tooltip = file_location_str
        else:
            display_value = location.get_display_path()
            tooltip = location.get_source_path()

        self.set_parameter_value(self.file_location_parameter.name, display_value)
        self.publish_update_to_parameter(self.file_location_parameter.name, display_value)
        self.file_location_parameter.tooltip = tooltip

    def _on_copy_to_workspace_clicked(self, button: Button, button_details: Any) -> NodeMessageResult:  # noqa: ARG002
        """Handle Copy to Workspace button click with proper state management."""
        if not isinstance(self._current_location, ExternalFileLocation):
            return NodeMessageResult(
                success=False, details="No valid external file to copy", altered_workflow_state=False
            )

        external_file_path = self._current_location.get_filesystem_path()
        if not external_file_path.exists():
            return NodeMessageResult(
                success=False, details=f"File not found: {external_file_path}", altered_workflow_state=False
            )

        # Set button to loading state
        button.state = "loading"
        button.loading_label = "Copying..."

        try:
            # Read file bytes
            file_bytes = external_file_path.read_bytes()

            # Generate proper filename using ArtifactLoadProvider protocol
            original_filename = external_file_path.name
            generated_filename = ArtifactLoadProvider.generate_upload_filename(
                workflow_name=GriptapeNodes.ContextManager().get_current_workflow_name(),
                node_name=self.name,
                parameter_name=self.file_location_parameter.name,
                original_filename=original_filename,
            )

            # Save to workspace uploads directory using StaticFilesManager
            upload_path = f"uploads/{generated_filename}"
            GriptapeNodes.StaticFilesManager().save_static_file(file_bytes, upload_path)

            # Calculate workspace-relative filesystem path
            # StaticFilesManager saves relative to workspace + workflow directory
            workspace_path = GriptapeNodes.ConfigManager().workspace_path
            workflow_name = GriptapeNodes.ContextManager().get_current_workflow_name()

            # Construct workflow filesystem path (same approach as image_loader.py)
            workflow_file_path = f"{workflow_name}.py"
            full_workflow_path = workspace_path / workflow_file_path

            if full_workflow_path.exists():
                # Get workflow directory and make relative to workspace
                workflow_dir = full_workflow_path.parent
                relative_workflow_dir = workflow_dir.relative_to(workspace_path)
                relative_path = relative_workflow_dir / "staticfiles" / "uploads" / generated_filename
            else:
                # Fallback: assume staticfiles/uploads from workspace root
                relative_path = Path("staticfiles") / "uploads" / generated_filename

            # Update file location parameter to workspace-relative filesystem path string
            file_location_str = str(relative_path)
            self.set_parameter_value(self.file_location_parameter.name, file_location_str)
            self.publish_update_to_parameter(self.file_location_parameter.name, file_location_str)

            # Trigger re-processing with new location (will update artifact, hide message)
            # This happens automatically via set_parameter_value triggering _handle_file_location_change

            # Reset button state
            button.state = "normal"

            return NodeMessageResult(
                success=True, details=f"File copied to workspace: {relative_path}", altered_workflow_state=True
            )

        except FileNotFoundError as e:
            button.state = "normal"
            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = f"File not found: {e}"
            return NodeMessageResult(success=False, details=f"File not found: {e}", altered_workflow_state=False)
        except PermissionError as e:
            button.state = "normal"
            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = f"Permission denied: {e}"
            return NodeMessageResult(success=False, details=f"Permission denied: {e}", altered_workflow_state=False)
        except Exception as e:
            button.state = "normal"
            self.file_status_info_message.variant = "error"
            self.file_status_info_message.value = f"Copy failed: {e}"
            logger.exception("Copy to workspace failed")
            return NodeMessageResult(success=False, details=f"Copy failed: {e}", altered_workflow_state=False)

    def _set_current_provider(self, provider: ArtifactLoadProvider) -> None:
        """Install provider and configure its dynamic parameters."""
        # Remove old provider parameters
        self._clear_current_provider()

        # Set new provider
        self._current_provider = provider

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

        # Clear dynamic parameter values
        for param in self._dynamic_parameters:
            param.default_value = None

    def _get_current_parameter_values(self) -> dict[str, Any]:
        """Collect parameter values for provider processing."""
        values = {}
        for param in self.parameters:
            values[param.name] = param.default_value
        return values

    def _get_provider_choices(self) -> list[str]:
        """Build list of selectable provider names."""
        choices = [LoadFile.AUTOMATIC_DETECTION]
        providers = self._get_all_providers()
        choices.extend(provider.provider_name for provider in providers)
        return choices

    def _create_provider_instance(self, provider_name: str) -> ArtifactLoadProvider | None:
        """Instantiate provider matching the given name."""
        providers = self._get_all_providers()
        for provider in providers:
            if provider.provider_name == provider_name:
                return provider
        return None

    def _get_all_providers(self) -> list[ArtifactLoadProvider]:
        """Create instances of all supported providers."""
        # Explicit provider list - add new providers here
        return [
            ImageLoadProvider(node=self, path_parameter=self.file_location_parameter),
        ]
