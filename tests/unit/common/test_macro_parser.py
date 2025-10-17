"""Tests for macro parser functionality."""

# ruff: noqa: PLR2004

import pytest

from griptape_nodes.common.macro_parser import (
    DateFormat,
    LowerCaseFormat,
    MacroResolutionError,
    MacroSyntaxError,
    NumericPaddingFormat,
    ParsedMacro,
    ParsedStaticValue,
    ParsedVariable,
    SeparatorFormat,
    SlugFormat,
    UpperCaseFormat,
    VariableInfo,
)


class TestFormatSpecs:
    """Test cases for format specifier classes."""

    def test_separator_format_apply(self) -> None:
        """Test SeparatorFormat.apply() appends separator."""
        fmt = SeparatorFormat(separator="_")
        assert fmt.apply("workflow") == "workflow_"
        assert fmt.apply(123) == "123_"

    def test_separator_format_reverse(self) -> None:
        """Test SeparatorFormat.reverse() removes separator."""
        fmt = SeparatorFormat(separator="_")
        assert fmt.reverse("workflow_") == "workflow"
        assert fmt.reverse("workflow") == "workflow"  # No separator to remove

    def test_numeric_padding_format_apply_int(self) -> None:
        """Test NumericPaddingFormat.apply() with integer."""
        fmt = NumericPaddingFormat(width=3)
        assert fmt.apply(5) == "005"
        assert fmt.apply(42) == "042"
        assert fmt.apply(123) == "123"
        assert fmt.apply(1234) == "1234"  # Doesn't truncate

    def test_numeric_padding_format_apply_string_digits(self) -> None:
        """Test NumericPaddingFormat.apply() with numeric string."""
        fmt = NumericPaddingFormat(width=3)
        assert fmt.apply("5") == "005"
        assert fmt.apply("42") == "042"

    def test_numeric_padding_format_apply_non_numeric_fails(self) -> None:
        """Test NumericPaddingFormat.apply() fails on non-numeric string."""
        fmt = NumericPaddingFormat(width=3)
        with pytest.raises(MacroResolutionError, match="cannot be applied to non-numeric value"):
            fmt.apply("abc")

    def test_numeric_padding_format_reverse(self) -> None:
        """Test NumericPaddingFormat.reverse() converts to int."""
        fmt = NumericPaddingFormat(width=3)
        assert fmt.reverse("005") == 5
        assert fmt.reverse("042") == 42
        assert fmt.reverse("123") == 123

    def test_numeric_padding_format_reverse_invalid(self) -> None:
        """Test NumericPaddingFormat.reverse() fails on non-numeric."""
        fmt = NumericPaddingFormat(width=3)
        with pytest.raises(MacroResolutionError, match="Cannot parse"):
            fmt.reverse("abc")

    def test_lowercase_format_apply(self) -> None:
        """Test LowerCaseFormat.apply() converts to lowercase."""
        fmt = LowerCaseFormat()
        assert fmt.apply("MyWorkflow") == "myworkflow"
        assert fmt.apply("HELLO") == "hello"
        assert fmt.apply(123) == "123"

    def test_lowercase_format_reverse(self) -> None:
        """Test LowerCaseFormat.reverse() returns as-is (cannot reverse)."""
        fmt = LowerCaseFormat()
        assert fmt.reverse("myworkflow") == "myworkflow"

    def test_uppercase_format_apply(self) -> None:
        """Test UpperCaseFormat.apply() converts to uppercase."""
        fmt = UpperCaseFormat()
        assert fmt.apply("MyWorkflow") == "MYWORKFLOW"
        assert fmt.apply("hello") == "HELLO"
        assert fmt.apply(123) == "123"

    def test_uppercase_format_reverse(self) -> None:
        """Test UpperCaseFormat.reverse() returns as-is (cannot reverse)."""
        fmt = UpperCaseFormat()
        assert fmt.reverse("MYWORKFLOW") == "MYWORKFLOW"

    def test_slug_format_apply(self) -> None:
        """Test SlugFormat.apply() slugifies value."""
        fmt = SlugFormat()
        assert fmt.apply("My Workflow") == "my-workflow"
        assert fmt.apply("Hello World!") == "hello-world"
        assert fmt.apply("test_123") == "test_123"
        assert fmt.apply("MIXED Case") == "mixed-case"

    def test_slug_format_reverse(self) -> None:
        """Test SlugFormat.reverse() returns as-is (cannot reverse)."""
        fmt = SlugFormat()
        assert fmt.reverse("my-workflow") == "my-workflow"

    def test_date_format_not_implemented(self) -> None:
        """Test DateFormat raises not implemented error."""
        fmt = DateFormat(pattern="%Y-%m-%d")
        with pytest.raises(MacroResolutionError, match="not yet fully implemented"):
            fmt.apply("2025-10-16")


