"""Format specifier classes for macro variable transformations."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from griptape_nodes.common.macro_parser.exceptions import MacroResolutionError, MacroResolutionFailureReason


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
                raise MacroResolutionError(
                    msg,
                    failure_reason=MacroResolutionFailureReason.NUMERIC_PADDING_ON_NON_NUMERIC,
                )
            value = int(value)
        return f"{value:0{self.width}d}"

    def reverse(self, value: str) -> int:
        """Reverse numeric padding: "005" → 5."""
        try:
            return int(value)
        except ValueError as e:
            msg = f"Cannot parse '{value}' as integer"
            raise MacroResolutionError(
                msg,
                failure_reason=MacroResolutionFailureReason.INVALID_INTEGER_PARSE,
            ) from e


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
        # TODO(https://github.com/griptape-ai/griptape-nodes/issues/2717): Implement date formatting
        msg = "DateFormat not yet fully implemented"
        raise MacroResolutionError(
            msg,
            failure_reason=MacroResolutionFailureReason.DATE_FORMAT_NOT_IMPLEMENTED,
        )

    def reverse(self, value: str) -> str:
        """Attempt to parse date string."""
        # TODO(https://github.com/griptape-ai/griptape-nodes/issues/2717): Implement date parsing
        return value


# Module-level registry of known format transformations
FORMAT_REGISTRY: dict[str, FormatSpec] = {
    "lower": LowerCaseFormat(),
    "upper": UpperCaseFormat(),
    "slug": SlugFormat(),
}
