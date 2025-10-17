"""Tests for macro parser functionality."""

# ruff: noqa: PLR2004

from typing import Any

import pytest

from griptape_nodes.common.macro_parser import (
    DateFormat,
    LowerCaseFormat,
    MacroResolutionError,
    NumericPaddingFormat,
    ParsedMacro,
    ParsedSegment,
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
        segments: list[ParsedSegment] = [ParsedStaticValue(text="static/path/only")]
        macro = ParsedMacro(template="static/path/only", segments=segments)

        variables = macro.get_variables()

        assert len(variables) == 0


class TestMacroParserParseVariable:
    """Test cases for MacroParser._parse_variable() (private helper)."""

    def test_parse_variable_simple_required(self) -> None:
        """Test parsing simple required variable."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("file_name")

        assert variable.info.name == "file_name"
        assert variable.info.is_required is True
        assert len(variable.format_specs) == 0
        assert variable.default_value is None

    def test_parse_variable_optional(self) -> None:
        """Test parsing optional variable."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("workflow_name?")

        assert variable.info.name == "workflow_name"
        assert variable.info.is_required is False
        assert len(variable.format_specs) == 0

    def test_parse_variable_with_separator(self) -> None:
        """Test parsing variable with separator format."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("workflow_name?:_")

        assert variable.info.name == "workflow_name"
        assert variable.info.is_required is False
        assert len(variable.format_specs) == 1
        assert isinstance(variable.format_specs[0], SeparatorFormat)
        assert variable.format_specs[0].separator == "_"

    def test_parse_variable_with_multiple_formats(self) -> None:
        """Test parsing variable with multiple format specifiers."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("workflow_name?:_:lower")

        assert variable.info.name == "workflow_name"
        assert variable.info.is_required is False
        assert len(variable.format_specs) == 2
        assert isinstance(variable.format_specs[0], SeparatorFormat)
        assert isinstance(variable.format_specs[1], LowerCaseFormat)

    def test_parse_variable_with_numeric_padding(self) -> None:
        """Test parsing variable with numeric padding format."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("index:03")

        assert variable.info.name == "index"
        assert variable.info.is_required is True
        assert len(variable.format_specs) == 1
        assert isinstance(variable.format_specs[0], NumericPaddingFormat)
        assert variable.format_specs[0].width == 3

    def test_parse_variable_with_default_value(self) -> None:
        """Test parsing variable with default value."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("name|default_value")

        assert variable.info.name == "name"
        assert variable.default_value == "default_value"

    def test_parse_variable_with_quoted_separator(self) -> None:
        """Test parsing variable with quoted separator (disambiguate from transformation)."""
        from griptape_nodes.common.macro_parser import MacroParser

        variable = MacroParser._parse_variable("name:'lower'")

        assert variable.info.name == "name"
        assert len(variable.format_specs) == 1
        assert isinstance(variable.format_specs[0], SeparatorFormat)
        assert variable.format_specs[0].separator == "lower"


class TestMacroParserParse:
    """Test cases for MacroParser.parse() method."""

    def test_parse_simple_template_with_single_variable(self) -> None:
        """Test parsing simple template with one variable."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("{file_name}")

        assert parsed.template == "{file_name}"
        assert len(parsed.segments) == 1
        assert isinstance(parsed.segments[0], ParsedVariable)
        assert parsed.segments[0].info.name == "file_name"

    def test_parse_template_with_static_and_variable(self) -> None:
        """Test parsing template with static text and variable."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("inputs/{file_name}")

        assert parsed.template == "inputs/{file_name}"
        assert len(parsed.segments) == 2
        assert isinstance(parsed.segments[0], ParsedStaticValue)
        assert parsed.segments[0].text == "inputs/"
        assert isinstance(parsed.segments[1], ParsedVariable)
        assert parsed.segments[1].info.name == "file_name"

    def test_parse_template_with_multiple_variables(self) -> None:
        """Test parsing template with multiple variables."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("{inputs}/{workflow_name?:_}{file_name}")

        assert len(parsed.segments) == 4
        assert isinstance(parsed.segments[0], ParsedVariable)
        assert parsed.segments[0].info.name == "inputs"
        assert isinstance(parsed.segments[1], ParsedStaticValue)
        assert parsed.segments[1].text == "/"
        assert isinstance(parsed.segments[2], ParsedVariable)
        assert parsed.segments[2].info.name == "workflow_name"
        assert parsed.segments[2].info.is_required is False
        assert isinstance(parsed.segments[3], ParsedVariable)
        assert parsed.segments[3].info.name == "file_name"

    def test_parse_template_with_adjacent_variables(self) -> None:
        """Test parsing template with adjacent variables (no static text between)."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("{workflow_name}{file_name}")

        assert len(parsed.segments) == 2
        assert isinstance(parsed.segments[0], ParsedVariable)
        assert parsed.segments[0].info.name == "workflow_name"
        assert isinstance(parsed.segments[1], ParsedVariable)
        assert parsed.segments[1].info.name == "file_name"

    def test_parse_template_with_format_specs(self) -> None:
        """Test parsing template with format specifiers."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("{outputs}/{file_name:slug}_{index:03}")

        assert len(parsed.segments) == 5
        # outputs variable
        assert isinstance(parsed.segments[0], ParsedVariable)
        assert parsed.segments[0].info.name == "outputs"
        # "/" static
        assert isinstance(parsed.segments[1], ParsedStaticValue)
        assert parsed.segments[1].text == "/"
        # file_name with slug format
        assert isinstance(parsed.segments[2], ParsedVariable)
        assert parsed.segments[2].info.name == "file_name"
        assert len(parsed.segments[2].format_specs) == 1
        assert isinstance(parsed.segments[2].format_specs[0], SlugFormat)
        # "_" static
        assert isinstance(parsed.segments[3], ParsedStaticValue)
        assert parsed.segments[3].text == "_"
        # index with numeric padding
        assert isinstance(parsed.segments[4], ParsedVariable)
        assert parsed.segments[4].info.name == "index"
        assert len(parsed.segments[4].format_specs) == 1
        assert isinstance(parsed.segments[4].format_specs[0], NumericPaddingFormat)

    def test_parse_empty_template(self) -> None:
        """Test parsing empty template returns empty static value."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("")

        assert parsed.template == ""
        assert len(parsed.segments) == 1
        assert isinstance(parsed.segments[0], ParsedStaticValue)
        assert parsed.segments[0].text == ""

    def test_parse_static_only_template(self) -> None:
        """Test parsing template with only static text."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("static/path/only")

        assert len(parsed.segments) == 1
        assert isinstance(parsed.segments[0], ParsedStaticValue)
        assert parsed.segments[0].text == "static/path/only"

    def test_parse_nested_braces_fails(self) -> None:
        """Test parsing template with nested braces fails."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroSyntaxError

        with pytest.raises(MacroSyntaxError, match="Nested braces are not allowed"):
            MacroParser.parse("{outer{inner}}")

    def test_parse_unclosed_brace_fails(self) -> None:
        """Test parsing template with unclosed brace fails."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroSyntaxError

        with pytest.raises(MacroSyntaxError, match="Unclosed brace"):
            MacroParser.parse("{file_name")

    def test_parse_unmatched_closing_brace_fails(self) -> None:
        """Test parsing template with unmatched closing brace fails."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroSyntaxError

        with pytest.raises(MacroSyntaxError, match="Unmatched closing brace"):
            MacroParser.parse("file_name}")

    def test_parse_empty_variable_fails(self) -> None:
        """Test parsing template with empty variable fails."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroSyntaxError

        with pytest.raises(MacroSyntaxError, match="Empty variable"):
            MacroParser.parse("{}")


class TestMacroParserFindMatchesDetailed:
    """Test cases for MacroParser.find_matches_detailed() method."""

    @pytest.fixture
    def mock_secrets_manager(self) -> Any:
        """Create a mock SecretsManager for testing."""
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.get_secret.return_value = None
        return mock

    def test_find_matches_static_only_exact_match(self, mock_secrets_manager: Any) -> None:
        """Test matching static-only template with exact match."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("static/path/only")
        matches = MacroParser.find_matches_detailed(parsed, "static/path/only", {}, mock_secrets_manager)

        assert len(matches) == 1
        assert matches[0] == {}  # No variables to extract

    def test_find_matches_static_only_no_match(self, mock_secrets_manager: Any) -> None:
        """Test matching static-only template with no match."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("static/path/only")
        matches = MacroParser.find_matches_detailed(parsed, "different/path", {}, mock_secrets_manager)

        assert matches == []

    def test_find_matches_single_unknown_variable(self, mock_secrets_manager: Any) -> None:
        """Test matching with single unknown variable."""
        from griptape_nodes.common.macro_parser import MacroParser, VariableInfo

        parsed = MacroParser.parse("{file_name}")
        matches = MacroParser.find_matches_detailed(parsed, "image.jpg", {}, mock_secrets_manager)

        assert len(matches) == 1
        assert VariableInfo(name="file_name", is_required=True) in matches[0]
        assert matches[0][VariableInfo(name="file_name", is_required=True)] == "image.jpg"

    def test_find_matches_with_known_variable(self, mock_secrets_manager: Any) -> None:
        """Test matching with known variable provided."""
        from griptape_nodes.common.macro_parser import MacroParser, VariableInfo

        parsed = MacroParser.parse("{inputs}/{file_name}")
        matches = MacroParser.find_matches_detailed(
            parsed, "inputs/image.jpg", {"inputs": "inputs"}, mock_secrets_manager
        )

        assert len(matches) == 1
        # Both inputs and file_name should be in results
        assert VariableInfo(name="inputs", is_required=True) in matches[0]
        assert VariableInfo(name="file_name", is_required=True) in matches[0]
        assert matches[0][VariableInfo(name="inputs", is_required=True)] == "inputs"
        assert matches[0][VariableInfo(name="file_name", is_required=True)] == "image.jpg"

    def test_find_matches_known_variable_mismatch(self, mock_secrets_manager: Any) -> None:
        """Test matching fails when known variable doesn't match path."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("{inputs}/{file_name}")
        matches = MacroParser.find_matches_detailed(
            parsed, "outputs/image.jpg", {"inputs": "inputs"}, mock_secrets_manager
        )

        assert matches == []

    def test_find_matches_multiple_unknowns_with_delimiters(self, mock_secrets_manager: Any) -> None:
        """Test matching multiple unknown variables separated by static text."""
        from griptape_nodes.common.macro_parser import MacroParser, VariableInfo

        parsed = MacroParser.parse("{dir}/{file_name}")
        matches = MacroParser.find_matches_detailed(parsed, "inputs/image.jpg", {}, mock_secrets_manager)

        assert len(matches) == 1
        assert matches[0][VariableInfo(name="dir", is_required=True)] == "inputs"
        assert matches[0][VariableInfo(name="file_name", is_required=True)] == "image.jpg"

    def test_find_matches_with_numeric_padding_format(self, mock_secrets_manager: Any) -> None:
        """Test matching with numeric padding format spec reversal."""
        from griptape_nodes.common.macro_parser import MacroParser, VariableInfo

        parsed = MacroParser.parse("{file_name}_{index:03}")
        matches = MacroParser.find_matches_detailed(parsed, "render_005", {}, mock_secrets_manager)

        assert len(matches) == 1
        assert matches[0][VariableInfo(name="file_name", is_required=True)] == "render"
        assert matches[0][VariableInfo(name="index", is_required=True)] == 5  # Reversed to int

    def test_find_matches_empty_path(self, mock_secrets_manager: Any) -> None:
        """Test matching empty path against empty template."""
        from griptape_nodes.common.macro_parser import MacroParser

        parsed = MacroParser.parse("")
        matches = MacroParser.find_matches_detailed(parsed, "", {}, mock_secrets_manager)

        assert len(matches) == 1
        assert matches[0] == {}


class TestMacroResolverResolve:
    """Test cases for MacroResolver.resolve() method."""

    @pytest.fixture
    def mock_secrets_manager(self) -> Any:
        """Create a mock SecretsManager for testing."""
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.get_secret.return_value = None
        return mock

    def test_resolve_simple_variable(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with single variable."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{file_name}")
        result = MacroResolver.resolve(parsed, {"file_name": "image.jpg"}, mock_secrets_manager)

        assert result == "image.jpg"

    def test_resolve_static_and_variable(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with static text and variable."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("inputs/{file_name}")
        result = MacroResolver.resolve(parsed, {"file_name": "image.jpg"}, mock_secrets_manager)

        assert result == "inputs/image.jpg"

    def test_resolve_multiple_variables(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with multiple variables."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{inputs}/{workflow_name}/{file_name}")
        result = MacroResolver.resolve(
            parsed, {"inputs": "inputs", "workflow_name": "my_workflow", "file_name": "image.jpg"}, mock_secrets_manager
        )

        assert result == "inputs/my_workflow/image.jpg"

    def test_resolve_optional_variable_present(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with optional variable that is provided."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{inputs}/{workflow_name?:_}{file_name}")
        result = MacroResolver.resolve(
            parsed, {"inputs": "inputs", "workflow_name": "my_workflow", "file_name": "image.jpg"}, mock_secrets_manager
        )

        assert result == "inputs/my_workflow_image.jpg"

    def test_resolve_optional_variable_missing(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with optional variable that is not provided."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{inputs}/{workflow_name?:_}{file_name}")
        result = MacroResolver.resolve(parsed, {"inputs": "inputs", "file_name": "image.jpg"}, mock_secrets_manager)

        assert result == "inputs/image.jpg"

    def test_resolve_with_numeric_padding(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with numeric padding format spec."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{outputs}/{file_name}_{index:03}")
        result = MacroResolver.resolve(
            parsed, {"outputs": "outputs", "file_name": "render", "index": 5}, mock_secrets_manager
        )

        assert result == "outputs/render_005"

    def test_resolve_with_slug_format(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with slug format spec."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{outputs}/{file_name:slug}")
        result = MacroResolver.resolve(
            parsed, {"outputs": "outputs", "file_name": "My Cool File Name!"}, mock_secrets_manager
        )

        assert result == "outputs/my-cool-file-name"

    def test_resolve_with_case_formats(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with case format specs."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed_lower = MacroParser.parse("{name:lower}")
        result_lower = MacroResolver.resolve(parsed_lower, {"name": "MyFile"}, mock_secrets_manager)
        assert result_lower == "myfile"

        parsed_upper = MacroParser.parse("{name:upper}")
        result_upper = MacroResolver.resolve(parsed_upper, {"name": "MyFile"}, mock_secrets_manager)
        assert result_upper == "MYFILE"

    def test_resolve_with_multiple_format_specs(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with multiple chained format specs."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{workflow_name?:slug:_}{file_name}")
        result = MacroResolver.resolve(
            parsed, {"workflow_name": "My Workflow", "file_name": "image.jpg"}, mock_secrets_manager
        )

        assert result == "my-workflow_image.jpg"

    def test_resolve_required_variable_missing_fails(self, mock_secrets_manager: Any) -> None:
        """Test resolving template fails when required variable is missing."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolutionError, MacroResolver

        parsed = MacroParser.parse("{inputs}/{file_name}")

        with pytest.raises(MacroResolutionError, match="Cannot fully resolve macro - missing required variables"):
            MacroResolver.resolve(parsed, {"inputs": "inputs"}, mock_secrets_manager)

    def test_resolve_env_var(self) -> None:
        """Test resolving template with environment variable reference."""
        from unittest.mock import MagicMock

        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        mock_secrets = MagicMock()
        mock_secrets.get_secret.return_value = "/path/to/outputs"

        parsed = MacroParser.parse("{outputs}/{file_name}")
        result = MacroResolver.resolve(parsed, {"outputs": "$TEST_OUTPUT_DIR", "file_name": "image.jpg"}, mock_secrets)

        assert result == "/path/to/outputs/image.jpg"
        mock_secrets.get_secret.assert_called_once_with("TEST_OUTPUT_DIR", should_error_on_not_found=False)

    def test_resolve_env_var_missing_fails(self) -> None:
        """Test resolving template fails when env var is not found."""
        from unittest.mock import MagicMock

        from griptape_nodes.common.macro_parser import MacroParser, MacroResolutionError, MacroResolver

        mock_secrets = MagicMock()
        mock_secrets.get_secret.return_value = None

        parsed = MacroParser.parse("{outputs}/{file_name}")

        with pytest.raises(MacroResolutionError, match="Environment variable 'NONEXISTENT_VAR' not found"):
            MacroResolver.resolve(parsed, {"outputs": "$NONEXISTENT_VAR", "file_name": "image.jpg"}, mock_secrets)

    def test_resolve_static_only_template(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with only static text."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("static/path/only")
        result = MacroResolver.resolve(parsed, {}, mock_secrets_manager)

        assert result == "static/path/only"

    def test_resolve_empty_template(self, mock_secrets_manager: Any) -> None:
        """Test resolving empty template."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("")
        result = MacroResolver.resolve(parsed, {}, mock_secrets_manager)

        assert result == ""

    def test_resolve_integer_value(self, mock_secrets_manager: Any) -> None:
        """Test resolving template with integer value (no format spec)."""
        from griptape_nodes.common.macro_parser import MacroParser, MacroResolver

        parsed = MacroParser.parse("{count}")
        result = MacroResolver.resolve(parsed, {"count": 42}, mock_secrets_manager)

        assert result == "42"
