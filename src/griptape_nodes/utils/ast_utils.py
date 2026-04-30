"""Utility functions for working with `ast`-generated source code."""

from __future__ import annotations


def rewrite_string_comments(source: str) -> str:
    """Turn bare-string statements that start with `#` into real Python comments.

    Only whole-line matches are rewritten; indentation is preserved so comments inside
    functions / `with` blocks stay indented correctly. The body may contain the
    opposing quote character (ast.unparse flips quoting style when the body already
    contains one) but must not contain the enclosing quote.
    """
    # Smallest valid bare-string comment is `"#"` or `'#'` — three characters.
    min_quoted_len = 3
    rewritten_lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if len(stripped) >= min_quoted_len and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]:
            quote = stripped[0]
            body = stripped[1:-1]
            # Must be a single-line literal with no embedded matching quote,
            # and must look like a comment ("#..." with no surprises).
            if quote not in body and body.startswith("#"):
                rewritten_lines.append(f"{indent}{body}")
                continue
        rewritten_lines.append(line)
    return "\n".join(rewritten_lines)
