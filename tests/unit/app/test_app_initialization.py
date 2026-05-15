"""Unit tests for orchestrator startup AppInitializationComplete event emission and library registration logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.app import app
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete


@pytest.mark.asyncio
async def test_orchestrator_emits_app_initialization_complete_with_config_libraries(monkeypatch):
    """Test that the orchestrator emits AppInitializationComplete with libraries_to_register from config."""
    # Arrange
    fake_libraries = ["lib1", "lib2"]
    monkeypatch.setattr(
        app.config_manager,
        "get_config_value",
        lambda key, **_: fake_libraries if "libraries_to_register" in key else None,
    )
    event_manager = MagicMock()
    monkeypatch.setattr(app.griptape_nodes, "EventManager", lambda: event_manager)

    # Patch Client context manager to avoid real network/async operations
    class DummyAsyncContext:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app, "Client", DummyAsyncContext)
    # Patch _run_orchestrator to prevent blocking
    monkeypatch.setattr(app, "_run_orchestrator", AsyncMock())
    mock_app_event = MagicMock()
    monkeypatch.setattr(app, "AppEvent", mock_app_event)

    # Act
    await app._run_websocket_tasks(app.Orchestrator())

    # Assert
    payload = mock_app_event.call_args_list[0][1]["payload"]
    assert isinstance(payload, AppInitializationComplete)
    assert payload.libraries_to_register == fake_libraries
    assert not payload.is_worker


@pytest.mark.asyncio
async def test_worker_emits_app_initialization_complete_with_library_name(monkeypatch):
    """Test that a Worker emits AppInitializationComplete with its library_name."""
    worker_role = app.Worker(session_id="sess", library_name="libA")
    event_manager = MagicMock()
    monkeypatch.setattr(app.griptape_nodes, "EventManager", lambda: event_manager)

    class DummyAsyncContext:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app, "Client", DummyAsyncContext)
    monkeypatch.setattr(app, "_run_worker", AsyncMock())
    mock_app_event = MagicMock()
    monkeypatch.setattr(app, "AppEvent", mock_app_event)

    # Act
    await app._run_websocket_tasks(worker_role)

    # Assert
    payload = mock_app_event.call_args_list[0][1]["payload"]
    assert isinstance(payload, AppInitializationComplete)
    assert payload.libraries_to_register == ["libA"]
    assert payload.is_worker
