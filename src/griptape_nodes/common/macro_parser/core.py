"""Core ParsedMacro class - main API for macro templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.common.macro_parser.exceptions import (
    MacroResolutionError,
    MacroResolutionFailureReason,
    MacroSyntaxError,
)
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
            raise MacroSyntaxError(
                msg,
                failure_reason=err.failure_reason,
                error_position=err.error_position,
            ) from err

        if not segments:
            segments.append(ParsedStaticValue(text=""))
        self.segments = segments

    def get_variables(self) -> set[VariableInfo]:
        """Extract all VariableInfo from parsed segments."""
        return {seg.info for seg in self.segments if isinstance(seg, ParsedVariable)}

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
            unresolved_names = {var.info.name for var in unresolved}
            msg = f"Cannot fully resolve macro - missing required variables: {', '.join(sorted(unresolved_names))}"
            raise MacroResolutionError(
                msg,
                failure_reason=MacroResolutionFailureReason.MISSING_REQUIRED_VARIABLES,
                missing_variables=unresolved_names,
            )

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
        partial = partial_resolve(self.template, self.segments, known_variables, secrets_manager)

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

        # STEP 3: Extract unknown variables from path
        # Use static segments as anchors to extract variable values between them
        #
        # Scenarios affected:
        # - Scenario C: extract workflow_name="my_workflow", file_name="photo.jpg"
        # - Scenario D: static "outputs" doesn't match "inputs/" → return None
        # - Scenario E: extract workflow_name="my_workflow", file_name="photo.jpg" (separator matched)
        # - Scenario F: extract file_name="photo.jpg" (optional was removed in Step 1)
        # - Scenario G: extract dir="render", file_name="output", ext="png" (multiple delimiters)
        # - Scenario H: extract frame="005", reverse format spec → 5
        extracted = extract_unknown_variables(partial.segments, path)
        if extracted is None:
            # Extraction failed (static segments don't match or can't extract variables)
            return None

        # STEP 4: Merge extracted unknowns with known variables to create complete result
        # The extracted dict contains only extracted unknowns, need to add knowns back in
        #
        # Scenarios affected (D was eliminated in Step 3):
        # - Scenario C: merge inputs="inputs" → final: {inputs, workflow_name, file_name}
        # - Scenario E: merge inputs="inputs" → final: {inputs, workflow_name, file_name}
        # - Scenario F: merge inputs="inputs" → final: {inputs, file_name}
        # - Scenario G: merge inputs="inputs" → final: {inputs, dir, file_name, ext}
        # - Scenario H: merge inputs="inputs" → final: {inputs, frame}
        for segment in self.segments:
            if isinstance(segment, ParsedVariable) and segment.info.name in known_variables:
                extracted[segment.info] = known_variables[segment.info.name]

        return extracted
