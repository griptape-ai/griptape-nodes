from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.executor import Executor
from griptape_nodes.retained_mode.events.base_events import (
    ResultPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.managers.base_manager import BaseManager

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class ExecuteMethodRequest:
    """Request to execute a method through the Executor."""

    def __init__(self, method_name: str, args: list[Any] | None = None, kwargs: dict[str, Any] | None = None):
        self.method_name = method_name
        self.args = args or []
        self.kwargs = kwargs or {}


class ExecuteMethodResultSuccess(ResultPayloadSuccess):
    """Successful method execution result."""

    def __init__(self, result: Any, method_name: str, result_details: str):
        super().__init__(result_details=result_details)
        self.result = result
        self.method_name = method_name


class ExecuteMethodResultFailure(ResultPayloadFailure):
    """Failed method execution result."""

    def __init__(self, method_name: str, error: str, result_details: str):
        super().__init__(result_details=result_details)
        self.method_name = method_name
        self.error = error


class ListMethodsRequest:
    """Request to list available executor methods."""

    def __init__(self, library_name: str | None = None):
        self.library_name = library_name


class ListMethodsResultSuccess(ResultPayloadSuccess):
    """Successful method listing result."""

    def __init__(self, methods: list[dict[str, Any]], result_details: str):
        super().__init__(result_details=result_details)
        self.methods = methods


class GetMethodInfoRequest:
    """Request to get information about a specific method."""

    def __init__(self, method_name: str):
        self.method_name = method_name


class GetMethodInfoResultSuccess(ResultPayloadSuccess):
    """Successful method info result."""

    def __init__(self, method_info: dict[str, Any], result_details: str):
        super().__init__(result_details=result_details)
        self.method_info = method_info


class GetMethodInfoResultFailure(ResultPayloadFailure):
    """Failed method info result."""

    def __init__(self, method_name: str, error: str, result_details: str):
        super().__init__(result_details=result_details)
        self.method_name = method_name
        self.error = error


class RefreshMethodsRequest:
    """Request to refresh all executor methods from libraries."""


class RefreshMethodsResultSuccess(ResultPayloadSuccess):
    """Successful method refresh result."""

    def __init__(self, methods_count: int, result_details: str):
        super().__init__(result_details=result_details)
        self.methods_count = methods_count


class ExecutorManager(BaseManager):
    """Manager for the Executor functionality.

    Provides event-driven access to the Executor class methods,
    allowing for execution of library-provided methods through
    the event system.
    """

    def __init__(self, event_manager: EventManager):
        super().__init__(event_manager)
        self._executor = Executor()

        # Register event handlers
        event_manager.assign_manager_to_request_type(ExecuteMethodRequest, self.on_execute_method_request)
        event_manager.assign_manager_to_request_type(ListMethodsRequest, self.on_list_methods_request)
        event_manager.assign_manager_to_request_type(GetMethodInfoRequest, self.on_get_method_info_request)
        event_manager.assign_manager_to_request_type(RefreshMethodsRequest, self.on_refresh_methods_request)

        # Initialize methods from registered libraries
        self._executor.refresh_methods()

    def on_execute_method_request(self, request: ExecuteMethodRequest) -> ResultPayload:
        """Handle method execution requests."""
        method_name = request.method_name

        try:
            if not self._executor.has_method(method_name):
                available_methods = [m.name for m in self._executor.list_methods()]
                error = f"Method '{method_name}' not found. Available methods: {available_methods}"
                return ExecuteMethodResultFailure(
                    method_name=method_name,
                    error=error,
                    result_details=f"Failed to execute method '{method_name}': {error}",
                )

            # Execute the method
            result = self._executor.execute(method_name, *request.args, **request.kwargs)

            return ExecuteMethodResultSuccess(
                result=result, method_name=method_name, result_details=f"Successfully executed method '{method_name}'"
            )

        except Exception as e:
            error = str(e)
            logger.error("Error executing method '%s': %s", method_name, e)
            return ExecuteMethodResultFailure(
                method_name=method_name,
                error=error,
                result_details=f"Failed to execute method '{method_name}': {error}",
            )

    def on_list_methods_request(self, request: ListMethodsRequest) -> ResultPayload:
        """Handle method listing requests."""
        try:
            methods = self._executor.list_methods(request.library_name)

            # Convert ExecutorMethod objects to dictionaries for serialization
            method_data = [
                {
                    "name": method.name,
                    "library_name": method.library_name,
                    "source_type": method.source_type,
                    "description": method.description,
                    "signature": str(method.signature),
                }
                for method in methods
            ]

            filter_text = f" from library '{request.library_name}'" if request.library_name else ""
            details = f"Found {len(method_data)} methods{filter_text}"

            return ListMethodsResultSuccess(methods=method_data, result_details=details)

        except Exception as e:
            error = str(e)
            logger.error("Error listing methods: %s", e)
            return ResultPayloadFailure(result_details=f"Failed to list methods: {error}")

    def on_get_method_info_request(self, request: GetMethodInfoRequest) -> ResultPayload:
        """Handle method info requests."""
        method_name = request.method_name

        try:
            method_info = self._executor.get_method_info(method_name)

            if not method_info:
                available_methods = [m.name for m in self._executor.list_methods()]
                error = f"Method '{method_name}' not found. Available methods: {available_methods}"
                return GetMethodInfoResultFailure(
                    method_name=method_name,
                    error=error,
                    result_details=f"Failed to get info for method '{method_name}': {error}",
                )

            method_data = {
                "name": method_info.name,
                "library_name": method_info.library_name,
                "source_type": method_info.source_type,
                "description": method_info.description,
                "signature": str(method_info.signature),
            }

            return GetMethodInfoResultSuccess(
                method_info=method_data, result_details=f"Retrieved info for method '{method_name}'"
            )

        except Exception as e:
            error = str(e)
            logger.error("Error getting method info for '%s': %s", method_name, e)
            return GetMethodInfoResultFailure(
                method_name=method_name,
                error=error,
                result_details=f"Failed to get info for method '{method_name}': {error}",
            )

    def on_refresh_methods_request(self, request: RefreshMethodsRequest) -> ResultPayload:  # noqa: ARG002
        """Handle method refresh requests."""
        try:
            self._executor.refresh_methods()
            methods_count = len(self._executor.list_methods())

            return RefreshMethodsResultSuccess(
                methods_count=methods_count,
                result_details=f"Refreshed {methods_count} methods from registered libraries",
            )

        except Exception as e:
            error = str(e)
            logger.error("Error refreshing methods: %s", e)
            return ResultPayloadFailure(result_details=f"Failed to refresh methods: {error}")

    def get_executor(self) -> Executor:
        """Get the underlying Executor instance."""
        return self._executor
