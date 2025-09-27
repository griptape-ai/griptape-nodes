import importlib
import inspect
import pkgutil
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.files.providers.artifact_load_provider import ArtifactLoadProvider
from griptape_nodes_library.files.providers.validation_result import ProviderValidationResult


class LoadFile(SuccessFailureNode):
    """Clean, streamlined universal file loader with provider instances."""

    AUTOMATIC_DETECTION = "Automatic Detection"

    def __init__(self, **kwargs) -> None:
        # Provider instance - this does all the heavy lifting
        self._current_provider: ArtifactLoadProvider | None = None
        # Dynamic parameters added by current provider (for cleanup)
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
        """Handle provider type changes - create new provider instance and configure."""
        if provider_value == LoadFile.AUTOMATIC_DETECTION:
            self._switch_to_automatic_detection()
        else:
            self._switch_to_specific_provider(provider_value)

    def _handle_path_change(self, path_value: Any) -> None:
        """Handle path changes - validate with current provider."""
        if not path_value:
            self._reset_all_parameters()
            return

        if not self._current_provider:
            self._set_status_results(was_successful=False, result_details="No provider available for validation")
            return

        try:
            current_values = self._get_current_parameter_values()
            result = self._current_provider.validate_from_path(str(path_value), current_values)
            self._apply_validation_result(result)
        except Exception as e:
            self._set_status_results(was_successful=False, result_details=f"Path validation failed: {e}")

    def _handle_artifact_change(self, artifact_value: Any) -> None:
        """Handle artifact changes - validate with current provider."""
        if artifact_value is None:
            self._reset_all_parameters()
            return

        if not self._current_provider:
            self._set_status_results(was_successful=False, result_details="No provider available for validation")
            return

        try:
            current_values = self._get_current_parameter_values()
            result = self._current_provider.validate_from_artifact(artifact_value, current_values)
            self._apply_validation_result(result)
        except Exception as e:
            self._set_status_results(was_successful=False, result_details=f"Artifact validation failed: {e}")

    def _switch_to_automatic_detection(self) -> None:
        """Switch to automatic detection mode."""
        # Configure artifact to accept all types
        self.artifact_parameter.type = ParameterTypeBuiltin.ALL.value
        self.artifact_parameter.output_type = ParameterTypeBuiltin.ALL.value
        self.artifact_parameter.input_types = [ParameterTypeBuiltin.ALL.value]
        self.artifact_parameter.ui_options["display_name"] = "File"

        # Remove current provider and its parameters
        self._clear_current_provider()

    def _switch_to_specific_provider(self, provider_name: str) -> None:
        """Switch to a specific provider by name."""
        provider_instance = self._create_provider_instance(provider_name)
        if not provider_instance:
            self._set_status_results(was_successful=False, result_details=f"Provider '{provider_name}' not found")
            return

        self._set_current_provider(provider_instance)

    def _apply_validation_result(self, result: ProviderValidationResult) -> None:
        """Apply validation result - either update all parameters or show errors."""
        if result.is_success:
            # Atomic update of all parameters
            self.artifact_parameter.default_value = result.artifact
            self.path_parameter.default_value = result.path

            # Update current provider with the new artifact state
            if self._current_provider:
                self._current_provider.artifact = result.artifact
                self._current_provider.internal_url = result.internal_url
                self._current_provider.path = result.path

            # Apply dynamic parameter updates
            for param_name, value in result.dynamic_parameter_updates.items():
                param = self.get_parameter_by_name(param_name)
                if param is None:
                    msg = f"Dynamic parameter '{param_name}' not found in LoadFile '{self.name}'"
                    raise RuntimeError(msg)
                param.default_value = value

            self._set_status_results(was_successful=True, result_details="File loaded successfully")
        else:
            # Show all error messages
            error_text = "; ".join(result.error_messages)
            self._set_status_results(was_successful=False, result_details=error_text)

    def _set_current_provider(self, provider: ArtifactLoadProvider) -> None:
        """Set current provider and configure artifact parameter."""
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
        """Clear current provider and remove its dynamic parameters."""
        # Remove dynamic parameters
        for param in self._dynamic_parameters[:]:
            try:
                self.remove_parameter_element_by_name(param.name)
                self._dynamic_parameters.remove(param)
            except KeyError as e:
                msg = f"Failed to remove dynamic parameter '{param.name}' from LoadFile '{self.name}'"
                raise RuntimeError(msg) from e

        self._current_provider = None

    def _reset_all_parameters(self) -> None:
        """Reset all file-related parameters."""
        self.artifact_parameter.default_value = None
        self.path_parameter.default_value = ""

        # Clear dynamic parameter values
        for param in self._dynamic_parameters:
            param.default_value = None

    def _get_current_parameter_values(self) -> dict[str, Any]:
        """Get current values of all parameters for provider context."""
        values = {}
        for param in self.parameters:
            values[param.name] = param.default_value
        return values

    def _get_provider_choices(self) -> list[str]:
        """Get available provider choices."""
        choices = [LoadFile.AUTOMATIC_DETECTION]
        providers = self._discover_all_providers()
        choices.extend(provider.provider_name for provider in providers)
        return choices

    def _create_provider_instance(self, provider_name: str) -> ArtifactLoadProvider | None:
        """Create provider instance by name."""
        providers = self._discover_all_providers()
        for provider in providers:
            if provider.provider_name == provider_name:
                return provider
        return None

    def _discover_all_providers(self) -> list[ArtifactLoadProvider]:
        """Discover all available provider instances."""
        provider_classes = self._discover_provider_classes()
        return [provider_class() for provider_class in provider_classes]

    def _discover_provider_classes(self) -> list[type[ArtifactLoadProvider]]:
        """Discover provider classes using subclass inspection."""
        self._import_provider_modules()
        return [subclass for subclass in ArtifactLoadProvider.__subclasses__() if not inspect.isabstract(subclass)]

    def _import_provider_modules(self) -> None:
        """Import all provider modules to ensure classes are registered."""
        provider_package = "griptape_nodes_library.files.providers"
        try:
            package = importlib.import_module(provider_package)

            for _, module_name, _ in pkgutil.walk_packages(package.__path__, f"{provider_package}."):
                importlib.import_module(module_name)
        except ImportError as e:
            msg = f"Failed to import provider modules from '{provider_package}': {e}"
            raise RuntimeError(msg) from e
