"""Exceptions for macro language parsing and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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


class MacroMatchFailureReason(StrEnum):
    """Reason why path matching failed."""

    NO_MATCH = "NO_MATCH"
    INVALID_MACRO_SYNTAX = "INVALID_MACRO_SYNTAX"


class MacroParseFailureReason(StrEnum):
    """Reason why macro parsing failed."""

    SYNTAX_ERROR = "SYNTAX_ERROR"


@dataclass
class MacroMatchFailure:
    """Details about why a macro match failed."""

    failure_reason: MacroMatchFailureReason
    expected_pattern: str
    known_variables_used: dict[str, str | int]
    error_details: str


@dataclass
class MacroParseFailure:
    """Details about why macro parsing failed."""

    failure_reason: MacroParseFailureReason
    error_position: int | None
    error_details: str
