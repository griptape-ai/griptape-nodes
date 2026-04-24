"""Unit tests for ast_utils module."""

from __future__ import annotations

import pytest

from griptape_nodes.utils.ast_utils import rewrite_string_comments


class TestRewriteStringComments:
    def test_double_quoted_comment_rewritten(self) -> None:
        assert rewrite_string_comments('"# hello"') == "# hello"

    def test_single_quoted_comment_rewritten(self) -> None:
        assert rewrite_string_comments("'# hello'") == "# hello"

    def test_preserves_leading_indent(self) -> None:
        assert rewrite_string_comments('    "# indented"') == "    # indented"

    def test_preserves_tab_indent(self) -> None:
        assert rewrite_string_comments('\t"# tabbed"') == "\t# tabbed"

    def test_non_comment_string_literal_left_alone(self) -> None:
        # Not prefixed with '#', so it is not a comment.
        assert rewrite_string_comments('"hello"') == '"hello"'

    def test_code_lines_untouched(self) -> None:
        source = "x = 1\ny = 2"
        assert rewrite_string_comments(source) == source

    def test_multiple_lines_mixed(self) -> None:
        source = '"# first comment"\nx = 1\n    "# nested comment"\n"keep me"'
        expected = '# first comment\nx = 1\n    # nested comment\n"keep me"'
        assert rewrite_string_comments(source) == expected

    def test_empty_string(self) -> None:
        assert rewrite_string_comments("") == ""

    def test_blank_lines_between_content_preserved(self) -> None:
        source = '"# first"\n\n"# second"'
        assert rewrite_string_comments(source) == "# first\n\n# second"

    def test_too_short_literal_ignored(self) -> None:
        # Fewer than the 3-char minimum — not enough room for a "#" body.
        assert rewrite_string_comments('""') == '""'

    def test_mismatched_quotes_left_alone(self) -> None:
        # Opening double, closing single — not a well-formed single-line literal.
        assert rewrite_string_comments("\"# hello'") == "\"# hello'"

    def test_embedded_matching_quote_skipped(self) -> None:
        # The double-quoted body embeds another double quote, which means naive
        # unwrap would produce invalid output — leave it untouched.
        source = '"# has " inside"'
        assert rewrite_string_comments(source) == source

    def test_body_may_contain_opposing_quote(self) -> None:
        # ast.unparse flips quote style when the body contains the opposing
        # quote; the rewrite should still handle it.
        assert rewrite_string_comments("'# it\"s fine'") == '# it"s fine'

    def test_trailing_content_on_line_not_rewritten(self) -> None:
        # The rule is "whole-line match"; trailing code means this is not a bare
        # string statement.
        source = '"# hello" + x'
        assert rewrite_string_comments(source) == source

    def test_preserves_line_ordering(self) -> None:
        source = '"# one"\n"# two"\n"# three"'
        assert rewrite_string_comments(source) == "# one\n# two\n# three"

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ('"#"', "#"),
            ("'#'", "#"),
            ('"# a"', "# a"),
            ('    "# indented"', "    # indented"),
        ],
    )
    def test_parametrized_valid_rewrites(self, source: str, expected: str) -> None:
        assert rewrite_string_comments(source) == expected
