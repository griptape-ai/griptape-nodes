import logging
from re import Pattern
from typing import Any, ClassVar

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    Parameter,
)
from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.engine import Engine, EngineScoped
from griptape_nodes.retained_mode.events.base_events import (
    ResultDetails,
    ResultPayload,
)
from griptape_nodes.retained_mode.events.node_events import (
    DeleteNodeRequest,
)
from griptape_nodes.retained_mode.events.object_events import (
    ClearAllObjectStateRequest,
    ClearAllObjectStateResultFailure,
    ClearAllObjectStateResultSuccess,
    RenameObjectRequest,
    RenameObjectResultFailure,
    RenameObjectResultSuccess,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    RemoveParameterFromNodeRequest,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.object_types import WorkflowObjects
from griptape_nodes.retained_mode.request_handlers import RequestScope, handles
from griptape_nodes.retained_mode.workflow_runtime import WorkflowRuntime

logger = logging.getLogger("griptape_nodes")


class ObjectManager(EngineScoped):
    request_scope: ClassVar[RequestScope] = RequestScope.HOST

    def __init__(self, _event_manager: EventManager, *, engine: Engine | None = None) -> None:
        super().__init__(engine)
        _event_manager.register_request_handlers(self)

    @handles(RenameObjectRequest)
    def on_rename_object_request(self, request: RenameObjectRequest, workflow: WorkflowRuntime) -> ResultPayload:
        # Does the source object exist?
        if request.object_name == request.requested_name:
            unchanged = RenameObjectResultSuccess(
                final_name=request.requested_name,
                result_details=f"Object '{request.requested_name}' already has the requested name",
            )
            # Nothing changed, so this is not an edit: it must not dirty the workflow or consume an
            # undo slot that would replay as a no-op.
            unchanged.altered_workflow_state = False
            return unchanged
        source_obj = workflow.objects.name_to_objects.get(request.object_name)
        if source_obj is None:
            details = f"Attempted to rename object '{request.object_name}', but no object of that name could be found."
            return RenameObjectResultFailure(next_available_name=None, result_details=details)

        # Is there a collision?
        requested_name_obj = workflow.objects.name_to_objects.get(request.requested_name)
        if requested_name_obj is None:
            final_name = request.requested_name
        else:
            # Collision. Decide what to do.
            next_name = workflow.objects.generate_name(
                type_name=source_obj.__class__.__name__, requested_name=request.requested_name
            )

            # Will the requester allow us to use the next closest name available?
            if not request.allow_next_closest_name_available:
                # Not allowed to use it :(
                # Fail it but be nice and offer the next name that WOULD HAVE been available.
                details = f"Attempted to rename object '{request.object_name}' to '{request.requested_name}'. Failed because another object of that name exists. Next available name would have been '{next_name}'."
                return RenameObjectResultFailure(next_available_name=next_name, result_details=details)
            # We'll use the next available name.
            final_name = next_name

            # Let the object's manager know. TODO: https://github.com/griptape-ai/griptape-nodes/issues/869
        match source_obj:
            case ControlFlow():
                self.engine.flow_manager.handle_flow_rename(old_name=request.object_name, new_name=final_name)
            case BaseNode():
                self.engine.node_manager.handle_node_rename(old_name=request.object_name, new_name=final_name)
            case _:
                details = f"Attempted to rename an object named '{request.object_name}', but that object wasn't of a type supported for rename."
                return RenameObjectResultFailure(next_available_name=None, result_details=details)

        # Update the object table.
        workflow.objects.name_to_objects[final_name] = source_obj
        del workflow.objects.name_to_objects[request.object_name]

        details = f"Successfully renamed object '{request.object_name}' to '{final_name}'."
        log_level = logging.DEBUG
        if final_name != request.requested_name:
            details += f" Originally requested the name '{request.requested_name}', but that was taken."
            log_level = logging.WARNING
        if log_level == logging.WARNING:
            result_details = ResultDetails(message=details, level=logging.WARNING)
        else:
            result_details = details
        return RenameObjectResultSuccess(final_name=final_name, result_details=result_details)

    @handles(ClearAllObjectStateRequest)
    async def on_clear_all_object_state_request(self, request: ClearAllObjectStateRequest) -> ResultPayload:
        if not request.i_know_what_im_doing:
            details = "Attempted to clear all object state and delete everything. Failed because they didn't know what they were doing."
            return ClearAllObjectStateResultFailure(result_details=details)

        engine = self.engine
        for runtime in engine.workflow_runtimes:
            failure = await self.clear_workflow(runtime)
            if failure is not None:
                return ClearAllObjectStateResultFailure(result_details=failure)
            engine.remove_workflow_runtime(runtime)

        engine.open_workflows_manager.announce_change()
        engine.event_manager.clear_event_suppression()

        details = "Successfully cleared all object state (deleted everything)."
        return ClearAllObjectStateResultSuccess(result_details=details)

    async def clear_workflow(self, workflow: WorkflowRuntime, *, keep_variables: bool = False) -> str | None:
        """Delete everything in `workflow`, leaving its runtime empty.

        The other open workflows are untouched. Returns why it failed, or None.

        Args:
            workflow: The workflow to clear.
            keep_variables: Keep the workflow's variables and settings, for a rebuild in the same runtime
                from a graph that doesn't record them.
        """
        # The managers the teardown calls act on the workflow the current work is bound to.
        with self.engine.bind_workflow(workflow):
            return await self._clear_bound_workflow(workflow, keep_variables=keep_variables)

    def has_objects(self) -> bool:
        """Whether the current workflow has any flows or nodes."""
        return bool(self._current_objects_or_empty().name_to_objects)

    def get_filtered_subset[T](
        self,
        name: str | Pattern | None = None,
        type: type[T] | None = None,  # noqa: A002
    ) -> dict[str, T]:
        """Filter the current workflow's objects by name pattern and/or type."""
        return self._current_objects_or_empty().get_filtered_subset(name=name, type=type)

    def generate_name_for_object(
        self, workflow: WorkflowRuntime, type_name: str, requested_name: str | None = None
    ) -> str:
        return workflow.objects.generate_name(type_name=type_name, requested_name=requested_name)

    def add_object_by_name(self, workflow: WorkflowRuntime, name: str, obj: object) -> None:
        workflow.objects.add(name, obj)

    def get_object_by_name(self, name: str) -> object:
        return self._current_objects_or_empty().name_to_objects[name]

    def has_object_with_name(self, name: str) -> bool:
        return name in self._current_objects_or_empty().name_to_objects

    def attempt_get_object_by_name(self, name: str) -> Any | None:
        return self._current_objects_or_empty().name_to_objects.get(name, None)

    def attempt_get_object_by_name_as_type[T](self, name: str, cast_type: type[T]) -> T | None:
        obj = self.attempt_get_object_by_name(name)
        if obj is not None and isinstance(obj, cast_type):
            return obj
        return None

    def del_obj_by_name(self, workflow: WorkflowRuntime, name: str) -> None:
        # Does the object have any children? delete those
        obj = workflow.objects.name_to_objects[name]
        if isinstance(obj, BaseNodeElement):
            children = obj.find_elements_by_type(BaseNodeElement)
            for child in children:
                obj.remove_child(child)
                if isinstance(child, BaseNode):
                    self.engine.handle_request(DeleteNodeRequest(child.name))
                    return
                if isinstance(child, Parameter) and isinstance(obj, BaseNode):
                    self.engine.handle_request(RemoveParameterFromNodeRequest(child.name, obj.name))
                    return
        del workflow.objects.name_to_objects[name]

    async def _clear_bound_workflow(self, workflow: WorkflowRuntime, *, keep_variables: bool) -> str | None:
        engine = self.engine
        # Cancel any in-flight run before tearing its bookkeeping down: the reset
        # below makes the flow look idle, so the cancel in
        # clear_current_workflow_data is skipped and the previous run's node tasks
        # keep going -- billing API calls, and emitting parameter updates keyed by
        # node name onto the same-named nodes of whatever run comes next.
        #
        # Best-effort: a node that refuses to cancel must not block the teardown.
        # A driver still parked holds its FSM claim until it wakes and abandons the
        # run; harmless here because deleting the flows drops the machine it holds.
        if engine.flow_manager.check_for_existing_running_flow():
            try:
                await engine.flow_manager.cancel_flow_run()
            except Exception as e:
                logger.warning("Could not cancel the running workflow before clearing it. Continuing anyway: %s", e)

        try:
            # Eliminate all execution references before deletion
            engine.flow_manager.reset_global_execution_state()
        except Exception as e:
            return f"Attempted to reset global execution state. Failed with exception: {e}"

        workflow_name = None
        if workflow.context.has_current_workflow():
            workflow_name = workflow.context.get_current_workflow_name()

        # Cancel its running flows, delete its child flows, drain its context substack, pop it.
        try:
            while workflow.context.has_current_workflow():
                engine.clear_current_workflow_data()
        except Exception as e:
            return f"Attempted to clear all object state and delete everything. Failed with exception: {e}"
        finally:
            # clear_current_workflow_data releases the objects this process holds; the workers hold their
            # own. The fan-out has to be awaited, which is why it is here and not in that sync method.
            #
            # In the finally because nothing retries this request, so a worker that was never told keeps
            # its objects for the life of the process.
            await engine.worker_manager.broadcast_local_object_teardown()

        if workflow.objects.name_to_objects:
            return f"Attempted to clear all object state, but {len(workflow.objects.name_to_objects)} object(s) remained after workflow teardown."

        if keep_variables:
            return None
        self._clear_variables_and_settings(workflow, workflow_name)
        return None

    def _current_objects_or_empty(self) -> WorkflowObjects:
        """The current workflow's objects for a lookup, which finds none when no workflow is open.

        Only lookups read through here. Adding or removing an object needs a workflow to hold it.
        """
        workflow = self.engine.current_workflow_or_none()
        if workflow is None:
            return WorkflowObjects()
        return workflow.objects

    def _clear_variables_and_settings(self, workflow: WorkflowRuntime, workflow_name: str | None) -> None:
        workflow.variables.clear()
        if workflow_name is not None:
            self.engine.workflow_manager.clear_object_state(workflow_name)
