"""Tests for library worker configuration and LibraryManager callback mechanism."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.node_library.library_registry import LibraryMetadata, WorkerConfig
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager


def _make_metadata(**kwargs: Any) -> LibraryMetadata:
    return LibraryMetadata(
        author="test",
        description="test library",
        library_version="1.0.0",
        engine_version="1.0.0",
        tags=[],
        **kwargs,
    )


def _make_library_manager() -> LibraryManager:
    return LibraryManager(event_manager=MagicMock())


class TestWorkerConfig:
    def test_defaults_to_disabled(self) -> None:
        config = WorkerConfig()

        assert config.enabled is False

    def test_can_be_enabled(self) -> None:
        config = WorkerConfig(enabled=True)

        assert config.enabled is True

    def test_parses_from_dict(self) -> None:
        config = WorkerConfig.model_validate({"enabled": True})

        assert config.enabled is True

    def test_unknown_fields_are_ignored(self) -> None:
        """Extra fields in JSON are silently ignored for forward compatibility."""
        config = WorkerConfig.model_validate({"enabled": True, "count": 3, "spinup_policy": "eager"})

        assert config.enabled is True


class TestLibraryMetadataWorkerField:
    def test_worker_defaults_to_none(self) -> None:
        metadata = _make_metadata()

        assert metadata.worker is None

    def test_worker_can_be_set_enabled(self) -> None:
        metadata = _make_metadata(worker=WorkerConfig(enabled=True))

        assert metadata.worker is not None
        assert metadata.worker.enabled is True

    def test_worker_parses_from_dict(self) -> None:
        metadata = _make_metadata(worker={"enabled": True})

        assert metadata.worker is not None
        assert metadata.worker.enabled is True

    def test_worker_disabled_explicitly(self) -> None:
        metadata = _make_metadata(worker={"enabled": False})

        assert metadata.worker is not None
        assert metadata.worker.enabled is False


class TestLibraryInfoRequiresWorker:
    def test_defaults_to_false(self) -> None:
        info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.DISCOVERED,
            fitness=LibraryManager.LibraryFitness.NOT_EVALUATED,
            library_path="/some/path.json",
            is_sandbox=False,
        )

        assert info.requires_worker is False

    def test_can_be_set_true(self) -> None:
        info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/some/path.json",
            is_sandbox=False,
            requires_worker=True,
        )

        assert info.requires_worker is True


class TestRegisterLibraryLoadedCallback:
    def test_registers_single_callback(self) -> None:
        mgr = _make_library_manager()
        cb = MagicMock()

        mgr.register_library_loaded_callback(cb)

        assert cb in mgr._library_loaded_callbacks

    def test_multiple_callbacks_all_registered(self) -> None:
        mgr = _make_library_manager()
        cb1, cb2 = MagicMock(), MagicMock()

        mgr.register_library_loaded_callback(cb1)
        mgr.register_library_loaded_callback(cb2)

        assert cb1 in mgr._library_loaded_callbacks
        assert cb2 in mgr._library_loaded_callbacks

    def test_callbacks_invoked_in_registration_order(self) -> None:
        mgr = _make_library_manager()
        call_order: list[int] = []

        mgr.register_library_loaded_callback(lambda _: call_order.append(1))
        mgr.register_library_loaded_callback(lambda _: call_order.append(2))

        info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/test.json",
            is_sandbox=False,
        )
        for cb in mgr._library_loaded_callbacks:
            cb(info)

        assert call_order == [1, 2]

    def test_failing_callback_does_not_prevent_others(self) -> None:
        """A callback that raises must not stop subsequent callbacks from running."""
        mgr = _make_library_manager()
        second_cb = MagicMock()

        def bad_callback(_: LibraryManager.LibraryInfo) -> None:
            msg = "boom"
            raise ValueError(msg)

        mgr.register_library_loaded_callback(bad_callback)
        mgr.register_library_loaded_callback(second_cb)

        info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/test.json",
            is_sandbox=False,
        )

        # Simulate what _attempt_load_nodes_from_library does
        for cb in mgr._library_loaded_callbacks:
            with contextlib.suppress(Exception):
                cb(info)

        second_cb.assert_called_once_with(info)

    @pytest.mark.asyncio
    async def test_no_callbacks_by_default(self) -> None:
        mgr = _make_library_manager()

        assert mgr._library_loaded_callbacks == []


class TestGetWorkerForLibrary:
    def test_returns_none_for_none_library_name(self) -> None:
        mgr = _make_library_manager()

        result = mgr.get_worker_for_library(None)

        assert result is None

    def test_returns_worker_when_registered(self) -> None:
        mgr = _make_library_manager()
        worker_engine_id = "eng-xyz"
        worker_request_topic = "sessions/s/workers/eng-xyz/request"
        lib_info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/some/path.json",
            is_sandbox=False,
            library_name="my_lib",
            requires_worker=True,
        )

        with patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn:
            mock_gtn.WorkerManager.return_value.get_worker_for_key.return_value = (
                worker_engine_id,
                worker_request_topic,
            )
            mgr._library_file_path_to_info["/some/path.json"] = lib_info
            result = mgr.get_worker_for_library("my_lib")

        assert result == (worker_engine_id, worker_request_topic)

    def test_returns_none_when_no_worker_and_not_required(self) -> None:
        mgr = _make_library_manager()
        lib_info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/some/path.json",
            is_sandbox=False,
            library_name="my_lib",
            requires_worker=False,
        )

        with patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn:
            mock_gtn.WorkerManager.return_value.get_worker_for_key.return_value = None
            mgr._library_file_path_to_info["/some/path.json"] = lib_info
            result = mgr.get_worker_for_library("my_lib")

        assert result is None

    def test_raises_when_library_requires_worker_but_none_registered(self) -> None:
        mgr = _make_library_manager()
        lib_info = LibraryManager.LibraryInfo(
            lifecycle_state=LibraryManager.LibraryLifecycleState.LOADED,
            fitness=LibraryManager.LibraryFitness.GOOD,
            library_path="/some/path.json",
            is_sandbox=False,
            library_name="my_lib",
            requires_worker=True,
        )

        with patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn:
            mock_gtn.WorkerManager.return_value.get_worker_for_key.return_value = None
            mgr._library_file_path_to_info["/some/path.json"] = lib_info

            with pytest.raises(RuntimeError, match="requires a dedicated worker"):
                mgr.get_worker_for_library("my_lib")


class TestMaybePrintEngineReadyBanner:
    def test_skips_when_is_worker(self) -> None:
        mgr = _make_library_manager()

        with patch("griptape_nodes.retained_mode.managers.library_manager.console") as mock_console:
            mgr._maybe_print_engine_ready_banner(is_worker=True)

        mock_console.print.assert_not_called()

    def test_prints_panel_when_not_worker(self) -> None:
        mgr = _make_library_manager()

        with (
            patch(
                "griptape_nodes.retained_mode.managers.library_manager.get_complete_version_string",
                return_value="1.0.0",
            ),
            patch("griptape_nodes.retained_mode.managers.library_manager.GriptapeNodes") as mock_gtn,
            patch("griptape_nodes.retained_mode.managers.library_manager.console") as mock_console,
        ):
            mock_gtn.get_session_id.return_value = None
            mock_gtn.UserManager.return_value.user = None
            mock_gtn.UserManager.return_value.user_organization = None

            mgr._maybe_print_engine_ready_banner(is_worker=False)

        mock_console.print.assert_called_once()
