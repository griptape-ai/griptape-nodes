"""Macro language parser and resolver for template-based path generation.

This module provides the core macro language implementation for parsing and resolving
template strings like "{inputs}/{workflow_name?:_}{file_name}" used in the project
schema-based file management system.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


class VariableInfo(NamedTuple):
    """Metadata about a variable in a macro template.

    Attributes:
        name: Variable name (e.g., "workflow_name", "file_name")
        is_required: True if variable is required (not marked with ?)
    """

    name: str
    is_required: bool


class MacroSyntaxError(Exception):
    """Raised when macro template has invalid syntax.

    Examples of syntax errors:
    - Unbalanced braces: "{inputs}/{file_name"
    - Invalid format specifier: "{index:xyz}"
    - Nested braces: "{outer_{inner}}"
    """


class MacroResolutionError(Exception):
    """Raised when macro cannot be resolved with provided variables.

    Examples of resolution errors:
    - Required variable missing from variables dict
    - Environment variable referenced but not found in environment
    - Format specifier cannot be applied to value type (e.g., :03 on string)
    """


# ============================================================================
# Format Specifier Classes
# ============================================================================


@dataclass
class FormatSpec(ABC):
    """Base class for format specifiers."""

    @abstractmethod
    def apply(self, value: str | int) -> str | int:
        """Apply this format spec to a value during resolution.

        Args:
            value: Value to transform

        Returns:
            Transformed value

        Raises:
            MacroResolutionError: If format cannot be applied to value type

        Examples:
            >>> # NumericPaddingFormat(width=3).apply(5)
            "005"
            >>> # LowerCaseFormat().apply("MyWorkflow")
            "myworkflow"
        """

    @abstractmethod
    def reverse(self, value: str) -> str | int:
        """Reverse this format spec during matching (best effort).

        Args:
            value: Formatted string value from a path

        Returns:
            Original value before format was applied

        Raises:
            MacroResolutionError: If value cannot be reversed

        Examples:
            >>> # NumericPaddingFormat(width=3).reverse("005")
            5
            >>> # SeparatorFormat(separator="_").reverse("workflow_")
            "workflow"
        """


@dataclass
class SeparatorFormat(FormatSpec):
    """Separator appended to variable value like :_, :/, :foo.

    Must be first format spec in list (if present).
    Syntax: {var:_} or {var:'lower'} (quotes to disambiguate from transformations)
    """

    separator: str  # e.g., "_", "/", "foo"

    def apply(self, value: str | int) -> str:
        """Append separator to value."""
        return str(value) + self.separator

    def reverse(self, value: str) -> str:
        """Remove separator from end of value."""
        if value.endswith(self.separator):
            return value[: -len(self.separator)]
        return value


@dataclass
class NumericPaddingFormat(FormatSpec):
    """Numeric padding format like :03, :04."""

    width: int  # e.g., 3 for :03

    def apply(self, value: str | int) -> str:
        """Apply numeric padding: 5 → "005"."""
        if not isinstance(value, int):
            if not str(value).isdigit():
                msg = (
                    f"Numeric padding format :{self.width:0{self.width}d} "
                    f"cannot be applied to non-numeric value: {value}"
                )
                raise MacroResolutionError(msg)
            value = int(value)
        return f"{value:0{self.width}d}"

    def reverse(self, value: str) -> int:
        """Reverse numeric padding: "005" → 5."""
        try:
            return int(value)
        except ValueError as e:
            msg = f"Cannot parse '{value}' as integer"
            raise MacroResolutionError(msg) from e


@dataclass
class LowerCaseFormat(FormatSpec):
    """Lowercase transformation :lower."""

    def apply(self, value: str | int) -> str:
        """Convert value to lowercase."""
        return str(value).lower()

    def reverse(self, value: str) -> str:
        """Cannot reliably reverse case - return as-is."""
        return value


@dataclass
class UpperCaseFormat(FormatSpec):
    """Uppercase transformation :upper."""

    def apply(self, value: str | int) -> str:
        """Convert value to uppercase."""
        return str(value).upper()

    def reverse(self, value: str) -> str:
        """Cannot reliably reverse case - return as-is."""
        return value


@dataclass
class SlugFormat(FormatSpec):
    """Slugification format :slug (spaces to hyphens, safe chars only)."""

    def apply(self, value: str | int) -> str:
        """Convert to slug: spaces→hyphens, lowercase, safe chars."""
        s = str(value).lower()
        s = re.sub(r"\s+", "-", s)  # Spaces to hyphens
        s = re.sub(r"[^a-z0-9\-_]", "", s)  # Keep only safe chars
        return s

    def reverse(self, value: str) -> str:
        """Cannot reliably reverse slugification - return as-is."""
        return value


@dataclass
class DateFormat(FormatSpec):
    """Date formatting like :%Y-%m-%d."""

    pattern: str  # e.g., "%Y-%m-%d"

    def apply(self, _value: str | int) -> str:
        """Apply date formatting."""
        # TODO(https://github.com/griptape-ai/griptape-nodes/issues/XXXX): Implement date formatting
        msg = "DateFormat not yet fully implemented"
        raise MacroResolutionError(msg)

    def reverse(self, value: str) -> str:
        """Attempt to parse date string."""
        # TODO(https://github.com/griptape-ai/griptape-nodes/issues/XXXX): Implement date parsing
        return value


# ============================================================================
# Segment Classes
# ============================================================================


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


# ============================================================================
# ParsedMacro Class
# ============================================================================


class ParsedMacro:
    """Structured representation of a parsed macro template.

    This class is an internal representation used by MacroResolver.
    Users should obtain instances via MacroParser.parse() and pass them
    to MacroResolver.resolve() without inspecting the internal structure.
    """

    def __init__(self, template: str, segments: list[ParsedSegment]) -> None:
        """Initialize parsed macro.

        Args:
            template: Original template string
            segments: List of parsed segments (alternating static/variable)
        """
        self.template = template
        self.segments = segments

    def get_variables(self) -> list[VariableInfo]:
        """Extract all VariableInfo from parsed segments."""
        return [seg.info for seg in self.segments if isinstance(seg, ParsedVariable)]


class MacroParser:
    """Parse and analyze macro templates.

    This class provides static methods for parsing macro template strings
    into structured representations and extracting metadata about variables.
    """

    @staticmethod
    def parse(template: str) -> ParsedMacro:
        """Parse a macro template string, validating syntax.

        Parses templates containing variables in the form:
        - {variable} - Required variable
        - {variable?} - Optional variable
        - {variable:format} - Required with format specifier
        - {variable?:format} - Optional with format specifier
        - {variable|default} - Required with default value

        Format specifiers:
        - Numeric padding: {index:03} -> "001", "002"
        - Case: {name:lower}, {name:upper}
        - Slugify: {name:slug}
        - Date: {date:%Y-%m-%d}
        - Conditional separator: {workflow_name?:_} -> "name_" or ""

        Args:
            template: Template string to parse (e.g., "{inputs}/{workflow_name?:_}{file_name}")

        Returns:
            ParsedMacro: Structured representation for use with MacroResolver

        Raises:
            MacroSyntaxError: If template has invalid syntax (unbalanced braces,
                invalid format specifiers, etc.)

        Examples:
            >>> parsed = MacroParser.parse("{inputs}/{file_name}")
            >>> parsed = MacroParser.parse("{workflow_name?:_}{file_name}")
        """
        try:
            segments = MacroParser._parse_segments(template)
        except MacroSyntaxError as err:
            msg = f"Attempted to parse template string '{template}'. Failed due to: {err}"
            raise MacroSyntaxError(msg) from err

        if not segments:
            segments.append(ParsedStaticValue(text=""))

        return ParsedMacro(template=template, segments=segments)

    @staticmethod
    def match(parsed_macro: ParsedMacro, path: str) -> list[dict[VariableInfo, str | int]]:
        """Check if a path matches a parsed template and extract variable values.

        Returns all possible variable value combinations that would produce
        the given path when resolved. May return multiple matches if optional
        variables create ambiguity.

        Args:
            parsed_macro: Parsed template from MacroParser.parse()
            path: Actual path string to match against template

        Returns:
            List of dictionaries mapping VariableInfo to extracted values.
            Empty list if path doesn't match the template pattern.
            The VariableInfo keys preserve metadata (name, is_required) from
            the original template. Values are reversed through format specifiers
            where possible (e.g., "005" with :03 becomes integer 5).

        Examples:
            >>> parsed = MacroParser.parse("{inputs}/{workflow_name?:_}{file_name}")
            >>> matches = MacroParser.match(parsed, "inputs/my_workflow_image.jpg")
            >>> matches[0]
            {
                VariableInfo(name='inputs', is_required=True): 'inputs',
                VariableInfo(name='workflow_name', is_required=False): 'my_workflow',
                VariableInfo(name='file_name', is_required=True): 'image.jpg'
            }

            >>> matches = MacroParser.match(parsed, "inputs/image.jpg")
            >>> matches[0]
            {
                VariableInfo(name='inputs', is_required=True): 'inputs',
                VariableInfo(name='file_name', is_required=True): 'image.jpg'
            }
            # workflow_name not in dict (optional variable not present)

            >>> parsed = MacroParser.parse("{outputs}/{file_name}_{index:03}")
            >>> matches = MacroParser.match(parsed, "outputs/render_005")
            >>> matches[0]
            {
                VariableInfo(name='outputs', is_required=True): 'outputs',
                VariableInfo(name='file_name', is_required=True): 'render',
                VariableInfo(name='index', is_required=True): 5
            }
            # Note: index value is integer 5, not string "005"

            >>> parsed = MacroParser.parse("{inputs}/{file_name}")
            >>> MacroParser.match(parsed, "outputs/image.jpg")
            []  # No match - first segment doesn't match
        """
        msg = "MacroParser.match() not yet implemented"
        raise NotImplementedError(msg)

    # Private helper methods

    @staticmethod
    def _parse_segments(template: str) -> list[ParsedSegment]:
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

            variable = MacroParser._parse_variable(variable_content)
            segments.append(variable)

            # Move past the closing brace
            current_pos = brace_end + 1

        return segments

    @staticmethod
    def _parse_variable(variable_content: str) -> ParsedVariable:
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
                format_spec = MacroParser._parse_format_spec(format_part)
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

    @staticmethod
    def _parse_format_spec(format_text: str) -> FormatSpec:
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
        known_transforms = {
            "lower": LowerCaseFormat(),
            "upper": UpperCaseFormat(),
            "slug": SlugFormat(),
        }

        if format_text in known_transforms:
            # Known transformation keyword (lower, upper, slug)
            return known_transforms[format_text]

        # Otherwise, treat as separator (unquoted text that doesn't match any format)
        return SeparatorFormat(separator=format_text)


class MacroResolver:
    """Resolve parsed macro templates with variable values.

    This class provides static methods for resolving ParsedMacro instances
    with actual variable values, handling environment variable resolution,
    format specifiers, and optional variables.
    """

    @staticmethod
    def resolve(
        parsed_macro: ParsedMacro,
        variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> str:
        """Fully resolve a macro template with variable values.

        Resolves all variables in the parsed template, including:
        - Direct value substitution
        - Environment variable resolution (values starting with $)
        - Format specifier application
        - Optional variable handling (omit if not provided)
        - Default value application

        Args:
            parsed_macro: Parsed template from MacroParser.parse()
            variables: Variable name -> value mapping. Values can be:
                - Direct values: "shots/"
                - Env var references: "$SHOT" (resolved automatically)
                - Integers: 5 (for format specs like {index:03})
            secrets_manager: SecretsManager instance for resolving env vars.

        Returns:
            Fully resolved string with all variables and env vars substituted

        Raises:
            MacroResolutionError: If:
                - Required variable missing from variables dict
                - Environment variable referenced (e.g., $SHOT) but not found
                - Format specifier cannot be applied to value type

        Examples:
            >>> parsed = MacroParser.parse("{inputs}/{workflow_name?:_}{file_name}")
            >>> MacroResolver.resolve(parsed, {
            ...     "inputs": "inputs",
            ...     "workflow_name": "my_workflow",
            ...     "file_name": "image.jpg"
            ... }, secrets_manager)
            'inputs/my_workflow_image.jpg'

            >>> MacroResolver.resolve(parsed, {
            ...     "inputs": "inputs",
            ...     "file_name": "image.jpg"
            ... }, secrets_manager)
            'inputs/image.jpg'

            >>> parsed = MacroParser.parse("{outputs}/{file_name}_{index:03}")
            >>> MacroResolver.resolve(parsed, {
            ...     "outputs": "$OUTPUT_DIR",  # Resolved from environment
            ...     "file_name": "render",
            ...     "index": 5
            ... }, secrets_manager)
            '/path/to/outputs/render_005'
        """
        result_parts: list[str] = []

        for segment in parsed_macro.segments:
            match segment:
                case ParsedStaticValue():
                    result_parts.append(segment.text)
                case ParsedVariable():
                    resolved_value = MacroResolver._resolve_variable(segment, variables, secrets_manager)
                    if resolved_value is not None:
                        # Optional variable was provided, add to result
                        result_parts.append(resolved_value)
                    # else: Optional variable not provided, skip it
                case _:
                    msg = f"Unexpected segment type: {type(segment).__name__}"
                    raise MacroResolutionError(msg)

        return "".join(result_parts)

    @staticmethod
    def _resolve_variable(
        variable: ParsedVariable, variables: dict[str, str | int], secrets_manager: SecretsManager
    ) -> str | None:
        """Resolve a single variable with format specs and env var resolution.

        Args:
            variable: The parsed variable to resolve
            variables: Variable name -> value mapping
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            Resolved string value, or None if optional variable not provided

        Raises:
            MacroResolutionError: If required variable missing or env var not found
        """
        variable_name = variable.info.name

        if variable_name not in variables:
            if variable.info.is_required:
                msg = f"Required variable '{variable_name}' not found in variables dict"
                raise MacroResolutionError(msg)
            # Optional variable not provided, return None to signal it should be skipped
            return None

        value = variables[variable_name]
        resolved_value: str | int = MacroResolver._resolve_env_var(value, secrets_manager)

        for format_spec in variable.format_specs:
            resolved_value = format_spec.apply(resolved_value)

        # Return fully resolved value as string
        return str(resolved_value)

    @staticmethod
    def _resolve_env_var(value: str | int, secrets_manager: SecretsManager) -> str | int:
        """Resolve environment variables in a value.

        Args:
            value: Value that may contain env var reference (e.g., "$VAR")
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            Resolved value (env var substituted if found)

        Raises:
            MacroResolutionError: If value starts with $ but env var not found
        """
        if not isinstance(value, str):
            # Integer values don't contain env vars, return as-is
            return value

        if not value.startswith("$"):
            # String doesn't reference an env var, return as-is
            return value

        env_var_name = value[1:]
        env_value = secrets_manager.get_secret(env_var_name, should_error_on_not_found=False)

        if env_value is None:
            msg = f"Environment variable '{env_var_name}' not found"
            raise MacroResolutionError(msg)

        # Return resolved env var value
        return env_value