class TestParsedMacro:
    """Test cases for ParsedMacro class."""

    def test_parsed_macro_initialization(self) -> None:
        """Test ParsedMacro can be initialized with segments."""
        segments = [
            ParsedStaticValue(text="inputs/"),
            ParsedVariable(
                info=VariableInfo(name="file_name", is_required=True),
                format_specs=[],
                default_value=None,
            ),
        ]
        macro = ParsedMacro(template="{inputs}/{file_name}", segments=segments)

        assert macro.template == "{inputs}/{file_name}"
        assert len(macro.segments) == 2
        assert isinstance(macro.segments[0], ParsedStaticValue)
        assert isinstance(macro.segments[1], ParsedVariable)

    def test_get_variables_extracts_variable_info(self) -> None:
        """Test get_variables() extracts VariableInfo from segments."""
        segments = [
            ParsedStaticValue(text=""),
            ParsedVariable(
                info=VariableInfo(name="inputs", is_required=True),
                format_specs=[],
                default_value=None,
            ),
            ParsedStaticValue(text="/"),
            ParsedVariable(
                info=VariableInfo(name="workflow_name", is_required=False),
                format_specs=[SeparatorFormat(separator="_")],
                default_value=None,
            ),
            ParsedVariable(
                info=VariableInfo(name="file_name", is_required=True),
                format_specs=[],
                default_value=None,
            ),
        ]
        macro = ParsedMacro(template="{inputs}/{workflow_name?:_}{file_name}", segments=segments)

        variables = macro.get_variables()

        assert len(variables) == 3
        assert variables[0] == VariableInfo(name="inputs", is_required=True)
        assert variables[1] == VariableInfo(name="workflow_name", is_required=False)
        assert variables[2] == VariableInfo(name="file_name", is_required=True)

    def test_get_variables_empty_for_no_variables(self) -> None:
        """Test get_variables() returns empty list when no variables."""
        segments = [ParsedStaticValue(text="static/path/only")]
        macro = ParsedMacro(template="static/path/only", segments=segments)

        variables = macro.get_variables()

        assert len(variables) == 0


class TestMacroParserPlaceholder:
    """Placeholder tests for MacroParser (to be implemented)."""

    def test_parse_not_implemented(self) -> None:
        """Test MacroParser.parse() raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import MacroParser

        with pytest.raises(NotImplementedError):
            MacroParser.parse("{inputs}/{file_name}")

    def test_get_variables_not_implemented(self) -> None:
        """Test MacroParser.get_variables() raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import MacroParser

        with pytest.raises(NotImplementedError):
            MacroParser.get_variables("{inputs}/{file_name}")

    def test_match_not_implemented(self) -> None:
        """Test MacroParser.match() raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import MacroParser

        # Create a minimal ParsedMacro to test with
        segments = [ParsedStaticValue(text="test")]
        parsed = ParsedMacro(template="test", segments=segments)

        with pytest.raises(NotImplementedError):
            MacroParser.match(parsed, "test")


class TestMacroResolverPlaceholder:
    """Placeholder tests for MacroResolver (to be implemented)."""

    def test_resolve_not_implemented(self) -> None:
        """Test MacroResolver.resolve() raises NotImplementedError."""
        from griptape_nodes.common.macro_parser import MacroResolver

        # Create a minimal ParsedMacro to test with
        segments = [ParsedStaticValue(text="test")]
        parsed = ParsedMacro(template="test", segments=segments)

        with pytest.raises(NotImplementedError):
            MacroResolver.resolve(parsed, {})
