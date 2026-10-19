from unittest.mock import MagicMock

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest, RenameObjectResultSuccess
from griptape_nodes.retained_mode.managers.object_manager import ObjectManager
from tests.unit.mock_engine import mock_engine_with_workflow_runtime


class TestRenameToTakenName:
    def test_details_name_the_requested_name(self) -> None:
        engine = mock_engine_with_workflow_runtime()
        object_manager = ObjectManager(MagicMock(), engine=engine)
        object_manager.add_object_by_name(engine.current_workflow, "Flow_1", MagicMock(spec=ControlFlow))
        object_manager.add_object_by_name(engine.current_workflow, "Taken", MagicMock(spec=ControlFlow))

        result = object_manager.on_rename_object_request(
            RenameObjectRequest(object_name="Flow_1", requested_name="Taken", allow_next_closest_name_available=True),
            engine.current_workflow,
        )

        assert isinstance(result, RenameObjectResultSuccess)
        assert "Originally requested the name 'Taken'" in str(result.result_details)
