from __future__ import annotations

import logging
from typing import Any

from griptape_nodes.exe_types.draw_types import BaseDraw
from griptape_nodes.retained_mode.events.base_events import ResultPayload
from griptape_nodes.retained_mode.events.draw_events import (
    CreateDrawRequest,
    CreateDrawResultFailure,
    CreateDrawResultSuccess,
    DeleteDrawRequest,
    DeleteDrawResultFailure,
    DeleteDrawResultSuccess,
    GetDrawMetadataRequest,
    GetDrawMetadataResultFailure,
    GetDrawMetadataResultSuccess,
    ListDrawsRequest,
    ListDrawsResultFailure,
    ListDrawsResultSuccess,
    SetDrawMetadataRequest,
    SetDrawMetadataResultFailure,
    SetDrawMetadataResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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

    def on_create_draw_request(self, request: CreateDrawRequest) -> ResultPayload:
        try:
            # Generate or validate name
            requested_name = request.requested_name
            name = GriptapeNodes.ObjectManager().generate_name_for_object(
                type_name="Draw", requested_name=requested_name
            )
            draw = BaseDraw(
                name=name,
                metadata=request.metadata,
                x=request.x,
                y=request.y,
                width=request.width,
                height=request.height,
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


