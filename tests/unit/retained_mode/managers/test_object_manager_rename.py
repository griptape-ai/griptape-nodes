from unittest.mock import MagicMock

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest, RenameObjectResultSuccess
from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
from griptape_nodes.retained_mode.runtime.open_workflow_set import OpenWorkflowSet


class TestRenameToTakenName:
    def test_details_name_the_requested_name(self) -> None:
        engine = MagicMock()
        engine.open_workflows = OpenWorkflowSet()
        engine.open_workflows.open("wf")
        object_manager = ObjectManager(MagicMock(), engine=engine)
        object_manager.add_object_by_name("Flow_1", MagicMock(spec=ControlFlow))
        object_manager.add_object_by_name("Taken", MagicMock(spec=ControlFlow))

        result = object_manager.on_rename_object_request(
            RenameObjectRequest(object_name="Flow_1", requested_name="Taken", allow_next_closest_name_available=True)
        )

        assert isinstance(result, RenameObjectResultSuccess)
        assert "Originally requested the name 'Taken'" in str(result.result_details)
