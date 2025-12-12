from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    DeleteFileRequest,
    DeleteFileResultFailure,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    WriteFileRequest,
    WriteFileResultFailure,
)
from griptape_nodes.retained_mode.events.timeline_events import (
    CreateTimelineRequest,
    CreateTimelineResultFailure,
    CreateTimelineResultSuccess,
    DeleteTimelineRequest,
    DeleteTimelineResultFailure,
    DeleteTimelineResultSuccess,
    GetTimelineRequest,
    GetTimelineResultFailure,
    GetTimelineResultSuccess,
    ListTimelinesRequest,
    ListTimelinesResultFailure,
    ListTimelinesResultSuccess,
    WriteTimelineRequest,
    WriteTimelineResultFailure,
    WriteTimelineResultSuccess,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.utils.metaclasses import SingletonMeta


class TimelineManager(metaclass=SingletonMeta):
    """Manager for handling Timeline operations (list/get/write) with auto-persistence."""

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(ListTimelinesRequest, self.on_list_timelines_request)
        event_manager.assign_manager_to_request_type(GetTimelineRequest, self.on_get_timeline_request)
        event_manager.assign_manager_to_request_type(WriteTimelineRequest, self.on_write_timeline_request)
        event_manager.assign_manager_to_request_type(CreateTimelineRequest, self.on_create_timeline_request)
        event_manager.assign_manager_to_request_type(DeleteTimelineRequest, self.on_delete_timeline_request)

    def _get_timelines_dir(self) -> Path:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Keep it simple for now: workspace/timelines
        base = GriptapeNodes.ConfigManager().workspace_path
        timelines_dir = base / "timelines"
        timelines_dir.mkdir(parents=True, exist_ok=True)
        return timelines_dir

    def _sanitize_name(self, name: str) -> str:
        # Simple name sanitizer to avoid path traversal; keep alnum, dash, underscore, dot
        safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name).strip("._")
        return safe or "untitled"

    def _timeline_path(self, name: str) -> Path:
        safe_name = self._sanitize_name(name)
        return self._get_timelines_dir() / f"{safe_name}.json"

    def on_list_timelines_request(self, request: ListTimelinesRequest) -> ResultPayload:  # noqa: ARG002
        try:
            timelines_dir = self._get_timelines_dir()
            names = [
                p.stem
                for p in sorted(timelines_dir.glob("*.json"))
                if p.is_file()
            ]
            return ListTimelinesResultSuccess(names=names, result_details="Successfully listed timelines.")
        except Exception as e:
            return ListTimelinesResultFailure(result_details=f"Failed to list timelines: {e}")

    def on_get_timeline_request(self, request: GetTimelineRequest) -> ResultPayload:
        path = self._timeline_path(request.name)
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        os_manager = GriptapeNodes.OSManager()
        read_result = os_manager.on_read_file_request(ReadFileRequest(file_path=str(path)))
        if isinstance(read_result, ReadFileResultFailure):
            return GetTimelineResultFailure(result_details=str(read_result.result_details))

        assert isinstance(read_result, ReadFileResultSuccess)
        raw_content = read_result.content
        parsed_content: Any
        try:
            if isinstance(raw_content, (bytes, bytearray)):
                raw_text = raw_content.decode(read_result.encoding or "utf-8")
            else:
                raw_text = raw_content
            parsed_content = json.loads(raw_text)
        except Exception:
            parsed_content = raw_content
        return GetTimelineResultSuccess(name=request.name, content=parsed_content, result_details="Loaded timeline.")

    def on_write_timeline_request(self, request: WriteTimelineRequest) -> ResultPayload:
        path = self._timeline_path(request.name)
        try:
            serialized = json.dumps(request.content, indent=2, ensure_ascii=False)
        except Exception:
            # Best-effort fallback to string
            serialized = json.dumps(str(request.content), indent=2, ensure_ascii=False)

        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Check disk space requirement similar to workflows (reuse same setting)
        config_manager = GriptapeNodes.ConfigManager()
        min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_workflows")
        if not OSManager.check_available_disk_space(path.parent, min_space_gb):
            error_msg = OSManager.format_disk_space_error(path.parent)
            return WriteTimelineResultFailure(
                result_details=f"Insufficient disk space to save timeline '{request.name}': {error_msg}"
            )

        os_manager = GriptapeNodes.OSManager()
        write_result = os_manager.on_write_file_request(
            WriteFileRequest(
                file_path=str(path),
                content=serialized,
                encoding="utf-8",
                append=False,
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
                create_parents=True,
            )
        )
        if isinstance(write_result, WriteFileResultFailure):
            return WriteTimelineResultFailure(result_details=str(write_result.result_details))

        return WriteTimelineResultSuccess(name=request.name, path=str(path), result_details="Saved timeline.")

    def on_create_timeline_request(self, request: CreateTimelineRequest) -> ResultPayload:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        path = self._timeline_path(request.name)
        # Fail if exists
        if Path(path).exists():
            return CreateTimelineResultFailure(result_details=f"Timeline '{request.name}' already exists.")
        content = request.content if request.content is not None else {"blocks": {}}
        try:
            serialized = json.dumps(content, indent=2, ensure_ascii=False)
        except Exception:
            serialized = json.dumps(str(content), indent=2, ensure_ascii=False)

        config_manager = GriptapeNodes.ConfigManager()
        min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_workflows")
        if not OSManager.check_available_disk_space(Path(path).parent, min_space_gb):
            error_msg = OSManager.format_disk_space_error(Path(path).parent)
            return CreateTimelineResultFailure(
                result_details=f"Insufficient disk space to create timeline '{request.name}': {error_msg}"
            )

        os_manager = GriptapeNodes.OSManager()
        write_result = os_manager.on_write_file_request(
            WriteFileRequest(
                file_path=str(path),
                content=serialized,
                encoding="utf-8",
                append=False,
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
                create_parents=True,
            )
        )
        if isinstance(write_result, WriteFileResultFailure):
            return CreateTimelineResultFailure(result_details=str(write_result.result_details))
        return CreateTimelineResultSuccess(name=request.name, path=str(path), result_details="Created timeline.")

    def on_delete_timeline_request(self, request: DeleteTimelineRequest) -> ResultPayload:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        path = self._timeline_path(request.name)
        if not Path(path).exists():
            return DeleteTimelineResultFailure(result_details=f"Timeline '{request.name}' not found.")
        delete_payload = GriptapeNodes.handle_request(DeleteFileRequest(path=str(path)))
        if isinstance(delete_payload, DeleteFileResultFailure):
            return DeleteTimelineResultFailure(result_details=str(delete_payload.result_details))
        return DeleteTimelineResultSuccess(name=request.name, path=str(path), result_details="Deleted timeline.")


