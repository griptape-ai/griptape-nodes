"""ParameterSplat component for splat inputs with enhanced UI options."""

from collections.abc import Callable
from typing import Any

from griptape_nodes_library.splat.splat_artifact import SplatUrlArtifact  # pyright: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import BadgeData, Parameter, ParameterMode, Trait
from griptape_nodes.utils.artifact_normalization import normalize_artifact_input


class ParameterSplat(Parameter):
    """A specialized Parameter class for splat inputs with enhanced UI options."""

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | None = None,
        *,
        type: str = "SplatUrlArtifact",  # noqa: A002, ARG002
        input_types: list[str] | None = None,  # noqa: ARG002
        output_type: str = "SplatUrlArtifact",  # noqa: ARG002
        default_value: Any = None,
        tooltip_as_input: str | None = None,
        tooltip_as_property: str | None = None,
        tooltip_as_output: str | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        traits: set[type[Trait] | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        ui_options: dict | None = None,
        pulse_on_run: bool = False,
        clickable_file_browser: bool = True,
        expander: bool = False,
        accept_any: bool = True,
        hide: bool | None = None,
        hide_label: bool = False,
        hide_property: bool = False,
        allow_input: bool = True,
        allow_property: bool = True,
        allow_output: bool = True,
        settable: bool = True,
        serializable: bool = True,
        user_defined: bool = False,
        private: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
        parent_container_name: str | None = None,
        badge: BadgeData | None = None,
    ) -> None:
        if ui_options is None:
            ui_options = {}
        else:
            ui_options = ui_options.copy()

        if pulse_on_run:
            ui_options["pulse_on_run"] = pulse_on_run
        if clickable_file_browser:
            ui_options["clickable_file_browser"] = clickable_file_browser
        if expander:
            ui_options["expander"] = expander

        if not allow_input and not allow_property and clickable_file_browser:
            ui_options.pop("clickable_file_browser", None)

        if accept_any:
            final_input_types = ["any"]
        else:
            final_input_types = ["SplatUrlArtifact"]

        splat_converters = list(converters) if converters else []
        if accept_any:
            def _normalize_splat(value: Any) -> Any:
                return normalize_artifact_input(value, SplatUrlArtifact)

            splat_converters.insert(0, _normalize_splat)

        super().__init__(
            name=name,
            tooltip=tooltip,
            type="SplatUrlArtifact",
            input_types=final_input_types,
            output_type="SplatUrlArtifact",
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            traits=traits,
            converters=splat_converters,
            validators=validators,
            ui_options=ui_options,
            hide=hide,
            hide_label=hide_label,
            hide_property=hide_property,
            allow_input=allow_input,
            allow_property=allow_property,
            allow_output=allow_output,
            settable=settable,
            serializable=serializable,
            user_defined=user_defined,
            private=private,
            element_id=element_id,
            element_type=element_type,
            parent_container_name=parent_container_name,
            badge=badge,
        )
