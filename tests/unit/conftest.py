"""Shared fixtures for unit tests."""

import pytest

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


@pytest.fixture
def griptape_nodes() -> GriptapeNodes:
    """Provide a properly initialized GriptapeNodes instance for testing."""
    # Initialize GriptapeNodes (it's a singleton, so this returns the existing instance)
    return GriptapeNodes()
