"""Segment classes for representing parsed macro templates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.common.macro_parser.formats import FormatSpec


MacroVariables = dict[str, str | int]


class SequenceTokenSyntax(StrEnum):
    """Which surface form a sequence token was authored as.

    Preserved so resolved templates can be round-tripped back to the exact
    string the author wrote (e.g., when handing an unexpanded pattern to
    a downstream tool like Nuke).
    """

    HASH = "hash"  # `#`, `##`, `####`, etc.
    PRINTF = "printf"  # `%d`, `%04d`, `%4d`, etc.


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


@dataclass
class ParsedSequenceToken(ParsedSegment):
    """Nuke-style image-sequence token (`####` or `%04d`).

    Represents the frame-number placeholder in a filename pattern. A template
    may contain at most one sequence token. The token binds to an integer
    frame number supplied at render time (write) or extracted from disk at
    scan time (read).

    Read/write asymmetry is intentional and mirrors Nuke:
        - Render (write): pad to declared `width` with overflow allowed.
          Frame 5 with width 4 -> "0005". Frame 12345 with width 4 -> "12345".
        - Scan (read): declared `width` is a *minimum*. `####` matches any
          integer with at least 4 digits. Width 1 effectively matches any
          non-negative integer.

    TODO: verify against Nuke source (duplicate-frame resolution, width
    semantics, negative-frame handling). See plan file for the open questions
    dispatched to the Nuke team.

    Attributes:
        width: Declared padding width. 4 for `####` or `%04d`. 1 for `#`.
            0 for `%d` (unpadded / variable-width).
        original_syntax: "hash" if authored as `#+`, "printf" if authored as
            `%d` / `%0Nd`. Preserved so `resolve()` can render the token back
            to its original form when no frame is supplied (for handing the
            pattern to a downstream tool like Nuke itself).
    """

    width: int
    original_syntax: SequenceTokenSyntax

    def to_literal(self) -> str:
        """Reconstruct the token's original source form for round-tripping.

        Returns the literal string that would re-parse into an equivalent
        token. Used when resolving a sequence template without expanding the
        frame (e.g., to hand the unexpanded pattern to Nuke).
        """
        match self.original_syntax:
            case SequenceTokenSyntax.HASH:
                return "#" * max(self.width, 1)
            case SequenceTokenSyntax.PRINTF:
                if self.width == 0:
                    return "%d"
                return f"%0{self.width}d"
            case _:
                msg = f"Unknown sequence token syntax: {self.original_syntax}"
                raise ValueError(msg)

    def render_frame(self, frame: int) -> str:
        """Render a concrete frame number into this token's padding.

        Pads to declared width; overflow allowed (frame 12345 with width 4
        renders as "12345"). Width 0 is unpadded. For negative frames, the
        sign is prepended *in addition to* the padding (frame -5 with width 4
        renders as "-0005", not "-005"), matching Nuke's write semantics.
        """
        if self.width <= 0:
            return str(frame)
        if frame < 0:
            return f"-{abs(frame):0{self.width}d}"
        return f"{frame:0{self.width}d}"
