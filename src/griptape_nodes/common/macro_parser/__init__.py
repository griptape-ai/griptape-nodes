"""Macro language parser for template-based path generation."""

from griptape_nodes.common.macro_parser.core import ParsedMacro
from griptape_nodes.common.macro_parser.exceptions import (
    MacroMatchFailure,
    MacroMatchFailureReason,
    MacroParseFailure,
    MacroParseFailureReason,
    MacroResolutionError,
    MacroResolutionFailure,
    MacroResolutionFailureReason,
    MacroSyntaxError,
)
from griptape_nodes.common.macro_parser.formats import (
    DateFormat,
    LowerCaseFormat,
    NumericPaddingFormat,
    SeparatorFormat,
    SlugFormat,
    UpperCaseFormat,
)
from griptape_nodes.common.macro_parser.segments import (
    MacroVariables,
    ParsedSequenceToken,
    ParsedStaticValue,
    ParsedVariable,
    SequenceTokenSyntax,
    VariableInfo,
)
from griptape_nodes.common.macro_parser.sequence import (
    MissingFrameError,
    MissingFrameMarker,
    MissingFramePolicy,
    Sequence,
    SequenceTemplate,
    SequenceTemplateError,
)

__all__ = [
    "DateFormat",
    "LowerCaseFormat",
    "MacroMatchFailure",
    "MacroMatchFailureReason",
    "MacroParseFailure",
    "MacroParseFailureReason",
    "MacroResolutionError",
    "MacroResolutionFailure",
    "MacroResolutionFailureReason",
    "MacroSyntaxError",
    "MacroVariables",
    "MissingFrameError",
    "MissingFrameMarker",
    "MissingFramePolicy",
    "NumericPaddingFormat",
    "ParsedMacro",
    "ParsedSequenceToken",
    "ParsedStaticValue",
    "ParsedVariable",
    "SeparatorFormat",
    "Sequence",
    "SequenceTemplate",
    "SequenceTemplateError",
    "SequenceTokenSyntax",
    "SlugFormat",
    "UpperCaseFormat",
    "VariableInfo",
]
