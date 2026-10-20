"""Node and run timings, and the run id, ride on the execution events, so the editor can show where a run spent its time."""

from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.machines.control_flow import CompleteState, ControlFlowContext, ControlFlowMachine
from griptape_nodes.machines.dag_builder import DagNode
from griptape_nodes.machines.fsm import WorkflowState
from griptape_nodes.machines.parallel_resolution import ExecuteDagState
from griptape_nodes.retained_mode.events.execution_events import (
    ControlFlowCancelledEvent,
    FlowRunStartedEvent,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.flow_manager import FlowManager
from griptape_nodes.retained_mode.managers.node_manager import NodeManager


def _dag_node() -> DagNode:
    return DagNode(node_reference=MagicMock(spec=BaseNode))


def _engine_whose_executor(execute: AsyncMock) -> MagicMock:
    engine = MagicMock()
    engine.flow_manager.node_executor.execute = execute
    return engine


def _context() -> ControlFlowContext:
    context = ControlFlowContext.__new__(ControlFlowContext)
    context.current_nodes = []
    context.resolution_machine = MagicMock()
    return context


class TestNodeRunSeconds:
    @pytest.mark.asyncio
    async def test_a_node_that_runs_records_how_long_it_took(self) -> None:
        dag_node = _dag_node()

        await ExecuteDagState.execute_node(_engine_whose_executor(AsyncMock()), dag_node)

        assert dag_node.run_seconds is not None
        assert dag_node.run_seconds >= 0

    @pytest.mark.asyncio
    async def test_a_node_that_fails_still_records_how_long_it_ran(self) -> None:
        dag_node = _dag_node()
        engine = _engine_whose_executor(AsyncMock(side_effect=RuntimeError("boom")))

        with pytest.raises(RuntimeError, match="boom"):
            await ExecuteDagState.execute_node(engine, dag_node)

        assert dag_node.run_seconds is not None


class TestRunSeconds:
    def test_no_run_started_means_no_run_time(self) -> None:
        assert _context().seconds_since_run_started() is None

    def test_a_started_run_reports_elapsed_time_until_reset(self) -> None:
        context = _context()
        context.run_started_at = 0.0

        run_seconds = context.seconds_since_run_started()
        assert run_seconds is not None
        assert run_seconds > 0

        context.reset()
        assert context.seconds_since_run_started() is None

    @pytest.mark.asyncio
    async def test_cancelling_a_run_reports_how_long_it_ran(self) -> None:
        engine = MagicMock()
        flow_manager = FlowManager(MagicMock(spec=EventManager), engine=engine)
        machine = MagicMock()
        machine.cancel_flow = AsyncMock()
        machine.context.seconds_since_run_started.return_value = 1.5
        machine.context.end_run.return_value = "run-1"
        # Resetting the real machine clears the run's start time, so the time must be read first.
        machine.reset_machine.side_effect = lambda **_: setattr(
            machine.context.seconds_since_run_started, "return_value", None
        )
        flow_manager._global_control_flow_machine = machine
        flow_manager.check_for_existing_running_flow = MagicMock(return_value=True)

        await flow_manager.cancel_flow_run()

        payloads = [call.args[0].wrapped_event.payload for call in engine.event_manager.put_event.call_args_list]
        cancelled = [p for p in payloads if isinstance(p, ControlFlowCancelledEvent)]
        assert [p.run_seconds for p in cancelled] == [1.5]
        assert [p.run_id for p in cancelled] == ["run-1"]


class TestRunId:
    def test_a_run_hands_over_its_id_once(self) -> None:
        context = _context()
        context.run_id = "run-1"

        assert context.end_run() == "run-1"
        assert context.end_run() is None

    def test_resetting_a_run_forgets_its_id(self) -> None:
        context = _context()
        context.run_id = "run-1"

        context.reset()

        assert context.run_id is None

    def test_no_run_in_progress_means_no_run_id(self) -> None:
        flow_manager = FlowManager(MagicMock(spec=EventManager), engine=MagicMock())
        machine = MagicMock()
        machine.context.run_id = "run-1"
        flow_manager._global_control_flow_machine = machine
        flow_manager.check_for_existing_running_flow = MagicMock(return_value=False)

        # A finished run's machine lingers, and its id must not label spend made after it.
        assert flow_manager.current_run_id is None

    @pytest.mark.asyncio
    async def test_a_cancel_ends_the_run_it_cancelled_when_another_starts_meanwhile(self) -> None:
        engine = MagicMock()
        flow_manager = FlowManager(MagicMock(spec=EventManager), engine=engine)
        cancelled_run = MagicMock()
        cancelled_run.context.end_run.return_value = "run-a"
        next_run = MagicMock()
        next_run.context.end_run.return_value = "run-b"

        async def start_another_run_meanwhile() -> None:
            flow_manager._global_control_flow_machine = next_run

        cancelled_run.cancel_flow = AsyncMock(side_effect=start_another_run_meanwhile)
        flow_manager._global_control_flow_machine = cancelled_run
        flow_manager.check_for_existing_running_flow = MagicMock(return_value=True)

        await flow_manager.cancel_flow_run()

        payloads = [call.args[0].wrapped_event.payload for call in engine.event_manager.put_event.call_args_list]
        assert [p.run_id for p in payloads if isinstance(p, ControlFlowCancelledEvent)] == ["run-a"]
        cancelled_run.reset_machine.assert_called_once_with(cancel=True)
        next_run.reset_machine.assert_not_called()

    def test_a_group_run_for_another_engine_reports_that_engine_s_run(self) -> None:
        flow_manager = FlowManager(MagicMock(spec=EventManager), engine=MagicMock())
        flow_manager.parent_run_id = "parent-run"
        flow_manager._global_control_flow_machine = MagicMock()
        flow_manager.check_for_existing_running_flow = MagicMock(return_value=True)

        assert flow_manager.current_run_id == "parent-run"

    def test_a_live_run_reports_its_machine_s_id(self) -> None:
        flow_manager = FlowManager(MagicMock(spec=EventManager), engine=MagicMock())
        machine = MagicMock()
        machine.context.run_id = "run-1"
        flow_manager._global_control_flow_machine = machine
        flow_manager.check_for_existing_running_flow = MagicMock(return_value=True)

        assert flow_manager.current_run_id == "run-1"


class _EndingRun(NamedTuple):
    context: ControlFlowContext
    engine: MagicMock

    @property
    def resolved(self) -> list[tuple[str, str | None]]:
        """Each ControlFlowResolvedEvent sent, as its end node and run id."""
        calls = self.engine.event_manager.put_event.call_args_list
        payloads = [call.args[0].wrapped_event.payload for call in calls]
        return [(payload.end_node_name, payload.run_id) for payload in payloads]


class TestRunEndEvents:
    @staticmethod
    def _ending(*, end_nodes: list[str], cancel_requested: bool) -> _EndingRun:
        """A context at the end of run "run-1", with its engine to read the sent events from."""
        engine = MagicMock()
        context = _context()
        context._engine = engine
        context.is_isolated = False
        context.flow_name = "Flow"
        context.run_started_at = None
        context.run_id = "run-1"
        context.cancel_requested = cancel_requested
        nodes = []
        for name in end_nodes:
            node = MagicMock(spec=BaseNode)
            node.name = name
            nodes.append(node)
        context.current_nodes = nodes
        return _EndingRun(context=context, engine=engine)

    @pytest.mark.asyncio
    async def test_a_run_ending_on_several_nodes_names_itself_on_one_end_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A client that closes a run on its end event must see exactly one for the id."""
        monkeypatch.setattr(NodeManager, "result_parameter_values", staticmethod(lambda _node: {}))
        run = self._ending(end_nodes=["First", "Second"], cancel_requested=False)

        await CompleteState.on_enter(run.context)

        assert run.resolved == [("First", "run-1"), ("Second", None)]

    @pytest.mark.asyncio
    async def test_a_cancelled_run_leaves_its_id_to_the_cancelled_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even when a node caught the cancellation and finished, so the resolution never read CANCELED."""
        monkeypatch.setattr(NodeManager, "result_parameter_values", staticmethod(lambda _node: {}))
        run = self._ending(end_nodes=["Runner"], cancel_requested=True)

        await CompleteState.on_enter(run.context)

        assert run.resolved == [("Runner", None)]
        assert run.context.end_run() == "run-1"

    @pytest.mark.asyncio
    async def test_a_run_nobody_cancelled_names_itself_on_its_resolved_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A node task that ends cancelled on its own sends no cancelled event, so this is the run's end."""
        monkeypatch.setattr(NodeManager, "result_parameter_values", staticmethod(lambda _node: {}))
        run = self._ending(end_nodes=["Runner"], cancel_requested=False)
        run.context.resolution_machine.context.workflow_state = WorkflowState.CANCELED

        await CompleteState.on_enter(run.context)

        assert run.resolved == [("Runner", "run-1")]


class _StartedRun(NamedTuple):
    machine: ControlFlowMachine
    engine: MagicMock

    @property
    def announced(self) -> list[str]:
        """The run ids this run announced on FlowRunStartedEvent."""
        calls = self.engine.event_manager.put_event.call_args_list
        payloads = [call.args[0].wrapped_event.payload for call in calls]
        return [payload.run_id for payload in payloads if isinstance(payload, FlowRunStartedEvent)]


class TestRunIdMinting:
    """Which runs get an id of their own, and which share another run's."""

    @staticmethod
    def _machine(*, is_isolated: bool = False, parent_run_id: str | None = None) -> _StartedRun:
        """A machine with everything past choosing its run id stubbed out."""
        engine = MagicMock()
        engine.config_manager.get_config_value.side_effect = lambda _key, default=None: default
        engine.flow_manager.parent_run_id = parent_run_id
        machine = ControlFlowMachine("Flow", is_isolated=is_isolated, engine=engine)
        machine._process_nodes_for_dag = AsyncMock(return_value=[])  # type: ignore[method-assign]
        machine.start = AsyncMock()  # type: ignore[method-assign]
        return _StartedRun(machine=machine, engine=engine)

    async def _start(self, *, is_isolated: bool, parent_run_id: str | None) -> _StartedRun:
        """Start a machine once."""
        run = self._machine(is_isolated=is_isolated, parent_run_id=parent_run_id)
        await run.machine.start_flow(MagicMock(), MagicMock())
        return run

    @pytest.mark.asyncio
    async def test_a_top_level_run_mints_and_announces_its_own_id(self) -> None:
        run = await self._start(is_isolated=False, parent_run_id=None)

        assert run.machine.context.run_id is not None
        assert run.announced == [run.machine.context.run_id]

    @pytest.mark.asyncio
    async def test_a_loop_body_neither_takes_an_id_nor_announces_a_run(self) -> None:
        run = await self._start(is_isolated=True, parent_run_id=None)

        assert run.machine.context.run_id is None
        assert run.announced == []

    @pytest.mark.asyncio
    async def test_a_group_run_for_another_engine_leaves_its_events_to_that_engine(self) -> None:
        """The parent engine sends the run's start and end events; this run's would duplicate them."""
        run = await self._start(is_isolated=False, parent_run_id="parent-run")

        assert run.machine.context.run_id is None
        assert run.announced == []

    @pytest.mark.asyncio
    async def test_a_start_that_fails_setting_up_announces_no_run(self) -> None:
        """Nothing would ever end a run announced before a failed setup."""
        run = self._machine()
        run.machine._process_nodes_for_dag = AsyncMock(side_effect=RuntimeError("setup failed"))  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="setup failed"):
            await run.machine.start_flow(MagicMock(), MagicMock())

        assert run.announced == []
        assert run.machine.context.run_id is None

    @pytest.mark.asyncio
    async def test_a_start_that_fails_after_building_its_dag_announces_no_run(self) -> None:
        run = self._machine()
        run.engine.flow_manager.get_flow_by_name.side_effect = KeyError("Flow")

        with pytest.raises(KeyError):
            await run.machine.start_flow(MagicMock(), MagicMock())

        assert run.announced == []

    @pytest.mark.asyncio
    async def test_a_cancel_that_fails_leaves_the_run_uncancelled(self) -> None:
        """The run goes on, so its own ending, not a cancelled event, is its end event."""
        run = self._machine()
        run.machine.resolution_machine.cancel_all_nodes = AsyncMock(side_effect=RuntimeError("worker gone"))  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="worker gone"):
            await run.machine.cancel_flow()

        assert run.machine.context.cancel_requested is False

    @pytest.mark.asyncio
    async def test_starting_again_is_a_new_run(self) -> None:
        """Each start has its own end event, so each is a run, including a queued next start node."""
        run = self._machine()

        await run.machine.start_flow(MagicMock(), MagicMock())
        await run.machine.start_flow(MagicMock(), MagicMock())

        first, second = run.announced
        assert first != second
