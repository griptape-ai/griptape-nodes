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
    """Parsed macro template with methods for resolving and matching paths.

    This is the main API class for working with macro templates. It provides methods to:
    - Parse template strings on construction
    - Generate paths by resolving variables (resolve)
    - Match paths against templates (find_matches, find_matches_detailed)

    Examples:
        >>> macro = ParsedMacro("{inputs}/{file_name}")
        >>> macro.resolve({"inputs": "outputs", "file_name": "photo.jpg"}, secrets)
        "outputs/photo.jpg"

        >>> macro.find_matches("inputs/photo.jpg", {"inputs": "inputs"}, secrets)
        ["inputs/photo.jpg"]
    """

    def __init__(self, template: str) -> None:
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

        Raises:
            MacroSyntaxError: If template has invalid syntax (unbalanced braces,
                invalid format specifiers, etc.)

        Examples:
            >>> macro = ParsedMacro("{inputs}/{file_name}")
            >>> macro = ParsedMacro("{workflow_name?:_}{file_name}")
        """
        self.template = template

        try:
            segments = self._parse_segments()
        except MacroSyntaxError as err:
            msg = f"Attempted to parse template string '{template}'. Failed due to: {err}"
            raise MacroSyntaxError(msg) from err

        if not segments:
            segments.append(ParsedStaticValue(text=""))
        self.segments = segments

    def get_variables(self) -> list[VariableInfo]:
        """Extract all VariableInfo from parsed segments."""
        return [seg.info for seg in self.segments if isinstance(seg, ParsedVariable)]

    def resolve(
        self,
        variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> str:
        """Fully resolve the macro template with variable values.

        Resolves all variables in the template, including:
        - Direct value substitution
        - Environment variable resolution (values starting with $)
        - Format specifier application
        - Optional variable handling (omit if not provided)
        - Default value application

        Args:
            variables: Variable name -> value mapping. Values can be:
                - Direct values: "shots/"
                - Env var references: "$SHOT" (resolved automatically)
                - Integers: 5 (for format specs like {index:03})
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            Fully resolved string with all variables and env vars substituted

        Raises:
            MacroResolutionError: If:
                - Required variable missing from variables dict
                - Environment variable referenced (e.g., $SHOT) but not found
                - Format specifier cannot be applied to value type

        Examples:
            >>> macro = ParsedMacro("{inputs}/{workflow_name?:_}{file_name}")
            >>> macro.resolve({
            ...     "inputs": "inputs",
            ...     "workflow_name": "my_workflow",
            ...     "file_name": "image.jpg"
            ... }, secrets_manager)
            'inputs/my_workflow_image.jpg'

            >>> macro.resolve({
            ...     "inputs": "inputs",
            ...     "file_name": "image.jpg"
            ... }, secrets_manager)
            'inputs/image.jpg'

            >>> macro = ParsedMacro("{outputs}/{file_name}_{index:03}")
            >>> macro.resolve({
            ...     "outputs": "$OUTPUT_DIR",  # Resolved from environment
            ...     "file_name": "render",
            ...     "index": 5
            ... }, secrets_manager)
            '/path/to/outputs/render_005'
        """
        # Partially resolve with known variables
        partial = self._partial_resolve(variables, secrets_manager)

        # Check if fully resolved
        if not partial.is_fully_resolved():
            unresolved = partial.get_unresolved_variables()
            unresolved_names = [var.info.name for var in unresolved]
            msg = f"Cannot fully resolve macro - missing required variables: {', '.join(unresolved_names)}"
            raise MacroResolutionError(msg)

        # Convert to string
        return partial.to_string()

    def matches(
        self,
        path: str,
        known_variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> bool:
        """Check if a path matches this template.

        This is the simplest matching API - returns True/False.

        Args:
            path: Path string to test against template
            known_variables: Known variable values (reduces ambiguity)
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            True if path matches template, False otherwise

        Examples:
            >>> macro = ParsedMacro("{inputs}/{file}")
            >>> macro.matches("inputs/photo.jpg", {"inputs": "inputs"}, secrets)
            True
            >>> macro.matches("outputs/photo.jpg", {"inputs": "inputs"}, secrets)
            False
        """
        result = self.find_matches_detailed(path, known_variables, secrets_manager)
        return result is not None

    def extract_variables(
        self,
        path: str,
        known_variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> dict[str, str | int] | None:
        """Extract variable values from a path (plain string keys).

        Returns a dictionary with simple string keys mapping to values.
        For advanced use cases needing VariableInfo metadata, use find_matches_detailed().

        Args:
            path: Path string to extract from
            known_variables: Known variable values (reduces ambiguity)
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            Dict mapping variable names to values, or None if no match

        Examples:
            >>> macro = ParsedMacro("{inputs}/{file}")
            >>> macro.extract_variables("inputs/photo.jpg", {"inputs": "inputs"}, secrets)
            {"inputs": "inputs", "file": "photo.jpg"}
            >>> macro.extract_variables("outputs/photo.jpg", {"inputs": "inputs"}, secrets)
            None
        """
        detailed = self.find_matches_detailed(path, known_variables, secrets_manager)
        if detailed is None:
            return None
        # Convert VariableInfo keys to plain string keys
        return {var_info.name: value for var_info, value in detailed.items()}

    def find_matches_detailed(
        self,
        path: str,
        known_variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> dict[VariableInfo, str | int] | None:
        """Extract variable values from a path with metadata (greedy match).

        This is the advanced version that returns detailed variable metadata with VariableInfo keys.
        Most callers should use extract_variables() for plain dict or matches() for boolean check.

        Given a parsed template and a path, extracts variable values by matching
        the path against the template pattern. Known variables are resolved before
        matching to reduce ambiguity. Uses greedy matching strategy to return a single
        result instead of exploring all possible interpretations.

        MATCHING SCENARIOS (how this method handles different cases):

        Scenario A: All variables known, path matches
            Template: "{inputs}/{file_name}"
            Known: {"inputs": "inputs", "file_name": "photo.jpg"}
            Path: "inputs/photo.jpg"
            Result: {"inputs": "inputs", "file_name": "photo.jpg"}
            Flow: Step 1 → fully resolved → Step 2 → exact match → return result

        Scenario B: All variables known, path doesn't match
            Template: "{inputs}/{file_name}"
            Known: {"inputs": "inputs", "file_name": "photo.jpg"}
            Path: "outputs/photo.jpg"
            Result: None
            Flow: Step 1 → fully resolved → Step 2 → no match → return None

        Scenario C: Some variables known, path matches
            Template: "{inputs}/{workflow_name}/{file_name}"
            Known: {"inputs": "inputs"}
            Path: "inputs/my_workflow/photo.jpg"
            Result: {"inputs": "inputs", "workflow_name": "my_workflow", "file_name": "photo.jpg"}
            Flow: Step 1 → partial resolve → Step 2 skipped → Step 3 → static validated
                  → Step 4 → extract unknowns (workflow_name, file_name) → merge with knowns → return

        Scenario D: Some variables known, known variable value doesn't match path
            Template: "{inputs}/{workflow_name}/{file_name}"
            Known: {"inputs": "outputs"}
            Path: "inputs/my_workflow/photo.jpg"
            Result: None
            Flow: Step 1 → partial resolve → Step 2 skipped → Step 3 → static mismatch → return None

        Scenario E: Optional variable present in path
            Template: "{inputs}/{workflow_name?:_}{file_name}"
            Known: {"inputs": "inputs"}
            Path: "inputs/my_workflow_photo.jpg"
            Result: {"inputs": "inputs", "workflow_name": "my_workflow", "file_name": "photo.jpg"}
            Flow: Step 1 → partial resolve → Step 2 skipped → Step 3 → validated
                  → Step 4 → extract with separator matching → return

        Scenario F: Optional variable omitted from path
            Template: "{inputs}/{workflow_name?:_}{file_name}"
            Known: {"inputs": "inputs"}
            Path: "inputs/photo.jpg"
            Result: {"inputs": "inputs", "file_name": "photo.jpg"}
            Flow: Step 1 → partial resolve (optional removed) → Step 2 skipped → Step 3 → validated
                  → Step 4 → extract file_name only → return

        Scenario G: Multiple unknowns with delimiters
            Template: "{inputs}/{dir}/{file_name}.{ext}"
            Known: {"inputs": "inputs"}
            Path: "inputs/render/output.png"
            Result: {"inputs": "inputs", "dir": "render", "file_name": "output", "ext": "png"}
            Flow: Step 1 → partial resolve → Step 2 skipped → Step 3 → validated
                  → Step 4 → extract dir, file_name, ext using "/" and "." delimiters → return

        Scenario H: Format spec reversal (numeric padding)
            Template: "{inputs}/{frame:03}.png"
            Known: {"inputs": "inputs"}
            Path: "inputs/005.png"
            Result: {"inputs": "inputs", "frame": 5}  # Note: integer value
            Flow: Step 1 → partial resolve → Step 2 skipped → Step 3 → validated
                  → Step 4 → extract "005", reverse format spec → 5 → return

        Args:
            path: Actual path string to match against template
            known_variables: Dictionary of variables with known values. These will be
                            resolved before matching to reduce ambiguity. Pass empty
                            dict {} if no variables are known.
            secrets_manager: SecretsManager instance for resolving env vars in known variables

        Returns:
            Dictionary mapping VariableInfo to extracted values, or None if path doesn't
            match the template pattern. Uses greedy matching to return a single result.
        """
        # STEP 1: Partial resolve - resolve known variables into static text
        # This reduces the matching problem from "match everything" to "match only the unknowns"
        #
        # Scenarios affected:
        # - All scenarios: always runs first
        # - Scenarios A, B: will be fully resolved (all variables known)
        # - Scenarios C-H: will have mix of static and unknown variables
        # - Scenarios E, F: optional variables not in known_variables are removed
        partial = self._partial_resolve(known_variables, secrets_manager)

        # STEP 2: Check if fully resolved (all variables were known)
        # If so, we can do a direct string comparison
        #
        # Scenarios affected:
        # - Scenario A: fully resolved, path matches → return result dict
        # - Scenario B: fully resolved, path doesn't match → return None
        # - Scenarios C-H: NOT fully resolved, skip this step
        if partial.is_fully_resolved():
            resolved_path = partial.to_string()
            if resolved_path == path:
                # Scenario A: exact match
                result: dict[VariableInfo, str | int] = {}
                for segment in self.segments:
                    if isinstance(segment, ParsedVariable) and segment.info.name in known_variables:
                        result[segment.info] = known_variables[segment.info.name]
                return result
            # Scenario B: no match
            return None

        # STEP 3: Pre-validate static segments (quick rejection)
        # Before expensive extraction, check if all static text appears in path
        #
        # Scenarios affected:
        # - Scenario D: static "outputs" doesn't match path starting with "inputs" → return None
        # - Scenarios C, E-H: static text matches → continue
        if not self._validate_static_match(partial.segments, path):
            # Scenario D: known variable value doesn't match path
            return None

        # STEP 4: Extract unknown variables from path
        # Use static segments as anchors to extract variable values between them
        #
        # Scenarios affected:
        # - Scenario C: extract workflow_name="my_workflow", file_name="photo.jpg"
        # - Scenario E: extract workflow_name="my_workflow", file_name="photo.jpg" (separator matched)
        # - Scenario F: extract file_name="photo.jpg" (optional was removed in Step 1)
        # - Scenario G: extract dir="render", file_name="output", ext="png" (multiple delimiters)
        # - Scenario H: extract frame="005", reverse format spec → 5
        extracted = self._extract_unknown_variables(partial.segments, path)
        if extracted is None:
            msg = f"INTERNAL ERROR: Failed when attempting to find matches against a macro. Static validation passed but extraction failed. Template: {self.template}, Path: {path}"
            raise MacroResolutionError(msg)

        # STEP 5: Merge extracted unknowns with known variables to create complete result
        # The extracted dict contains only extracted unknowns, need to add knowns back in
        #
        # Scenarios affected (D was already eliminated in Step 3):
        # - Scenario C: merge inputs="inputs" → final: {inputs, workflow_name, file_name}
        # - Scenario E: merge inputs="inputs" → final: {inputs, workflow_name, file_name}
        # - Scenario F: merge inputs="inputs" → final: {inputs, file_name}
        # - Scenario G: merge inputs="inputs" → final: {inputs, dir, file_name, ext}
        # - Scenario H: merge inputs="inputs" → final: {inputs, frame}
        for segment in self.segments:
            if isinstance(segment, ParsedVariable) and segment.info.name in known_variables:
                extracted[segment.info] = known_variables[segment.info.name]

        return extracted

    def _validate_static_match(self, pattern_segments: list[ParsedSegment], path: str) -> bool:
        """Check if static segments exist in path (we'll determine positions during extraction)."""
        # For now, just check that all static segments appear in the path
        # The extraction phase will determine exact positions
        for segment in pattern_segments:
            match segment:
                case ParsedStaticValue():
                    if segment.text not in path:
                        # Static text not found in path
                        return False
                case ParsedVariable():
                    # Unknown variable - skip
                    pass
                case _:
                    msg = f"Unexpected segment type: {type(segment).__name__}"
                    raise MacroSyntaxError(msg)

        # All static segments found in path
        return True

    def _extract_unknown_variables(
        self,
        pattern_segments: list[ParsedSegment],
        path: str,
    ) -> dict[VariableInfo, str | int] | None:
        """Extract unknown variable values from path (greedy matching).

        Returns a single match using greedy matching strategy, or None if no match.
        """
        # Simple implementation for now - just handle required variables delimited by static
        current_match: dict[VariableInfo, str | int] = {}
        current_pos = 0

        for i, segment in enumerate(pattern_segments):
            match segment:
                case ParsedStaticValue():
                    current_pos += len(segment.text)
                case ParsedVariable():
                    # Find next static segment to determine end position
                    next_static = self._find_next_static(pattern_segments[i + 1 :])
                    if next_static:
                        end_pos = path.find(next_static.text, current_pos)
                        if end_pos == -1:
                            # Can't find next static - no match
                            return None
                    else:
                        # No more static segments - consume to end
                        end_pos = len(path)

                    # Extract raw value
                    raw_value = path[current_pos:end_pos]

                    # Reverse format specs
                    reversed_value = self._reverse_format_specs(raw_value, segment.format_specs)
                    if reversed_value is None:
                        # Can't reverse format specs - no match
                        return None

                    current_match[segment.info] = reversed_value
                    current_pos = end_pos
                case _:
                    msg = f"Unexpected segment type: {type(segment).__name__}"
                    raise MacroSyntaxError(msg)

        return current_match

    def _find_next_static(self, segments: list[ParsedSegment]) -> ParsedStaticValue | None:
        """Find next static segment in list."""
        for seg in segments:
            if isinstance(seg, ParsedStaticValue):
                return seg
        # No static segment found
        return None

    def _reverse_format_specs(self, value: str, format_specs: list[FormatSpec]) -> str | int | None:
        """Apply format spec reversal in reverse order."""
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

    def _parse_segments(self) -> list[ParsedSegment]:
        """Parse template into alternating static/variable segments.

        Returns:
            List of ParsedSegment (static and variable)

        Raises:
            MacroSyntaxError: If template syntax is invalid
        """
        segments: list[ParsedSegment] = []
        current_pos = 0
        template = self.template

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

            variable = self._parse_variable(variable_content)
            segments.append(variable)

            # Move past the closing brace
            current_pos = brace_end + 1

        return segments

    def _parse_variable(self, variable_content: str) -> ParsedVariable:
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
                format_spec = self._parse_format_spec(format_part)
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

    def _parse_format_spec(self, format_text: str) -> FormatSpec:
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

    def _partial_resolve(
        self,
        variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> _PartiallyResolvedMacro:
        """Partially resolve the macro template with known variables.

        Resolves known variables (including env vars and format specs) into static
        text, leaving unknown variables as-is. This is the core resolution logic
        used by both resolve() and find_matches().

        Args:
            variables: Variable name -> value mapping for known variables
            secrets_manager: SecretsManager instance for resolving env vars

        Returns:
            _PartiallyResolvedMacro with resolved and unresolved segments

        Raises:
            MacroResolutionError: If:
                - Required variable is provided but env var resolution fails
                - Format specifier cannot be applied to value type
        """
        resolved_segments: list[ParsedSegment] = []

        for segment in self.segments:
            match segment:
                case ParsedStaticValue():
                    resolved_segments.append(segment)
                case ParsedVariable():
                    if segment.info.name in variables:
                        # Known variable - resolve it
                        resolved_value = self._resolve_variable(segment, variables, secrets_manager)
                        if resolved_value is not None:
                            # Variable was resolved, add as static
                            resolved_segments.append(ParsedStaticValue(text=resolved_value))
                        # else: Optional variable provided as None, skip it
                        continue

                    if segment.info.is_required:
                        # Required variable not in variables dict - keep as unresolved
                        resolved_segments.append(segment)
                        continue

                    # Optional variable not in variables dict - skip it
                    continue
                case _:
                    msg = f"Unexpected segment type: {type(segment).__name__}"
                    raise MacroResolutionError(msg)

        return _PartiallyResolvedMacro(
            original_template=self.template,
            segments=resolved_segments,
            known_variables=variables,
        )

    def _resolve_variable(
        self, variable: ParsedVariable, variables: dict[str, str | int], secrets_manager: SecretsManager
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
        resolved_value: str | int = self._resolve_env_var(value, secrets_manager)

        for format_spec in variable.format_specs:
            resolved_value = format_spec.apply(resolved_value)

        # Return fully resolved value as string
        return str(resolved_value)

    def _resolve_env_var(self, value: str | int, secrets_manager: SecretsManager) -> str | int:
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


@dataclass
class _PartiallyResolvedMacro:
    """Result of partially resolving a macro with known variables.

    Contains both resolved segments (known variables → static text) and
    unresolved segments (unknown variables still as variables).
    """

    original_template: str
    segments: list[ParsedSegment]
    known_variables: dict[str, str | int]

    def is_fully_resolved(self) -> bool:
        """Check if all variables have been resolved."""
        return all(isinstance(seg, ParsedStaticValue) for seg in self.segments)

    def to_string(self) -> str:
        """Convert to string (only valid if fully resolved)."""
        if not self.is_fully_resolved():
            msg = "Cannot convert partially resolved macro to string - unresolved variables remain"
            raise MacroResolutionError(msg)
        # All segments are ParsedStaticValue at this point
        return "".join(seg.text for seg in self.segments if isinstance(seg, ParsedStaticValue))

    def get_unresolved_variables(self) -> list[ParsedVariable]:
        """Get list of unresolved variables."""
        return [seg for seg in self.segments if isinstance(seg, ParsedVariable)]
