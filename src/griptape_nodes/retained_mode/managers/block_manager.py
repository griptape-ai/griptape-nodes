from __future__ import annotations

import json
from typing import Any

from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.block_events import (
    CreateBlockRequest,
    CreateBlockResultFailure,
    CreateBlockResultSuccess,
    DeleteBlockRequest,
    DeleteBlockResultFailure,
    DeleteBlockResultSuccess,
    GetBlockRequest,
    GetBlockResultFailure,
    GetBlockResultSuccess,
    ListBlocksRequest,
    ListBlocksResultFailure,
    ListBlocksResultSuccess,
    WriteBlockRequest,
    WriteBlockResultFailure,
    WriteBlockResultSuccess,
)
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    ReadFileRequest,
    ReadFileResultFailure,
    ReadFileResultSuccess,
    WriteFileRequest,
    WriteFileResultFailure,
)
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.os_manager import OSManager
from griptape_nodes.utils.metaclasses import SingletonMeta


class BlockManager(metaclass=SingletonMeta):
    """Manager for handling blocks inside timeline JSON with auto-persistence."""

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(ListBlocksRequest, self.on_list_blocks_request)
        event_manager.assign_manager_to_request_type(GetBlockRequest, self.on_get_block_request)
        event_manager.assign_manager_to_request_type(WriteBlockRequest, self.on_write_block_request)
        event_manager.assign_manager_to_request_type(CreateBlockRequest, self.on_create_block_request)
        event_manager.assign_manager_to_request_type(DeleteBlockRequest, self.on_delete_block_request)

    def _sanitize_timeline_name(self, name: str) -> str:
        # Keep in sync with TimelineManager
        safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name).strip("._")
        return safe or "untitled"

    def _timeline_path(self, timeline_name: str) -> str:
        from pathlib import Path
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        safe_name = self._sanitize_timeline_name(timeline_name)
        base = GriptapeNodes.ConfigManager().workspace_path
        return str((base / "timelines" / f"{safe_name}.json").resolve())

    def _load_timeline_json(self, path: str) -> dict[str, Any] | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        os_manager = GriptapeNodes.OSManager()
        read_result = os_manager.on_read_file_request(ReadFileRequest(file_path=path))
        if isinstance(read_result, ReadFileResultFailure):
            return None
        assert isinstance(read_result, ReadFileResultSuccess)
        try:
            if isinstance(read_result.content, (bytes, bytearray)):
                text = read_result.content.decode(read_result.encoding or "utf-8")
            else:
                text = read_result.content
            data = json.loads(text)
            return data if isinstance(data, dict) else {"blocks": data}
        except Exception:
            return {"blocks": read_result.content}

    def _save_timeline_json(self, path: str, data: dict[str, Any]) -> str | None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        # Check disk space similar to TimelineManager
        from pathlib import Path

        config_manager = GriptapeNodes.ConfigManager()
        min_space_gb = config_manager.get_config_value("minimum_disk_space_gb_workflows")
        target_dir = Path(path).parent
        if not OSManager.check_available_disk_space(target_dir, min_space_gb):
            return f"Insufficient disk space to save timeline at '{path}'."

        try:
            serialized = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            serialized = json.dumps(str(data), indent=2, ensure_ascii=False)

        os_manager = GriptapeNodes.OSManager()
        write_result = os_manager.on_write_file_request(
            WriteFileRequest(
                file_path=path,
                content=serialized,
                encoding="utf-8",
                append=False,
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
                create_parents=True,
            )
        )
        if isinstance(write_result, WriteFileResultFailure):
            return str(write_result.result_details)
        return None

    def on_list_blocks_request(self, request: ListBlocksRequest) -> ResultPayload:
        path = self._timeline_path(request.timeline_name)
        data = self._load_timeline_json(path)
        if data is None:
            return ListBlocksResultFailure(result_details=f"Timeline '{request.timeline_name}' not found.")

        blocks = data.get("blocks", {})
        # Support both dict and list structures
        if isinstance(blocks, dict):
            block_ids = list(blocks.keys())
        elif isinstance(blocks, list):
            block_ids = [str(i) for i in range(len(blocks))]
        else:
            block_ids = []
        return ListBlocksResultSuccess(timeline_name=request.timeline_name, block_ids=block_ids, result_details="Listed blocks.")

    def on_get_block_request(self, request: GetBlockRequest) -> ResultPayload:
        path = self._timeline_path(request.timeline_name)
        data = self._load_timeline_json(path)
        if data is None:
            return GetBlockResultFailure(result_details=f"Timeline '{request.timeline_name}' not found.")

        blocks = data.get("blocks", {})
        content: Any | None = None
        if isinstance(blocks, dict):
            content = blocks.get(request.block_id)
        elif isinstance(blocks, list):
            try:
                idx = int(request.block_id)
                if 0 <= idx < len(blocks):
                    content = blocks[idx]
            except Exception:
                content = None

        if content is None:
            return GetBlockResultFailure(result_details=f"Block '{request.block_id}' not found in timeline '{request.timeline_name}'.")
        return GetBlockResultSuccess(
            timeline_name=request.timeline_name,
            block_id=request.block_id,
            content=content,
            result_details="Loaded block.",
        )

    def on_write_block_request(self, request: WriteBlockRequest) -> ResultPayload:
        path = self._timeline_path(request.timeline_name)
        data = self._load_timeline_json(path) or {}
        blocks = data.get("blocks")
        if blocks is None:
            # Default to dict keyed by block_id
            blocks = {}
            data["blocks"] = blocks

        if isinstance(blocks, dict):
            blocks[request.block_id] = request.content
        elif isinstance(blocks, list):
            try:
                idx = int(request.block_id)
            except Exception:
                return WriteBlockResultFailure(
                    result_details=f"Timeline '{request.timeline_name}' uses list-based blocks. Block id must be an integer index."
                )
            # Expand list if needed
            if idx < 0:
                return WriteBlockResultFailure(
                    result_details="Negative block indices are not supported for writes."
                )
            if idx >= len(blocks):
                blocks.extend([None] * (idx - len(blocks) + 1))
            blocks[idx] = request.content
        else:
            # Convert unknown structure into dict
            data["blocks"] = {request.block_id: request.content}

        error = self._save_timeline_json(path, data)
        if error is not None:
            return WriteBlockResultFailure(result_details=error)
        return WriteBlockResultSuccess(
            timeline_name=request.timeline_name,
            block_id=request.block_id,
            result_details="Saved block.",
        )

    def on_create_block_request(self, request: CreateBlockRequest) -> ResultPayload:
        path = self._timeline_path(request.timeline_name)
        data = self._load_timeline_json(path) or {"blocks": {}}
        blocks = data.get("blocks")
        if isinstance(blocks, dict):
            if request.block_id in blocks:
                return CreateBlockResultFailure(
                    result_details=f"Block '{request.block_id}' already exists in timeline '{request.timeline_name}'."
                )
            blocks[request.block_id] = request.content
        elif isinstance(blocks, list):
            try:
                idx = int(request.block_id)
            except Exception:
                return CreateBlockResultFailure(
                    result_details=f"Timeline '{request.timeline_name}' uses list-based blocks. Block id must be an integer index."
                )
            if 0 <= idx <= len(blocks):
                blocks.insert(idx, request.content)
            else:
                return CreateBlockResultFailure(result_details="Index out of range for create.")
        else:
            data["blocks"] = {request.block_id: request.content}

        error = self._save_timeline_json(path, data)
        if error is not None:
            return CreateBlockResultFailure(result_details=error)
        return CreateBlockResultSuccess(
            timeline_name=request.timeline_name,
            block_id=request.block_id,
            result_details="Created block.",
        )

    def on_delete_block_request(self, request: DeleteBlockRequest) -> ResultPayload:
        path = self._timeline_path(request.timeline_name)
        data = self._load_timeline_json(path)
        if data is None:
            return DeleteBlockResultFailure(result_details=f"Timeline '{request.timeline_name}' not found.")
        blocks = data.get("blocks")
        if isinstance(blocks, dict):
            if request.block_id not in blocks:
                return DeleteBlockResultFailure(
                    result_details=f"Block '{request.block_id}' not found in timeline '{request.timeline_name}'."
                )
            del blocks[request.block_id]
        elif isinstance(blocks, list):
            try:
                idx = int(request.block_id)
            except Exception:
                return DeleteBlockResultFailure(
                    result_details=f"Timeline '{request.timeline_name}' uses list-based blocks. Block id must be an integer index."
                )
            if 0 <= idx < len(blocks):
                blocks.pop(idx)
            else:
                return DeleteBlockResultFailure(result_details="Index out of range for delete.")
        else:
            return DeleteBlockResultFailure(result_details="Blocks container not found.")

        error = self._save_timeline_json(path, data)
        if error is not None:
            return DeleteBlockResultFailure(result_details=error)
        return DeleteBlockResultSuccess(
            timeline_name=request.timeline_name,
            block_id=request.block_id,
            result_details="Deleted block.",
        )


