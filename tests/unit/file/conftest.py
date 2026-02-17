"""Shared fixtures for file system tests."""

from collections.abc import Generator
from pathlib import Path

import pytest

from griptape_nodes.file.file_driver import FileDriverRegistry


@pytest.fixture
def temp_file(tmp_path: Path) -> Path:
    """Create a temporary file with known content."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    return file_path


@pytest.fixture
def clear_registry() -> Generator[None, None, None]:
    """Clear driver registry before/after tests.

    Driver registration is handled by OSManager._initialize_file_drivers().
    This fixture provides a clean slate for tests that need to test registration logic.
    """
    yield

    FileDriverRegistry.clear()
