"""Core ParsedMacro class - main API for macro templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.common.macro_parser.exceptions import MacroResolutionError, MacroSyntaxError
from griptape_nodes.common.macro_parser.matching import extract_unknown_variables
from griptape_nodes.common.macro_parser.parsing import parse_segments
from griptape_nodes.common.macro_parser.resolution import partial_resolve
from griptape_nodes.common.macro_parser.segments import ParsedStaticValue, ParsedVariable, VariableInfo

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


class ParsedMacro:
    """Parsed macro template with methods for resolving and matching paths.

    This is the main API class for working with macro templates.
    """

    def __init__(self, template: str) -> None:
        """Parse a macro template string, validating syntax."""
        self.template = template

        try:
            segments = parse_segments(template)
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
        """Fully resolve the macro template with variable values."""
        # Partially resolve with known variables
        partial = partial_resolve(self.template, self.segments, variables, secrets_manager)

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
        """Check if a path matches this template."""
        result = self.find_matches_detailed(path, known_variables, secrets_manager)
        return result is not None

    def extract_variables(
        self,
        path: str,
        known_variables: dict[str, str | int],
        secrets_manager: SecretsManager,
    ) -> dict[str, str | int] | None:
        """Extract variable values from a path (plain string keys)."""
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
        """Extract variable values from a path with metadata (greedy match)."""
        # STEP 1: Partial resolve - resolve known variables into static text
        partial = partial_resolve(self.template, self.segments, known_variables, secrets_manager)

        # STEP 2: Check if fully resolved (all variables were known)
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

        # STEP 3: Extract unknown variables from path
        extracted = extract_unknown_variables(partial.segments, path)
        if extracted is None:
            # Extraction failed (static segments don't match or can't extract variables)
            return None

        # STEP 4: Merge extracted unknowns with known variables to create complete result
        for segment in self.segments:
            if isinstance(segment, ParsedVariable) and segment.info.name in known_variables:
                extracted[segment.info] = known_variables[segment.info.name]

        return extracted
