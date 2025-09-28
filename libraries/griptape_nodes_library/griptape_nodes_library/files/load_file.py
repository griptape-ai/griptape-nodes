from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.path_utils import PathUtils
from griptape_nodes_library.files.providers.artifact_load_provider import ArtifactLoadProvider
from griptape_nodes_library.files.providers.image.image_loader import ImageLoadProvider


class LoadFile(SuccessFailureNode):
    """Clean, streamlined universal file loader with provider instances."""

    AUTOMATIC_DETECTION = "Automatic Detection"

    def __init__(self, **kwargs) -> None:
        # Current provider instance
        self._current_provider: ArtifactLoadProvider | None = None
        # Dynamic parameters added by current provider
        self._dynamic_parameters: list[Parameter] = []

        super().__init__(**kwargs)

        # Core parameters
        self.provider_parameter = Parameter(
            name="provider_type",
            type="str",
            default_value=LoadFile.AUTOMATIC_DETECTION,
            tooltip="File type provider to use for loading",
            ui_options={"display_name": "Provider Type"},
        )
        self.provider_parameter.add_trait(Options(choices=self._get_provider_choices()))

        self.path_parameter = Parameter(
            name="path",
            type="str",
            default_value="",
            tooltip="Path to a local file or URL to load",
            ui_options={"display_name": "File Path or URL"},
        )

        self.artifact_parameter = Parameter(
            name="artifact",
            input_types=[ParameterTypeBuiltin.ALL.value],
            type=ParameterTypeBuiltin.ALL.value,
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            tooltip="The loaded file artifact",
            ui_options={"expander": True, "display_name": "File"},
        )

        self.add_parameter(self.provider_parameter)
        self.add_parameter(self.path_parameter)
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

        # Handle parameter changes
        if param_name == self.provider_parameter.name:
            self._handle_provider_change(value)
        elif param_name == self.path_parameter.name:
            self._handle_path_change(value)
        elif param_name == self.artifact_parameter.name:
            self._handle_artifact_change(value)

    def _handle_provider_change(self, provider_value: str) -> None:
        """Switch between automatic detection and specific provider."""
        if provider_value == LoadFile.AUTOMATIC_DETECTION:
            self._switch_to_automatic_detection()
        else:
            self._switch_to_specific_provider(provider_value)

    def _handle_path_change(self, path_value: Any) -> None:
        """Load file from path, detecting provider if needed."""
        if not path_value:
            self._reset_all_parameters()
            return

        # If no current provider, try automatic detection
        if not self._current_provider:
            candidate_providers = self._get_candidate_providers_for_path_input(path_value)
            if candidate_providers:
                self._try_providers_for_path_input(candidate_providers=candidate_providers, path_input=path_value)
            else:
                self._set_status_results(
                    was_successful=False, result_details="No suitable provider found for this file type"
                )
            return

        # Use current provider
        self._load_path_with_current_provider(path_input=path_value)

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
        # Configure artifact to accept all types
        self.artifact_parameter.type = ParameterTypeBuiltin.ALL.value
        self.artifact_parameter.output_type = ParameterTypeBuiltin.ALL.value
        self.artifact_parameter.input_types = [ParameterTypeBuiltin.ALL.value]
        self.artifact_parameter.ui_options["display_name"] = "File"

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
        current_path = self.path_parameter.default_value
        current_artifact = self.artifact_parameter.default_value

        if current_path:
            self._load_path_with_current_provider(path_input=current_path)
        elif current_artifact:
            self._load_artifact_with_current_provider(artifact_input=current_artifact)

    def _get_candidate_providers_for_path_input(self, path_input: str) -> list[ArtifactLoadProvider]:
        """Find providers capable of loading from this path."""
        candidates = []
        providers = self._get_all_providers()

        for provider in providers:
            if PathUtils.is_url(path_input):
                if provider.can_handle_url(path_input):
                    candidates.append(provider)
            elif provider.can_handle_path(path_input):
                candidates.append(provider)

        return candidates

    def _get_candidate_providers_for_artifact_input(self, artifact_input: Any) -> list[ArtifactLoadProvider]:
        """Find providers capable of processing this artifact."""
        candidates = []
        providers = self._get_all_providers()

        for provider in providers:
            if provider.can_handle_artifact(artifact_input):
                candidates.append(provider)  # noqa: PERF401

        return candidates

    def _try_providers_for_path_input(
        self, *, candidate_providers: list[ArtifactLoadProvider], path_input: str
    ) -> None:
        """Attempt loading with each provider until success."""
        current_values = self._get_current_parameter_values()

        for provider in candidate_providers:
            result = provider.attempt_load_from_path(path_input, current_values)
            if result.was_successful:
                # Success! Set this provider as current and apply the result
                self._set_current_provider(provider)
                self._apply_validation_result(result)
                return

        # All providers failed
        self._set_status_results(
            was_successful=False, result_details="No provider could successfully process this path input"
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

    def _load_path_with_current_provider(self, *, path_input: str) -> None:
        """Process path input using the configured provider."""
        if not self._current_provider:
            return

        current_values = self._get_current_parameter_values()
        if PathUtils.is_url(path_input):
            result = self._current_provider.attempt_load_from_url(path_input, current_values)
        else:
            result = self._current_provider.attempt_load_from_path(path_input, current_values)
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
            # Update parameters with proper notifications
            self.set_parameter_value(self.artifact_parameter.name, result.artifact)
            self.publish_update_to_parameter(self.artifact_parameter.name, result.artifact)

            self.set_parameter_value(self.path_parameter.name, result.path)
            self.publish_update_to_parameter(self.path_parameter.name, result.path)

            # Apply dynamic parameter updates with proper notifications
            for param_name, value in result.dynamic_parameter_updates.items():
                param = self.get_parameter_by_name(param_name)
                if param is None:
                    msg = f"Provider attempted to update non-existent parameter '{param_name}' - provider/node state inconsistency"
                    raise RuntimeError(
                        msg
                    )
                self.set_parameter_value(param_name, value)
                self.publish_update_to_parameter(param_name, value)

            self._set_status_results(was_successful=True, result_details=result.result_details)
        else:
            # Use result details directly
            self._set_status_results(was_successful=False, result_details=result.result_details)

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
        self.artifact_parameter.ui_options["display_name"] = details.display_name
        self.artifact_parameter.ui_options.update(provider.get_artifact_ui_options())

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
        self.path_parameter.default_value = ""

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
            ImageLoadProvider(node=self, path_parameter=self.path_parameter),
        ]
