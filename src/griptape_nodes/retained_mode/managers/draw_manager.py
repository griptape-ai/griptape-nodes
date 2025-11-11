from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from griptape_nodes.exe_types.draw_types import BaseDraw
from griptape_nodes.retained_mode.events.draw_events import (
    CreateDrawRequest,
    CreateDrawResultFailure,
    CreateDrawResultSuccess,
    DeserializeDrawFromCommandsRequest,
    DeserializeDrawFromCommandsResultFailure,
    DeserializeDrawFromCommandsResultSuccess,
    DeleteDrawRequest,
    DeleteDrawResultFailure,
    DeleteDrawResultSuccess,
    GetDrawMetadataRequest,
    GetDrawMetadataResultFailure,
    GetDrawMetadataResultSuccess,
    ListDrawsRequest,
    ListDrawsResultFailure,
    ListDrawsResultSuccess,
    SerializeDrawToCommandsRequest,
    SerializeDrawToCommandsResultFailure,
    SerializeDrawToCommandsResultSuccess,
    SerializedDrawCommands,
    SetDrawMetadataRequest,
    SetDrawMetadataResultFailure,
    SetDrawMetadataResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class DrawManager:
    """Minimal draw object manager that stores BaseDraw in the ObjectManager."""

    def __init__(self, event_manager: EventManager) -> None:
        event_manager.assign_manager_to_request_type(CreateDrawRequest, self.on_create_draw_request)
        event_manager.assign_manager_to_request_type(DeleteDrawRequest, self.on_delete_draw_request)
        event_manager.assign_manager_to_request_type(GetDrawMetadataRequest, self.on_get_draw_metadata_request)
        event_manager.assign_manager_to_request_type(SetDrawMetadataRequest, self.on_set_draw_metadata_request)
        event_manager.assign_manager_to_request_type(ListDrawsRequest, self.on_list_draws_request)
        event_manager.assign_manager_to_request_type(
            SerializeDrawToCommandsRequest, self.on_serialize_draw_to_commands_request
        )
        event_manager.assign_manager_to_request_type(
            DeserializeDrawFromCommandsRequest, self.on_deserialize_draw_from_commands_request
        )

    def on_create_draw_request(self, request: CreateDrawRequest) -> ResultPayload:
        try:
            # Generate or validate name
            requested_name = request.requested_name
            name = GriptapeNodes.ObjectManager().generate_name_for_object(
                type_name="Draw", requested_name=requested_name
            )
            # Merge provided position/size convenience fields into metadata
            merged_metadata: dict[str, Any] = {}
            if request.metadata:
                merged_metadata.update(request.metadata)
            if request.x is not None:
                merged_metadata["x"] = request.x
            if request.y is not None:
                merged_metadata["y"] = request.y
            if request.width is not None:
                merged_metadata["width"] = request.width
            if request.height is not None:
                merged_metadata["height"] = request.height
            draw = BaseDraw(
                name=name,
                metadata=merged_metadata,
            )
            GriptapeNodes.ObjectManager().add_object_by_name(name, draw)
            return CreateDrawResultSuccess(draw_name=name, result_details="Draw created successfully.")
        except Exception as e:
            logger.error("Failed to create draw: %s", e)
            return CreateDrawResultFailure(result_details=f"Failed to create draw: {e}")

    def on_delete_draw_request(self, request: DeleteDrawRequest) -> ResultPayload:
        try:
            obj = GriptapeNodes.ObjectManager().attempt_get_object_by_name(request.draw_name)
            if obj is None or not isinstance(obj, BaseDraw):
                return DeleteDrawResultFailure(result_details=f"Draw '{request.draw_name}' not found.")
            GriptapeNodes.ObjectManager().del_obj_by_name(request.draw_name)
            return DeleteDrawResultSuccess(result_details="Draw deleted successfully.")
        except Exception as e:
            logger.error("Failed to delete draw '%s': %s", request.draw_name, e)
            return DeleteDrawResultFailure(result_details=f"Failed to delete draw: {e}")

    def on_get_draw_metadata_request(self, request: GetDrawMetadataRequest) -> ResultPayload:
        try:
            draw = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(request.draw_name, BaseDraw)
            if draw is None:
                return GetDrawMetadataResultFailure(result_details=f"Draw '{request.draw_name}' not found.")
            return GetDrawMetadataResultSuccess(metadata=dict(draw.metadata), result_details="Success")
        except Exception as e:
            logger.error("Failed to get draw metadata '%s': %s", request.draw_name, e)
            return GetDrawMetadataResultFailure(result_details=f"Failed to get draw metadata: {e}")

    def on_set_draw_metadata_request(self, request: SetDrawMetadataRequest) -> ResultPayload:
        try:
            draw = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(request.draw_name, BaseDraw)
            if draw is None:
                return SetDrawMetadataResultFailure(result_details=f"Draw '{request.draw_name}' not found.")
            # Merge metadata
            for k, v in request.metadata.items():
                draw.metadata[k] = v
            return SetDrawMetadataResultSuccess(result_details="Draw metadata updated.")
        except Exception as e:
            logger.error("Failed to set draw metadata '%s': %s", request.draw_name, e)
            return SetDrawMetadataResultFailure(result_details=f"Failed to set draw metadata: {e}")

    def on_list_draws_request(self, request: ListDrawsRequest) -> ResultPayload:  # noqa: ARG002
        try:
            subset: dict[str, Any] = GriptapeNodes.ObjectManager().get_filtered_subset(type=BaseDraw)
            return ListDrawsResultSuccess(draw_names=list(subset.keys()), result_details="Success")
        except Exception as e:
            logger.error("Failed to list draws: %s", e)
            return ListDrawsResultFailure(result_details=f"Failed to list draws: {e}")

    def on_serialize_draw_to_commands_request(self, request: SerializeDrawToCommandsRequest) -> ResultPayload:
        try:
            draw = GriptapeNodes.ObjectManager().attempt_get_object_by_name_as_type(request.draw_name, BaseDraw)
            if draw is None:
                return SerializeDrawToCommandsResultFailure(
                    result_details=f"Draw '{request.draw_name}' not found."
                )
            create_cmd = CreateDrawRequest(
                requested_name=draw.name,
                metadata=dict(draw.metadata),
            )
            serialized = SerializedDrawCommands(create_draw_command=create_cmd, modification_commands=[])
            return SerializeDrawToCommandsResultSuccess(
                serialized_draw_commands=serialized, result_details="Serialized draw successfully."
            )
        except Exception as e:
            logger.error("Failed to serialize draw '%s': %s", request.draw_name, e)
            return SerializeDrawToCommandsResultFailure(result_details=f"Failed to serialize draw: {e}")

    def on_deserialize_draw_from_commands_request(
        self, request: DeserializeDrawFromCommandsRequest
    ) -> ResultPayload:
        try:
            commands = request.serialized_draw_commands
            # Issue create
            create_cmd = commands.create_draw_command
            create_result = GriptapeNodes.handle_request(create_cmd)
            if not isinstance(create_result, CreateDrawResultSuccess):
                return DeserializeDrawFromCommandsResultFailure(
                    result_details=f"Failed to create draw during deserialize: {create_result.result_details}"
                )
            new_name = create_result.draw_name
            # Apply any modifications (none by default)
            for cmd in commands.modification_commands:
                GriptapeNodes.handle_request(cmd)
            return DeserializeDrawFromCommandsResultSuccess(
                draw_name=new_name, result_details="Deserialized draw successfully."
            )
        except Exception as e:
            logger.error("Failed to deserialize draw: %s", e)
            return DeserializeDrawFromCommandsResultFailure(result_details=f"Failed to deserialize draw: {e}")
