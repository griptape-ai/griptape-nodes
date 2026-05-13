"""Matching logic for extracting variables from paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.common.macro_parser.exceptions import MacroParseFailureReason, MacroSyntaxError
from griptape_nodes.common.macro_parser.segments import (
    ParsedSegment,
    ParsedStaticValue,
    ParsedVariable,
    VariableInfo,
)

if TYPE_CHECKING:
    from griptape_nodes.common.macro_parser.formats import FormatSpec


def extract_unknown_variables(
    pattern_segments: list[ParsedSegment],
    path: str,
) -> dict[VariableInfo, str | int] | None:
    """Extract unknown variable values from path (greedy matching).

    Args:
        pattern_segments: Partially resolved segments to match against
        path: Path string to extract variables from

    Returns:
        Dict mapping VariableInfo to extracted values, or None if no match.
    """
    current_match: dict[VariableInfo, str | int] = {}
    current_pos = 0

    for i, segment in enumerate(pattern_segments):
        match segment:
            case ParsedStaticValue():
                # Verify static text matches at current position
                if not path[current_pos:].startswith(segment.text):
                    # Static text doesn't match at this position
                    return None
                current_pos += len(segment.text)
            case ParsedVariable():
                result = extract_single_variable(segment, pattern_segments[i + 1 :], path, current_pos)
                if result is None:
                    return None
                value, new_pos = result
                current_match[segment.info] = value
                current_pos = new_pos
            case _:
                msg = f"Unexpected segment type: {type(segment).__name__}"
                raise MacroSyntaxError(
                    msg,
                    failure_reason=MacroParseFailureReason.UNEXPECTED_SEGMENT_TYPE,
                )

    return current_match


def extract_single_variable(
    variable: ParsedVariable,
    remaining_segments: list[ParsedSegment],
    path: str,
    start_pos: int,
) -> tuple[str | int, int] | None:
    """Extract value for a single variable from path.

    Args:
        variable: The variable to extract
        remaining_segments: Segments after this variable
        path: Full path being matched
        start_pos: Position in path to start extraction

    Returns:
        Tuple of (extracted_value, new_position) or None if extraction fails.
    """
    # Find next static segment to determine end position
    next_static = find_next_static(remaining_segments)
    if next_static:
        end_pos = path.find(next_static.text, start_pos)
        if end_pos == -1:
            # Can't find next static - no match
            return None
    else:
        # No more static segments - consume to end
        end_pos = len(path)

    # Extract raw value
    raw_value = path[start_pos:end_pos]

    # Reverse format specs
    reversed_value = reverse_format_specs(raw_value, variable.format_specs)
    if reversed_value is None:
        # Can't reverse format specs - no match
        return None

    return (reversed_value, end_pos)


def find_next_static(segments: list[ParsedSegment]) -> ParsedStaticValue | None:
    """Find next static segment in list.

    Args:
        segments: List of segments to search

    Returns:
        First ParsedStaticValue found, or None if no static segments.
    """
    for seg in segments:
        if isinstance(seg, ParsedStaticValue):
            return seg
    # No static segment found
    return None


def reverse_format_specs(value: str, format_specs: list[FormatSpec]) -> str | int | None:
    """Apply format spec reversal in reverse order.

    Args:
        value: String value extracted from path
        format_specs: List of format specs to reverse

    Returns:
        Reversed value (might be int after NumericPaddingFormat.reverse), or None if reversal fails.
    """
    result: str | int = value
    # Apply in reverse order (last spec first)
    for spec in reversed(format_specs):
        # reverse() expects str but result might be int, so convert if needed
        str_result = str(result) if isinstance(result, int) else result
        reversed_result = spec.reverse(str_result)
        if reversed_result is None:
            # Can't reverse this format spec
            return None
        result = reversed_result
    # Return reversed value (might be int after NumericPaddingFormat.reverse)
    return result
