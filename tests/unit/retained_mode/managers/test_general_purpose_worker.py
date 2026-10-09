"""Tests for the general-purpose worker: the worker that serves no single library.

It runs the nodes of Private Execution groups, so it loads every library -- but it is no library's
worker, so it neither reports their loads nor builds their environments. The orchestrator spawns it
once its library workers have loaded, and learns it is ready from one report of its own.
"""

from __future__ import annotations

import asyncio
import sys
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events import worker_events
from griptape_nodes.retained_mode.events.app_events import (
    AppInitializationComplete,
    ReportGeneralPurposeWorkerReadyRequest,
    ReportGeneralPurposeWorkerReadyResultSuccess,
)
from griptape_nodes.retained_mode.managers.library_manager import LibraryManager
from griptape_nodes.retained_mode.managers.worker_manager import WorkerManager, WorkerRegistration

_SESSION = "sess-abc"
_WORKER = "eng-general"
_WORKER_REQUEST_TOPIC = f"sessions/{_SESSION}/workers/{_WORKER}/request"


def _worker_manager() -> WorkerManager:
    engine = MagicMock()
    engine.get_session_id.return_value = _SESSION
    engine.config_manager.get_config_value.side_effect = lambda _key, default, cast_type=None: (
        default if cast_type is None else cast_type(default)
    )
    engine.project_manager.get_pre_project_environ.return_value = {}
    manager = WorkerManager(engine=engine, event_manager=MagicMock())
    manager.attach_transport(
        send_message=AsyncMock(),
        subscribe_to_topic=AsyncMock(),
        unsubscribe_from_topic=AsyncMock(),
        request_client=MagicMock(fail_requests_by_tag=AsyncMock()),
    )
    manager._orchestrator_static_server_base_url = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return manager


def _managed_proc() -> MagicMock:
    proc = MagicMock()
    proc.wait = AsyncMock()
    return proc


def _library_manager() -> LibraryManager:
    worker_manager = MagicMock()
    worker_manager.worker_unavailable_reason.return_value = None
    manager = LibraryManager(event_manager=MagicMock(), worker_manager=worker_manager)
    engine = MagicMock()
    engine.library_manager = manager
    engine.ahandle_request = AsyncMock()
    manager._engine = engine
    for part in vars(manager).values():
        if isinstance(part, EngineScoped):
            part._engine = engine
    return manager


class TestSpawn:
    @pytest.mark.asyncio
    async def test_starts_without_a_library_or_the_command_prefix(self) -> None:
        """The prefix prepares an environment for one library, and this worker serves none."""
        manager = _worker_manager()
        resolve = MagicMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=MagicMock()) as create,
            patch("griptape_nodes.retained_mode.managers.worker_manager.resolve_worker_command", resolve),
        ):
            await manager._spawn_general_purpose_worker_when_session_ready()

        assert list(create.call_args.args) == [
            sys.executable,
            "-m",
            "griptape_nodes_app",
            "engine",
            "--session-id",
            _SESSION,
        ]
        resolve.assert_not_called()
        assert None in manager._managed_worker_processes

    @pytest.mark.asyncio
    async def test_gets_no_library_environment(self) -> None:
        manager = _worker_manager()
        environment = cast("MagicMock", manager._engine).library_manager.environment

        with patch("asyncio.create_subprocess_exec", return_value=MagicMock()) as create:
            await manager.spawn_worker(["gtn", "engine"], None)

        environment.execution_site_packages.assert_not_called()
        assert "PYTHONPATH" not in create.call_args.kwargs["env"]

    @pytest.mark.asyncio
    async def test_waits_for_library_workers_to_load_first(self) -> None:
        """Before they load, a library's own worker may still be writing the environment this one reads."""
        manager = _worker_manager()
        manager.expect_worker("Heavy Library")

        with patch("asyncio.create_subprocess_exec", return_value=MagicMock()) as create:
            spawn = asyncio.create_task(manager._spawn_general_purpose_worker_when_session_ready())
            await asyncio.sleep(0)
            create.assert_not_called()

            manager.note_library_loaded("Heavy Library")
            await asyncio.wait_for(spawn, timeout=5.0)

        create.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_start_request_without_a_library_spawns_it(self) -> None:
        manager = _worker_manager()
        manager._spawn_general_purpose_worker_when_session_ready = AsyncMock()  # type: ignore[method-assign]
        manager._spawn_when_session_ready = AsyncMock()  # type: ignore[method-assign]

        await manager.handle_start_worker_request(worker_events.StartWorkerRequest(library_name=None))
        await asyncio.sleep(0)

        manager._spawn_general_purpose_worker_when_session_ready.assert_awaited_once()
        manager._spawn_when_session_ready.assert_not_awaited()


