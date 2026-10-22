"""Compact parameter specs for a compact DescribeNodeTypeRequest, and the cache that keeps them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.core_types import ParameterList, ParameterMode
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.library_events import NodeTypeParameterSpec
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter

# Longest note a compact spec carries. Long enough for the sentence that says what a parameter is
# for, short enough that the specs of several hundred node types stay small.
NOTE_MAX_CHARS = 200
NOTE_ELLIPSIS = "…"

# Tooltip prefix that marks a parameter kept only so older workflows still load, as in
# "Deprecated. Use images." Libraries have no structured field for this.
DEPRECATED_TOOLTIP_PREFIX = "deprecated"

# The ui_options key a MultiOptions trait writes its settings under, choices included.
MULTI_OPTIONS_UI_KEY = "multi_options"

# Mode names in the order a spec lists them.
MODE_NAMES: dict[ParameterMode, str] = {
    ParameterMode.INPUT: "input",
    ParameterMode.PROPERTY: "property",
    ParameterMode.OUTPUT: "output",
}


class NodeTypeSpecCache:
    """Compact parameter specs per node type, kept until any library or node type registration changes.

    Specs are keyed by library and node type. The whole cache is dropped as soon as
    `LibraryRegistry.get_generation` moves, which every load, reload, unload and sandbox
    re-registration does, so a spec is never served for a node class that is no longer registered.
    """

    def __init__(self) -> None:
        self._generation = LibraryRegistry.get_generation()
        self._specs: dict[str, dict[str, list[NodeTypeParameterSpec]]] = {}

    def get(self, library_name: str, node_type: str) -> list[NodeTypeParameterSpec] | None:
        """The cached specs for a node type, or None when there are none for the current registrations."""
        self._drop_if_registrations_changed()
        return self._specs.get(library_name, {}).get(node_type)

    def put(self, library_name: str, node_type: str, specs: list[NodeTypeParameterSpec], *, generation: int) -> None:
        """Keep a node type's specs, built while the registry was at `generation`.

        Specs built before a registration change are discarded rather than kept, since they may
        describe a node class that has since been replaced.

        Args:
            library_name: Library that provides the node type
            node_type: Name of the node type
            specs: The node type's parameter specs
            generation: `LibraryRegistry.get_generation()` read before the specs were built
        """
        self._drop_if_registrations_changed()
        if generation != self._generation:
            return
        self._specs.setdefault(library_name, {})[node_type] = specs

    def _drop_if_registrations_changed(self) -> None:
        current_generation = LibraryRegistry.get_generation()
        if current_generation == self._generation:
            return
        self._specs.clear()
        self._generation = current_generation


def build_parameter_spec(param: Parameter) -> NodeTypeParameterSpec:
    """Reduce a live parameter to its compact spec."""
    tooltip = param.tooltip
    return NodeTypeParameterSpec(
        name=param.name,
        type=param.type,
        input_types=list(param.input_types or []),
        output_type=param.output_type or "",
        modes=[mode_name for mode, mode_name in MODE_NAMES.items() if mode in param.allowed_modes],
        default=param.default_value,
        options=_options_from_ui_options(param.ui_options),
        multi_input=isinstance(param, ParameterList),
        deprecated=_tooltip_marks_deprecated(tooltip),
        note=_note_from_tooltip(tooltip),
    )


def _options_from_ui_options(ui_options: dict[str, Any]) -> list | None:
    """The choices a dropdown or multi-select offers, or None when the parameter is neither.

    Read from ui_options, which carries the choices of an attached Options or MultiOptions trait as
    well as ones a library wrote into ui_options directly.
    """
    for choices_key in Options.CHOICES_KEYS:
        choices = ui_options.get(choices_key)
        if isinstance(choices, list):
            return list(choices)

    multi_options = ui_options.get(MULTI_OPTIONS_UI_KEY)
    if not isinstance(multi_options, dict):
        return None
    choices = multi_options.get("choices")
    if not isinstance(choices, list):
        return None
    return list(choices)


def _tooltip_marks_deprecated(tooltip: str | list[dict]) -> bool:
    if not isinstance(tooltip, str):
        return False
    return tooltip.lstrip().lower().startswith(DEPRECATED_TOOLTIP_PREFIX)


def _note_from_tooltip(tooltip: str | list[dict]) -> str | None:
    """The tooltip text cut to `NOTE_MAX_CHARS`, at a word boundary where there is one."""
    if not isinstance(tooltip, str):
        return None
    text = " ".join(tooltip.split())
    if not text:
        return None
    if len(text) <= NOTE_MAX_CHARS:
        return text

    cut = text[: NOTE_MAX_CHARS - len(NOTE_ELLIPSIS)]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip(" ,;:.") + NOTE_ELLIPSIS
