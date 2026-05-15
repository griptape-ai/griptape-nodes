"""Unit tests for orchestrator startup AppInitializationComplete event emission and library registration logic."""

import asyncio
from unittest.mock import patch, MagicMock
import pytest

from griptape_nodes.app import app
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete

@pytest.mark.asyncio
async def test_orchestrator_emits_app_initialization_complete_with_config_libraries(monkeypatch):
    """
    Test that the orchestrator emits AppInitializationComplete with libraries_to_register from config.
    """
    # Arrange
    fake_libraries = ["lib1", "lib2"]
    monkeypatch.setattr(app.config_manager, "get_config_value", lambda key, **_: fake_libraries if "libraries_to_register" in key else None)
    event_manager = MagicMock()
    monkeypatch.setattr(app.griptape_nodes, "EventManager", lambda: event_manager)
    monkeypatch.setattr(app, "Client", MagicMock())
    monkeypatch.setattr(app, "AppEvent", AppInitializationComplete)

    # Act
    await app._run_websocket_tasks(app.Orchestrator())

    # Assert
    # The first event should be AppInitializationComplete with correct libraries
    assert event_manager.put_event.call_args_list[0][0][0].payload.libraries_to_register == fake_libraries
    assert not event_manager.put_event.call_args_list[0][0][0].payload.is_worker

@pytest.mark.asyncio
async def test_worker_emits_app_initialization_complete_with_library_name(monkeypatch):
    """
    Test that a Worker emits AppInitializationComplete with its library_name.
    """
    worker_role = app.Worker(session_id="sess", library_name="libA")
    event_manager = MagicMock()
    monkeypatch.setattr(app.griptape_nodes, "EventManager", lambda: event_manager)
    monkeypatch.setattr(app, "Client", MagicMock())
    monkeypatch.setattr(app, "AppEvent", AppInitializationComplete)

    await app._run_websocket_tasks(worker_role)

    assert event_manager.put_event.call_args_list[0][0][0].payload.libraries_to_register == ["libA"]
    assert event_manager.put_event.call_args_list[0][0][0].payload.is_worker
