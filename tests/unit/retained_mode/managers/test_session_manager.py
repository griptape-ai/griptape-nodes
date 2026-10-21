"""Tests for the clients a session reports to discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from griptape_nodes.retained_mode.events.app_events import (
    AppEndSessionRequest,
    AppEndSessionResultSuccess,
)
from griptape_nodes.retained_mode.managers.session_manager import SessionManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionManager:
    """A session manager whose state file lives under tmp_path."""
    monkeypatch.setattr(
        "griptape_nodes.retained_mode.managers.session_manager.engine_state_dir",
        lambda: tmp_path,
    )
    identity = Mock()
    identity.active_engine_id = "engine-1"
    return SessionManager(identity)


class TestSessionClients:
    def test_attach_is_refused_when_no_session_is_active(self, manager: SessionManager) -> None:
        assert manager.active_session_id is None

        assert manager.attach_client("nuke:shot010", "nuke") is False
        assert manager.clients == []

    def test_attach_joins_the_active_session(self, manager: SessionManager) -> None:
        manager.save_session("session-a")

        assert manager.attach_client("nuke:shot010", "nuke") is True

        (client,) = manager.clients
        assert client.client_id == "nuke:shot010"
        assert client.client_type == "nuke"
        assert client.connected_at

    def test_reattaching_the_same_client_refreshes_rather_than_duplicates(self, manager: SessionManager) -> None:
        manager.save_session("session-a")
        manager.attach_client("nuke:shot010", "nuke")
        first = manager.clients[0].connected_at

        manager.attach_client("nuke:shot010", "nuke")

        assert len(manager.clients) == 1
        assert manager.clients[0].connected_at >= first

    def test_detach_removes_only_that_client(self, manager: SessionManager) -> None:
        manager.save_session("session-a")
        manager.attach_client("nuke:shot010", "nuke")
        manager.attach_client("nuke:shot020", "nuke")

        manager.detach_client("nuke:shot010")
        manager.detach_client("never-attached")

        assert [c.client_id for c in manager.clients] == ["nuke:shot020"]

    @pytest.mark.asyncio
    async def test_ending_the_session_clears_its_clients(self, manager: SessionManager) -> None:
        manager.save_session("session-a")
        manager.attach_client("nuke:shot010", "nuke")

        result = await manager.handle_session_end_request(AppEndSessionRequest())

        assert isinstance(result, AppEndSessionResultSuccess)
        assert manager.clients == []

    def test_clients_are_not_persisted_with_the_session(self, manager: SessionManager, tmp_path: Path) -> None:
        manager.save_session("session-a")
        manager.attach_client("nuke:shot010", "nuke")

        state = (tmp_path / "engines" / "engine-1" / "sessions.json").read_text(encoding="utf-8")

        assert "nuke:shot010" not in state
