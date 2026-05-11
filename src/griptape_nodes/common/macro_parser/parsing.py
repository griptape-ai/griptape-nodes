"""Parsing logic for macro templates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from griptape_nodes.common.macro_parser.exceptions import MacroParseFailureReason, MacroSyntaxError
from griptape_nodes.common.macro_parser.formats import (
    FORMAT_REGISTRY,
    DateFormat,
    FormatSpec,
    NumericPaddingFormat,
    SeparatorFormat,
)
from griptape_nodes.common.macro_parser.segments import (
    ParsedSegment,
    ParsedSequenceToken,
    ParsedStaticValue,
    ParsedVariable,
    SequenceTokenSyntax,
    VariableInfo,
)

# Nuke printf sequence token: %d, %04d, %4d, etc. Width is optional; leading
# zero is optional but conventional (both `%4d` and `%04d` are accepted; both
# produce zero-padded output on render).
_PRINTF_SEQUENCE_RE = re.compile(r"%(0?\d*)d")


@dataclass
class _NextBrace:
    """Next `{` position in the template."""

    start: int


@dataclass
class _NextSequence:
    """Next sequence token in the template, already parsed into a segment."""

    start: int
    end: int
    segment: ParsedSequenceToken


_NextSpecial = _NextBrace | _NextSequence


def parse_segments(template: str) -> list[ParsedSegment]:
    """Parse template into alternating static/variable/sequence segments.

    Args:
        template: Template string to parse

    Returns:
        List of ParsedSegment (static, variable, and sequence tokens)

    Raises:
        MacroSyntaxError: If template syntax is invalid, including multiple
            sequence tokens in a single template.
    """
    segments: list[ParsedSegment] = []
    sequence_token_positions: list[int] = []
    current_pos = 0

    while current_pos < len(template):
        # Find the next "special" position in what follows: either an opening
        # brace, or a sequence token (hash or printf). Sequence tokens are
        # only recognized OUTSIDE braces; inside braces, `#` is treated as
        # text (via SeparatorFormat) and `%` introduces a DateFormat pattern.
        next_special = _find_next_special(template, current_pos)

        if next_special is None:
            # No more specials, rest is static text
            static_text = template[current_pos:]
            if static_text:
                _check_for_unmatched_closing_brace(static_text, current_pos)
                segments.append(ParsedStaticValue(text=static_text))
            break

        # Emit static text leading up to the special position (if any)
        if next_special.start > current_pos:
            static_text = template[current_pos : next_special.start]
            _check_for_unmatched_closing_brace(static_text, current_pos)
            segments.append(ParsedStaticValue(text=static_text))

        match next_special:
            case _NextBrace():
                variable, new_pos = _parse_brace_at(template, next_special.start)
                segments.append(variable)
                current_pos = new_pos
            case _NextSequence():
                sequence_token_positions.append(next_special.start)
                segments.append(next_special.segment)
                current_pos = next_special.end
            case _:
                msg = f"Unexpected _NextSpecial variant: {type(next_special).__name__}"
                raise TypeError(msg)

        if len(sequence_token_positions) > 1:
            msg = (
                f"Template contains more than one sequence token; only one is "
                f"allowed (second occurrence at position {sequence_token_positions[1]})"
            )
            raise MacroSyntaxError(
                msg,
                failure_reason=MacroParseFailureReason.MULTIPLE_SEQUENCE_TOKENS,
                error_position=sequence_token_positions[1],
            )

    return segments


def parse_variable(variable_content: str) -> ParsedVariable:
    """Parse a variable from its content (text between braces).

    Args:
        variable_content: Content between braces (e.g., "workflow_name?:_:lower")

    Returns:
        ParsedVariable with name, format specs, and default value

    Raises:
        MacroSyntaxError: If variable syntax is invalid
    """
    # Parse variable content: name[?][:format[:format...]][|default]

    # Check for default value (|)
    default_value = None
    if "|" in variable_content:
        parts = variable_content.split("|", 1)
        variable_content = parts[0]
        default_value = parts[1]

    # Check for format specifiers (:)
    format_specs: list[FormatSpec] = []
    is_required = True
    if ":" in variable_content:
        parts = variable_content.split(":")
        variable_part = parts[0]
        format_parts = parts[1:]

        # Parse format specifiers
        for format_part in format_parts:
            format_spec = parse_format_spec(format_part)
            format_specs.append(format_spec)

        # Check if last format spec ends with unquoted ?
        if format_parts:
            last_format_part = format_parts[-1]

            # Check if it's quoted (quoted formats preserve ? as literal)
            is_quoted = last_format_part.startswith("'") and last_format_part.endswith("'")

            if not is_quoted and last_format_part.endswith("?"):
                # Strip the ? and re-parse the format
                stripped_format = last_format_part[:-1]
                if stripped_format:
                    # Re-parse without the ?
                    format_specs[-1] = parse_format_spec(stripped_format)
                else:
                    # Format was just "?", remove it entirely
                    format_specs.pop()

                # Mark variable as optional
                is_required = False
    else:
        variable_part = variable_content

    # Check for optional marker (?) after variable name
    if variable_part.endswith("?"):
        name = variable_part[:-1]
        is_required = False
    else:
        name = variable_part

    info = VariableInfo(name=name, is_required=is_required)
    return ParsedVariable(info=info, format_specs=format_specs, default_value=default_value)


def parse_format_spec(format_text: str) -> FormatSpec:
    """Parse a single format specifier.

    Args:
        format_text: Format specifier text (e.g., "lower", "03", "_")

    Returns:
        Appropriate FormatSpec subclass instance

    Raises:
        MacroSyntaxError: If format specifier is invalid
    """
    # Remove quotes if present (for explicit separators like 'lower')
    if format_text.startswith("'") and format_text.endswith("'"):
        # Quoted text is always a separator, even if it matches other keywords
        return SeparatorFormat(separator=format_text[1:-1])

    # Check for date format (starts with %)
    if format_text.startswith("%"):
        # Date format pattern like %Y-%m-%d
        return DateFormat(pattern=format_text)

    # Check for numeric padding (e.g., "03", "04")
    if re.match(r"^\d+$", format_text):
        width = int(format_text)
        # Numeric padding like 03 means pad to 3 digits with zeros
        return NumericPaddingFormat(width=width)

    # Check for known transformations
    if format_text in FORMAT_REGISTRY:
        # Known transformation keyword (lower, upper, slug)
        return FORMAT_REGISTRY[format_text]

    # Otherwise, treat as separator (unquoted text that doesn't match any format)
    return SeparatorFormat(separator=format_text)


def _find_next_special(template: str, start: int) -> _NextSpecial | None:
    """Return the earliest next brace or sequence token at/after `start`.

    Returns None if no special tokens remain.
    """
    candidates: list[_NextSpecial] = []

    brace_pos = template.find("{", start)
    if brace_pos != -1:
        candidates.append(_NextBrace(start=brace_pos))

    hash_match = _find_hash_sequence(template, start)
    if hash_match is not None:
        hash_start, hash_end = hash_match
        candidates.append(
            _NextSequence(
                start=hash_start,
                end=hash_end,
                segment=ParsedSequenceToken(
                    width=hash_end - hash_start,
                    original_syntax=SequenceTokenSyntax.HASH,
                ),
            )
        )

    printf_match = _PRINTF_SEQUENCE_RE.search(template, start)
    if printf_match is not None:
        width_str = printf_match.group(1)
        # Empty width string (`%d`) => unpadded (width 0).
        width = int(width_str) if width_str else 0
        candidates.append(
            _NextSequence(
                start=printf_match.start(),
                end=printf_match.end(),
                segment=ParsedSequenceToken(
                    width=width,
                    original_syntax=SequenceTokenSyntax.PRINTF,
                ),
            )
        )

    if not candidates:
        return None

    # Earliest wins. `#`/`%` can never coincide with `{`, so no tiebreak needed.
    return min(candidates, key=lambda c: c.start)


def _find_hash_sequence(template: str, start: int) -> tuple[int, int] | None:
    """Find the next run of `#` characters at/after `start`.

    Returns (start, end-exclusive) of the run, or None if no `#` found.
    """
    hash_start = template.find("#", start)
    if hash_start == -1:
        return None
    hash_end = hash_start
    while hash_end < len(template) and template[hash_end] == "#":
        hash_end += 1
    return (hash_start, hash_end)


def _parse_brace_at(template: str, brace_start: int) -> tuple[ParsedVariable, int]:
    """Parse a `{...}` block starting at `brace_start`.

    Returns the parsed variable and the position immediately after the
    closing brace.
    """
    brace_end = template.find("}", brace_start)
    if brace_end == -1:
        msg = f"Unclosed brace at position {brace_start}"
        raise MacroSyntaxError(
            msg,
            failure_reason=MacroParseFailureReason.UNCLOSED_BRACE,
            error_position=brace_start,
        )

    # Check for nested braces (opening brace before closing brace)
    next_open = template.find("{", brace_start + 1)
    if next_open != -1 and next_open < brace_end:
        msg = f"Nested braces are not allowed at position {next_open}"
        raise MacroSyntaxError(
            msg,
            failure_reason=MacroParseFailureReason.NESTED_BRACES,
            error_position=next_open,
        )

    variable_content = template[brace_start + 1 : brace_end]
    if not variable_content:
        msg = f"Empty variable at position {brace_start}"
        raise MacroSyntaxError(
            msg,
            failure_reason=MacroParseFailureReason.EMPTY_VARIABLE,
            error_position=brace_start,
        )

    variable = parse_variable(variable_content)
    return (variable, brace_end + 1)


def _check_for_unmatched_closing_brace(static_text: str, base_pos: int) -> None:
    """Raise if `static_text` contains a `}` (which would be unmatched)."""
    if "}" not in static_text:
        return
    closing_pos = base_pos + static_text.index("}")
    msg = f"Unmatched closing brace at position {closing_pos}"
    raise MacroSyntaxError(
        msg,
        failure_reason=MacroParseFailureReason.UNMATCHED_CLOSING_BRACE,
        error_position=closing_pos,
    )