class TestReadiness:
    def test_the_ready_report_releases_its_gate(self) -> None:
        manager = _worker_manager()
        manager.expect_worker(None)

        result = manager.handle_report_general_purpose_worker_ready_request(ReportGeneralPurposeWorkerReadyRequest())

        assert isinstance(result, ReportGeneralPurposeWorkerReadyResultSuccess)
        assert manager.has_settled(None)
        assert manager.worker_unavailable_reason(None) is None

    def test_a_library_load_does_not_release_it(self) -> None:
        manager = _worker_manager()
        manager.expect_worker(None)

        manager.note_library_loaded("Some Library")

        assert not manager.has_settled(None)


class TestLifecycle:
    """A key of None is a worker like any other: it is terminated, and what waits on it is released."""

    @pytest.mark.asyncio
    async def test_unregister_drops_its_process_and_releases_a_waiter(self) -> None:
        manager = _worker_manager()
        manager.expect_worker(None)
        manager._workers[_WORKER] = WorkerRegistration(request_topic=_WORKER_REQUEST_TOPIC, worker_key=None)
        manager._managed_worker_processes[None] = _managed_proc()

        await manager.handle_unregister_worker_request(worker_events.UnregisterWorkerRequest(worker_engine_id=_WORKER))

        assert None not in manager._managed_worker_processes
        assert manager.has_settled(None)
        assert manager.worker_unavailable_reason(None) is not None

    @pytest.mark.asyncio
    async def test_evict_terminates_its_process_and_records_why(self) -> None:
        manager = _worker_manager()
        manager.expect_worker(None)
        proc = _managed_proc()
        manager._workers[_WORKER] = WorkerRegistration(request_topic=_WORKER_REQUEST_TOPIC, worker_key=None)
        manager._managed_worker_processes[None] = proc

        await manager.evict_worker(_WORKER)

        proc.terminate.assert_called_once()
        assert None not in manager._managed_worker_processes
        reason = manager.worker_unavailable_reason(None)
        assert reason is not None
        assert "stopped responding" in reason

    @pytest.mark.asyncio
    async def test_reset_terminates_it(self) -> None:
        manager = _worker_manager()
        proc = _managed_proc()
        manager._managed_worker_processes[None] = proc

        await manager.reset_workers()

        proc.terminate.assert_called_once()


class TestStartRequest:
    """The orchestrator asks for it alongside its library workers, only while the beta feature is on."""

    @pytest.mark.asyncio
    async def test_requested_when_the_beta_feature_is_on(self) -> None:
        manager = _library_manager()
        worker_manager = cast("MagicMock", manager._worker_manager)
        worker_manager.get_worker_for_key.return_value = None
        worker_manager.has_settled.return_value = True

        with patch("griptape_nodes.retained_mode.managers.library.workers.is_beta_enabled", return_value=True):
            await manager.workers._start_workers()

        worker_manager.expect_worker.assert_called_once_with(None)
        cast("MagicMock", manager._engine).ahandle_request.assert_awaited_once_with(
            worker_events.StartWorkerRequest(library_name=None)
        )

    @pytest.mark.asyncio
    async def test_not_requested_when_the_beta_feature_is_off(self) -> None:
        manager = _library_manager()

        with patch("griptape_nodes.retained_mode.managers.library.workers.is_beta_enabled", return_value=False):
            await manager.workers._start_workers()

        cast("MagicMock", manager._engine).ahandle_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_requested_again_while_one_is_registered(self) -> None:
        manager = _library_manager()
        worker_manager = cast("MagicMock", manager._worker_manager)
        worker_manager.get_worker_for_key.return_value = (_WORKER, _WORKER_REQUEST_TOPIC)
        worker_manager.has_settled.return_value = True

        with patch("griptape_nodes.retained_mode.managers.library.workers.is_beta_enabled", return_value=True):
            await manager.workers._start_workers()

        worker_manager.expect_worker.assert_not_called()
        cast("MagicMock", manager._engine).ahandle_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_requested_again_while_one_is_starting(self) -> None:
        """A second request would reset the gate the first spawn is due to release, and fork twice."""
        manager = _library_manager()
        worker_manager = cast("MagicMock", manager._worker_manager)
        worker_manager.get_worker_for_key.return_value = None
        worker_manager.has_settled.return_value = False

        with patch("griptape_nodes.retained_mode.managers.library.workers.is_beta_enabled", return_value=True):
            await manager.workers._start_workers()

        worker_manager.expect_worker.assert_not_called()
        cast("MagicMock", manager._engine).ahandle_request.assert_not_awaited()


