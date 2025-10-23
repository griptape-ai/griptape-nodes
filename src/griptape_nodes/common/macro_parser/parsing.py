"""Parsing logic for macro templates."""

from __future__ import annotations

import re

from griptape_nodes.common.macro_parser.exceptions import MacroSyntaxError
from griptape_nodes.common.macro_parser.formats import (
    FORMAT_REGISTRY,
    DateFormat,
    FormatSpec,
    NumericPaddingFormat,
    SeparatorFormat,
)
from griptape_nodes.common.macro_parser.segments import (
    ParsedSegment,
    ParsedStaticValue,
    ParsedVariable,
    VariableInfo,
)


def parse_segments(template: str) -> list[ParsedSegment]:
    """Parse template into alternating static/variable segments.

    Args:
        template: Template string to parse

    Returns:
        List of ParsedSegment (static and variable)

    Raises:
        MacroSyntaxError: If template syntax is invalid
    """
    segments: list[ParsedSegment] = []
    current_pos = 0

    while current_pos < len(template):
        # Find next opening brace
        brace_start = template.find("{", current_pos)

        if brace_start == -1:
            # No more variables, rest is static text
            static_text = template[current_pos:]
            if static_text:
                # Check for unmatched closing braces in remaining text
                if "}" in static_text:
                    closing_pos = current_pos + static_text.index("}")
                    msg = f"Unmatched closing brace at position {closing_pos}"
                    raise MacroSyntaxError(msg)
                segments.append(ParsedStaticValue(text=static_text))
            break

        # Add static text before the brace (if any)
        if brace_start > current_pos:
            static_text = template[current_pos:brace_start]
            # Check for unmatched closing braces in static text
            if "}" in static_text:
                closing_pos = current_pos + static_text.index("}")
                msg = f"Unmatched closing brace at position {closing_pos}"
                raise MacroSyntaxError(msg)
            segments.append(ParsedStaticValue(text=static_text))

        # Find matching closing brace
        brace_end = template.find("}", brace_start)
        if brace_end == -1:
            msg = f"Unclosed brace at position {brace_start}"
            raise MacroSyntaxError(msg)

        # Check for nested braces (opening brace before closing brace)
        next_open = template.find("{", brace_start + 1)
        if next_open != -1 and next_open < brace_end:
            msg = f"Nested braces are not allowed at position {next_open}"
            raise MacroSyntaxError(msg)

        # Extract and parse the variable content
        variable_content = template[brace_start + 1 : brace_end]
        if not variable_content:
            msg = f"Empty variable at position {brace_start}"
            raise MacroSyntaxError(msg)

        variable = parse_variable(variable_content)
        segments.append(variable)

        # Move past the closing brace
        current_pos = brace_end + 1

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
    if ":" in variable_content:
        parts = variable_content.split(":")
        variable_part = parts[0]
        format_parts = parts[1:]

        # Parse format specifiers
        for format_part in format_parts:
            format_spec = parse_format_spec(format_part)
            format_specs.append(format_spec)
    else:
        variable_part = variable_content

    # Check for optional marker (?)
    if variable_part.endswith("?"):
        name = variable_part[:-1]
        is_required = False
    else:
        name = variable_part
        is_required = True

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
