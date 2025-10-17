"""Segment classes for representing parsed macro templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.common.macro_parser.formats import FormatSpec


class VariableInfo(NamedTuple):
    """Metadata about a variable in a macro template.

    Attributes:
        name: Variable name (e.g., "workflow_name", "file_name")
        is_required: True if variable is required (not marked with ?)
    """

    name: str
    is_required: bool


@dataclass
class ParsedSegment:
    """Base class for template segments."""


@dataclass
class ParsedStaticValue(ParsedSegment):
    """Static text segment in template."""

    text: str


@dataclass
class ParsedVariable(ParsedSegment):
    """Variable segment in template."""

    info: VariableInfo  # name + is_required
    format_specs: list[FormatSpec]  # Applied in order during resolution
    default_value: str | None  # From {var|default} syntax