def _initializing_library_manager() -> LibraryManager:
    """A LibraryManager whose app-init steps around the library load are inert."""
    manager = _library_manager()
    engine = cast("MagicMock", manager._engine)
    engine.get_session_id.return_value = None
    engine.workflow_manager = AsyncMock()
    manager.provisioning.ensure_libraries_from_config = AsyncMock()  # type: ignore[method-assign]
    manager.discovery.migrate_old_xdg_library_paths = MagicMock()  # type: ignore[method-assign]
    manager.workers.maybe_start_workers_for_existing_session = AsyncMock()  # type: ignore[method-assign]
    manager._collect_library_workflow_files = AsyncMock(return_value=[])  # type: ignore[method-assign]
    manager.load_all_libraries_from_config = AsyncMock(return_value=[])  # type: ignore[method-assign]
    manager.workers.report_general_purpose_worker_ready = AsyncMock()  # type: ignore[method-assign]
    return manager


class TestWorkerSideLoading:
    @pytest.mark.asyncio
    async def test_loads_every_library_and_then_reports_ready(self) -> None:
        manager = _initializing_library_manager()

        await manager.on_app_initialization_complete(
            AppInitializationComplete(is_worker=True, is_general_purpose_worker=True)
        )

        cast("AsyncMock", manager.load_all_libraries_from_config).assert_awaited_once_with(target_library_names=None)
        cast("AsyncMock", manager.workers.report_general_purpose_worker_ready).assert_awaited_once()
        assert manager.is_general_purpose_worker

    @pytest.mark.asyncio
    async def test_a_library_worker_still_loads_only_its_library_and_reports_no_readiness(self) -> None:
        manager = _initializing_library_manager()

        await manager.on_app_initialization_complete(
            AppInitializationComplete(is_worker=True, libraries_to_register=["Heavy Library"])
        )

        cast("AsyncMock", manager.load_all_libraries_from_config).assert_awaited_once_with(
            target_library_names=["Heavy Library"]
        )
        cast("AsyncMock", manager.workers.report_general_purpose_worker_ready).assert_not_awaited()
        assert not manager.is_general_purpose_worker

    @pytest.mark.asyncio
    async def test_the_flag_means_nothing_on_the_orchestrator(self) -> None:
        manager = _initializing_library_manager()

        await manager.on_app_initialization_complete(AppInitializationComplete(is_general_purpose_worker=True))

        cast("AsyncMock", manager.workers.report_general_purpose_worker_ready).assert_not_awaited()
        assert not manager.is_general_purpose_worker

    def test_it_is_none_of_its_libraries_worker(self) -> None:
        """So it claims an edit-time environment only where nothing has built one."""
        manager = _library_manager()
        manager._is_worker = True
        manager._is_general_purpose_worker = True

        assert not manager.dependencies._is_one_of_my_target_libraries("Any Library")

    @pytest.mark.asyncio
    async def test_the_ready_report_goes_through_the_load_reporter(self) -> None:
        manager = _library_manager()
        reporter = AsyncMock()
        manager.workers.register_library_load_reporter(reporter)

        await manager.workers.report_general_purpose_worker_ready()

        reporter.assert_awaited_once_with(ReportGeneralPurposeWorkerReadyRequest())
