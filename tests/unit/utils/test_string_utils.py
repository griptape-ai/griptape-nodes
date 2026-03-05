"""Unit tests for string_utils module."""

from __future__ import annotations

import pytest

from griptape_nodes.utils.string_utils import derive_registry_key, normalize_display_name


class TestDeriveRegistryKey:
    def test_flat_workflow(self) -> None:
        assert derive_registry_key("my_workflow.py") == "my_workflow"

    def test_subdirectory(self) -> None:
        assert derive_registry_key("subdir/my_workflow.py") == "subdir/my_workflow"

    def test_nested_subdirectory(self) -> None:
        assert derive_registry_key("a/b/c/my_workflow.py") == "a/b/c/my_workflow"

    def test_backslash_normalization(self) -> None:
        assert derive_registry_key("subdir\\my_workflow.py") == "subdir/my_workflow"

    def test_no_extension(self) -> None:
        assert derive_registry_key("my_workflow") == "my_workflow"

    def test_dot_prefix_normalized(self) -> None:
        assert derive_registry_key("./my_workflow.py") == "my_workflow"

    @pytest.mark.parametrize(
        ("input_path", "expected"),
        [
            ("my_workflow.py", "my_workflow"),
            ("subdir/my_workflow.py", "subdir/my_workflow"),
            ("a/b/deep_workflow.py", "a/b/deep_workflow"),
            ("windows\\path\\workflow.py", "windows/path/workflow"),
        ],
    )
    def test_known_inputs(self, input_path: str, expected: str) -> None:
        assert derive_registry_key(input_path) == expected


class TestNormalizeDisplayName:
    def test_simple_lowercase(self) -> None:
        assert normalize_display_name("Image") == "image"

    def test_spaces_replaced_with_underscores(self) -> None:
        assert normalize_display_name("Standard Thumbnail Generation") == "standard_thumbnail_generation"

    def test_special_chars_removed(self) -> None:
        assert normalize_display_name("My Cool Workflow!") == "my_cool_workflow"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert normalize_display_name("  Hello World  ") == "hello_world"

    def test_hyphens_preserved(self) -> None:
        assert normalize_display_name("my-workflow") == "my-workflow"

    def test_multiple_spaces_collapsed(self) -> None:
        assert normalize_display_name("hello   world") == "hello_world"

    def test_mixed_case(self) -> None:
        assert normalize_display_name("My WORKFLOW Name") == "my_workflow_name"

    def test_numbers_preserved(self) -> None:
        assert normalize_display_name("Workflow 2") == "workflow_2"

    def test_only_special_chars(self) -> None:
        assert normalize_display_name("!!!") == ""

    def test_empty_string(self) -> None:
        assert normalize_display_name("") == ""

    def test_already_normalized(self) -> None:
        assert normalize_display_name("already_normalized") == "already_normalized"

    @pytest.mark.parametrize(
        ("input_name", "expected"),
        [
            ("Image", "image"),
            ("Standard Thumbnail Generation", "standard_thumbnail_generation"),
            ("My Cool Workflow!", "my_cool_workflow"),
            ("  Hello World  ", "hello_world"),
            ("WebP Preview", "webp_preview"),
        ],
    )
    def test_known_inputs(self, input_name: str, expected: str) -> None:
        assert normalize_display_name(input_name) == expected
