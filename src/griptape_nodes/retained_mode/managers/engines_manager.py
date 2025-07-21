"""Manages engine identity and session state.

Consolidates engine identity management and session management into a single
interface. Handles engine ID, name storage, and session lifecycle management.
"""

import importlib.metadata
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from xdg_base_dirs import xdg_data_home, xdg_state_home

from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.app_events import (
    AppEndSessionRequest,
    AppEndSessionResultFailure,
    AppEndSessionResultSuccess,
    AppGetSessionRequest,
    AppGetSessionResultSuccess,
    AppStartSessionRequest,
    AppStartSessionResultSuccess,
    EngineHeartbeatRequest,
    EngineHeartbeatResultFailure,
    EngineHeartbeatResultSuccess,
    GetEngineNameRequest,
    GetEngineNameResultFailure,
    GetEngineNameResultSuccess,
    GetEngineVersionRequest,
    GetEngineVersionResultFailure,
    GetEngineVersionResultSuccess,
    SessionHeartbeatRequest,
    SessionHeartbeatResultFailure,
    SessionHeartbeatResultSuccess,
    SetEngineNameRequest,
    SetEngineNameResultFailure,
    SetEngineNameResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import BaseEvent, ResultPayload
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.utils.name_generator import generate_engine_name

logger = logging.getLogger("griptape_nodes")

engine_version = importlib.metadata.version("griptape_nodes")


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def from_string(cls, version_string: str) -> "Version | None":
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_string)
        if match:
            major, minor, patch = map(int, match.groups())
            return cls(major, minor, patch)
        return None

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "Version") -> bool:
        """Less than comparison."""
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: "Version") -> bool:
        """Less than or equal comparison."""
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: "Version") -> bool:
        """Greater than comparison."""
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: "Version") -> bool:
        """Greater than or equal comparison."""
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)

    def __eq__(self, other: "Version") -> bool:  # type: ignore[override]
        """Equality comparison."""
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __hash__(self) -> int:
        """Hash function for Version."""
        return hash((self.major, self.minor, self.patch))


class SessionData(BaseModel):
    """Represents a session with its metadata."""

    session_id: str
    engine_id: str
    started_at: datetime
    last_updated: datetime


class EngineData(BaseModel):
    """Represents an engine with its metadata."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime | None = None


class EnginesData(BaseModel):
    """Container for all engine data."""

    engines: list[EngineData] = []
    default_engine_id: str | None = None


class SessionsData(BaseModel):
    """Container for all session data."""

    sessions: list[SessionData] = []


class EnginesManager:
    """Manages engine identity and session state."""

    _active_engine_id: str | None = None
    _active_session_id: str | None = None

    _ENGINE_DATA_FILE = "engines.json"
    _SESSION_DATA_FILE = "sessions.json"

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the EnginesManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        BaseEvent._session_id = self._active_session_id
        if event_manager is not None:
            event_manager.assign_manager_to_request_type(GetEngineVersionRequest, self.handle_engine_version_request)
            event_manager.assign_manager_to_request_type(AppStartSessionRequest, self.handle_session_start_request)
            event_manager.assign_manager_to_request_type(AppEndSessionRequest, self.handle_session_end_request)
            event_manager.assign_manager_to_request_type(AppGetSessionRequest, self.handle_get_session_request)
            event_manager.assign_manager_to_request_type(SessionHeartbeatRequest, self.handle_session_heartbeat_request)
            event_manager.assign_manager_to_request_type(EngineHeartbeatRequest, self.handle_engine_heartbeat_request)
            event_manager.assign_manager_to_request_type(GetEngineNameRequest, self.handle_get_engine_name_request)
            event_manager.assign_manager_to_request_type(SetEngineNameRequest, self.handle_set_engine_name_request)

    @classmethod
    def _get_engine_data_dir(cls) -> Path:
        """Get the XDG data directory for engine storage."""
        return xdg_data_home() / "griptape_nodes"

    @classmethod
    def _get_session_data_dir(cls) -> Path:
        """Get the XDG state directory for session storage."""
        return xdg_state_home() / "griptape_nodes"

    @classmethod
    def _get_engine_data_file(cls) -> Path:
        """Get the path to the engine data storage file."""
        return cls._get_engine_data_dir() / cls._ENGINE_DATA_FILE

    @classmethod
    def _get_session_data_file(cls) -> Path:
        """Get the path to the session data storage file."""
        return cls._get_session_data_dir() / cls._SESSION_DATA_FILE

    @classmethod
    def _load_engines_data(cls) -> EnginesData:
        """Load engines data from storage.

        Returns:
            EnginesData: The engines data structure
        """
        engine_data_file = cls._get_engine_data_file()

        if engine_data_file.exists():
            try:
                with engine_data_file.open("r") as f:
                    data = json.load(f)
                    return EnginesData.model_validate(data)
            except (json.JSONDecodeError, OSError, ValueError):
                logger.warning("Failed to load engines data, using defaults")

        return EnginesData()

    @classmethod
    def _save_engines_data(cls, engines_data: EnginesData) -> None:
        """Save engines data to storage.

        Args:
            engines_data: Engines data structure to save
        """
        engine_data_dir = cls._get_engine_data_dir()
        engine_data_dir.mkdir(parents=True, exist_ok=True)

        engine_data_file = cls._get_engine_data_file()
        with engine_data_file.open("w") as f:
            json.dump(engines_data.model_dump(), f, indent=2, default=str)

    @classmethod
    def _load_sessions_data(cls) -> SessionsData:
        """Load sessions data from storage.

        Returns:
            SessionsData: The sessions data structure
        """
        session_data_file = cls._get_session_data_file()

        if session_data_file.exists():
            try:
                with session_data_file.open("r") as f:
                    data = json.load(f)
                    return SessionsData.model_validate(data)
            except (json.JSONDecodeError, OSError, ValueError):
                logger.warning("Failed to load sessions data, using defaults")

        return SessionsData()

    @classmethod
    def _save_sessions_data(cls, sessions_data: SessionsData) -> None:
        """Save sessions data to storage.

        Args:
            sessions_data: Sessions data structure to save
        """
        session_data_dir = cls._get_session_data_dir()
        session_data_dir.mkdir(parents=True, exist_ok=True)

        session_data_file = cls._get_session_data_file()
        with session_data_file.open("w") as f:
            json.dump(sessions_data.model_dump(), f, indent=2, default=str)

    @classmethod
    def _get_selected_engine_id(cls) -> str | None:
        """Get the selected engine ID from environment variable.

        Returns:
            str | None: The selected engine ID or None if not specified
        """
        return os.getenv("GTN_ENGINE_ID")

    @classmethod
    def _find_engine_by_id(cls, engines_data: EnginesData, engine_id: str) -> EngineData | None:
        """Find an engine by ID in the engines data.

        Args:
            engines_data: The engines data structure
            engine_id: The engine ID to find

        Returns:
            EngineData | None: The engine data if found, None otherwise
        """
        for engine in engines_data.engines:
            if engine.id == engine_id:
                return engine
        return None

    @classmethod
    def _find_session_by_id(cls, sessions_data: SessionsData, session_id: str) -> SessionData | None:
        """Find a session by ID in the sessions data.

        Args:
            sessions_data: The sessions data structure
            session_id: The session ID to find

        Returns:
            SessionData | None: The session data if found, None otherwise
        """
        for session in sessions_data.sessions:
            if session.session_id == session_id:
                return session
        return None

    @classmethod
    def _add_or_update_engine(cls, engine_data: EngineData) -> None:
        """Add or update an engine in the engines data structure.

        Args:
            engine_data: The engine data to add or update
        """
        engines_data = cls._load_engines_data()

        # Find existing engine
        existing_engine = cls._find_engine_by_id(engines_data, engine_data.id)

        if existing_engine:
            # Update existing engine
            existing_engine.name = engine_data.name
            existing_engine.updated_at = datetime.now(tz=UTC)
        else:
            # Add new engine
            engines_data.engines.append(engine_data)

            # Set as default if it's the first engine
            if not engines_data.default_engine_id and len(engines_data.engines) == 1:
                engines_data.default_engine_id = engine_data.id

        cls._save_engines_data(engines_data)

    @classmethod
    def _add_or_update_session(cls, session_data: SessionData) -> None:
        """Add or update a session in the sessions data structure.

        Args:
            session_data: The session data to add or update
        """
        sessions_data = cls._load_sessions_data()

        # Find existing session
        existing_session = cls._find_session_by_id(sessions_data, session_data.session_id)

        if existing_session:
            # Update existing session
            existing_session.last_updated = datetime.now(tz=UTC)
        else:
            # Add new session
            sessions_data.sessions.append(session_data)

        cls._save_sessions_data(sessions_data)

    @classmethod
    def _get_engine_data(cls) -> EngineData:
        """Get the current engine data, creating default if it doesn't exist.

        Returns:
            EngineData: The current engine data
        """
        engines_data = cls._load_engines_data()

        # Determine which engine to use
        selected_engine_id = cls._get_selected_engine_id()

        if selected_engine_id:
            # Use specified engine ID
            engine_data = cls._find_engine_by_id(engines_data, selected_engine_id)
            if engine_data:
                return engine_data
            # If specified engine not found, create it
            engine_data = EngineData(
                id=selected_engine_id,
                name=generate_engine_name(),
                created_at=datetime.now(tz=UTC),
            )
        else:
            # Use default engine (first one) or create new one
            if engines_data.engines:
                default_id = engines_data.default_engine_id
                if default_id:
                    engine_data = cls._find_engine_by_id(engines_data, default_id)
                    if engine_data:
                        return engine_data
                # Fall back to first engine
                return engines_data.engines[0]

            # Create new engine
            engine_data = EngineData(
                id=str(uuid.uuid4()),
                name=generate_engine_name(),
                created_at=datetime.now(tz=UTC),
            )

        # Add or update engine in the data structure
        cls._add_or_update_engine(engine_data)
        return engine_data

    @classmethod
    def get_active_engine_id(cls) -> str | None:
        """Get the active engine ID.

        Returns:
            str | None: The active engine ID or None if not set
        """
        return cls._active_engine_id

    @classmethod
    def initialize_engine_id(cls) -> str:
        """Initialize the engine ID if not already set."""
        if cls._active_engine_id is None:
            engine_data = cls._get_engine_data()
            engine_id = engine_data.id
            BaseEvent._engine_id = engine_id
            cls._active_engine_id = engine_id
            logger.debug("Initialized engine ID: %s", engine_id)

        return cls._active_engine_id

    @classmethod
    def get_engine_name(cls) -> str:
        """Get the engine name.

        Returns:
            str: The engine name
        """
        engine_data = cls._get_engine_data()
        return engine_data.name

    @classmethod
    def set_engine_name(cls, engine_name: str) -> None:
        """Set and persist the current engine name.

        Args:
            engine_name: The new engine name to set
        """
        # Get current engine data
        engine_data = cls._get_engine_data()

        # Update the name
        engine_data.name = engine_name
        engine_data.updated_at = datetime.now(tz=UTC)

        # Save updated engine data
        cls._add_or_update_engine(engine_data)

    @classmethod
    def get_active_session_id(cls) -> str | None:
        """Get the active session ID.

        Returns:
            str | None: The active session ID or None if not set
        """
        return cls._active_session_id

    @classmethod
    def start_session(cls, session_id: str) -> None:
        """Start a new session and make it the active session.

        Args:
            session_id: The session ID to start
        """
        engine_id = cls.get_active_engine_id()
        if engine_id is None:
            # Initialize engine if needed
            engine_id = cls.initialize_engine_id()

        session_data = SessionData(
            session_id=session_id,
            engine_id=engine_id,
            started_at=datetime.now(tz=UTC),
            last_updated=datetime.now(tz=UTC),
        )

        # Add or update the session
        cls._add_or_update_session(session_data)

        # Set as active session
        cls._active_session_id = session_id
        BaseEvent._session_id = session_id
        logger.info("Started and activated session: %s for engine: %s", session_id, engine_id)

    @classmethod
    def get_saved_session_id(cls) -> str | None:
        """Get the active session ID if it exists.

        Returns:
            str | None: The active session ID or None if no active session
        """
        # Return active session if set
        if cls._active_session_id:
            return cls._active_session_id

        # Fall back to first session for current engine if available
        engine_id = cls.get_active_engine_id()
        if engine_id:
            sessions_data = cls._load_sessions_data()
            for session in sessions_data.sessions:
                if session.engine_id == engine_id:
                    first_session_id = session.session_id
                    # Set as active for future calls
                    BaseEvent._session_id = first_session_id
                    cls._active_session_id = first_session_id
                    logger.debug(
                        "Retrieved first saved session as active: %s for engine: %s", first_session_id, engine_id
                    )
                    return first_session_id

        return None

    @classmethod
    def end_session(cls) -> str | None:
        """End the active session and return the session ID that was ended.

        Returns:
            str | None: The session ID that was ended, or None if no active session
        """
        previous_session_id = cls._active_session_id

        # Clear active session
        cls._active_session_id = None
        BaseEvent._session_id = None

        # Clear all sessions
        sessions_data = SessionsData()
        cls._save_sessions_data(sessions_data)

        if previous_session_id:
            logger.info("Ended session: %s", previous_session_id)
        else:
            logger.info("No active session to end")

        return previous_session_id

    @classmethod
    def handle_session_start_request(cls, request: AppStartSessionRequest) -> ResultPayload:  # noqa: ARG003
        """Handle session start requests.

        Args:
            request: The session start request

        Returns:
            ResultPayload: Success result with session ID
        """
        current_session_id = cls.get_active_session_id()
        if current_session_id is None:
            # Client wants a new session
            current_session_id = uuid.uuid4().hex
            cls.start_session(current_session_id)
            details = f"New session '{current_session_id}' started at {datetime.now(tz=UTC)}."
            logger.info(details)
        else:
            details = f"Session '{current_session_id}' already active. Joining..."
            logger.info(details)

        return AppStartSessionResultSuccess(current_session_id)

    @classmethod
    def handle_session_end_request(cls, _: AppEndSessionRequest) -> ResultPayload:
        """Handle session end requests.

        Args:
            _: The session end request (unused)

        Returns:
            ResultPayload: Success or failure result
        """
        try:
            previous_session_id = cls.end_session()

            if previous_session_id is None:
                details = "No active session to end."
                logger.info(details)
            else:
                details = f"Session '{previous_session_id}' ended at {datetime.now(tz=UTC)}."
                logger.info(details)

            return AppEndSessionResultSuccess(session_id=previous_session_id)
        except Exception as err:
            details = f"Failed to end session due to '{err}'."
            logger.error(details)
            return AppEndSessionResultFailure()

    @classmethod
    def handle_get_session_request(cls, _: AppGetSessionRequest) -> ResultPayload:
        """Handle get session requests.

        Args:
            _: The get session request (unused)

        Returns:
            ResultPayload: Success result with current session ID
        """
        return AppGetSessionResultSuccess(session_id=cls.get_active_session_id())

    @classmethod
    def handle_engine_version_request(cls, request: GetEngineVersionRequest) -> ResultPayload:  # noqa: ARG003
        """Handle engine version requests.

        Args:
            request: The engine version request (unused)

        Returns:
            ResultPayload: Success result with version info or failure result
        """
        try:
            engine_ver = Version.from_string(engine_version)
            if engine_ver:
                return GetEngineVersionResultSuccess(
                    major=engine_ver.major,
                    minor=engine_ver.minor,
                    patch=engine_ver.patch,
                )
            details = f"Attempted to get engine version. Failed because version string '{engine_ver}' wasn't in expected major.minor.patch format."
            logger.error(details)
            return GetEngineVersionResultFailure()
        except Exception as err:
            details = f"Attempted to get engine version. Failed due to '{err}'."
            logger.error(details)
            return GetEngineVersionResultFailure()

    @classmethod
    def handle_session_heartbeat_request(cls, request: SessionHeartbeatRequest) -> ResultPayload:  # noqa: ARG003
        """Handle session heartbeat requests.

        Simply verifies that the session is active and responds with success.

        Args:
            request: The session heartbeat request (unused)

        Returns:
            ResultPayload: Success or failure result
        """
        try:
            active_session_id = cls.get_active_session_id()
            if active_session_id is None:
                logger.warning("Session heartbeat received but no active session found")
                return SessionHeartbeatResultFailure()

            logger.debug("Session heartbeat successful for session: %s", active_session_id)
            return SessionHeartbeatResultSuccess()
        except Exception as err:
            logger.error("Failed to handle session heartbeat: %s", err)
            return SessionHeartbeatResultFailure()

    @classmethod
    def handle_get_engine_name_request(cls, request: GetEngineNameRequest) -> ResultPayload:  # noqa: ARG003
        """Handle requests to get the current engine name.

        Args:
            request: The get engine name request (unused)

        Returns:
            ResultPayload: Success result with engine name or failure result
        """
        try:
            engine_name = cls.get_engine_name()
            logger.debug("Retrieved engine name: %s", engine_name)
            return GetEngineNameResultSuccess(engine_name=engine_name)
        except Exception as err:
            error_message = f"Failed to get engine name: {err}"
            logger.error(error_message)
            return GetEngineNameResultFailure(error_message=error_message)

    @classmethod
    def handle_set_engine_name_request(cls, request: SetEngineNameRequest) -> ResultPayload:
        """Handle requests to set a new engine name.

        Args:
            request: The set engine name request

        Returns:
            ResultPayload: Success result with new engine name or failure result
        """
        try:
            # Validate engine name (basic validation)
            if not request.engine_name or not request.engine_name.strip():
                error_message = "Engine name cannot be empty"
                logger.warning(error_message)
                return SetEngineNameResultFailure(error_message=error_message)

            # Set the new engine name
            cls.set_engine_name(request.engine_name.strip())
            logger.info("Engine name set to: %s", request.engine_name.strip())
            return SetEngineNameResultSuccess(engine_name=request.engine_name.strip())

        except Exception as err:
            error_message = f"Failed to set engine name: {err}"
            logger.error(error_message)
            return SetEngineNameResultFailure(error_message=error_message)

    @classmethod
    def handle_engine_heartbeat_request(cls, request: EngineHeartbeatRequest) -> ResultPayload:
        """Handle engine heartbeat requests.

        Returns engine status information including version, session state, and system metrics.

        Args:
            request: The engine heartbeat request

        Returns:
            ResultPayload: Success result with engine status or failure result
        """
        try:
            # Get instance information based on environment variables
            instance_info = cls._get_instance_info()

            # Get current workflow information
            workflow_info = cls._get_current_workflow_info()

            # Get engine name
            engine_name = cls.get_engine_name()

            logger.debug("Engine heartbeat successful")
            return EngineHeartbeatResultSuccess(
                heartbeat_id=request.heartbeat_id,
                engine_version=engine_version,
                engine_name=engine_name,
                engine_id=cls.get_active_engine_id(),
                session_id=cls.get_active_session_id(),
                timestamp=datetime.now(tz=UTC).isoformat(),
                **instance_info,
                **workflow_info,
            )
        except Exception as err:
            logger.error("Failed to handle engine heartbeat: %s", err)
            return EngineHeartbeatResultFailure(heartbeat_id=request.heartbeat_id)

    @classmethod
    def _get_instance_info(cls) -> dict[str, str | None]:
        """Get instance information from environment variables.

        Returns instance type, region, provider, and public IP information if available.
        """
        instance_info: dict[str, str | None] = {
            "instance_type": os.getenv("GTN_INSTANCE_TYPE"),
            "instance_region": os.getenv("GTN_INSTANCE_REGION"),
            "instance_provider": os.getenv("GTN_INSTANCE_PROVIDER"),
        }

        # Determine deployment type based on presence of instance environment variables
        instance_info["deployment_type"] = "griptape_hosted" if any(instance_info.values()) else "local"

        # Get public IP address
        public_ip = cls._get_public_ip()
        if public_ip:
            instance_info["public_ip"] = public_ip

        return instance_info

    @classmethod
    def _get_public_ip(cls) -> str | None:
        """Get the public IP address of this device.

        Returns the public IP address if available, None otherwise.
        """
        try:
            # Try multiple services in case one is down
            services = [
                "https://api.ipify.org",
                "https://ipinfo.io/ip",
                "https://icanhazip.com",
            ]

            for service in services:
                try:
                    with httpx.Client(timeout=5.0) as client:
                        response = client.get(service)
                        response.raise_for_status()
                        public_ip = response.text.strip()
                        if public_ip:
                            logger.debug("Retrieved public IP from %s: %s", service, public_ip)
                            return public_ip
                except Exception as err:
                    logger.debug("Failed to get public IP from %s: %s", service, err)
                    continue
            logger.warning("Unable to retrieve public IP from any service")
        except Exception as err:
            logger.warning("Failed to get public IP: %s", err)
            return None
        else:
            return None

    @classmethod
    def _get_current_workflow_info(cls) -> dict[str, Any]:
        """Get information about the currently loaded workflow.

        Returns workflow name, file path, and status information if available.
        """
        workflow_info = {
            "current_workflow": None,
            "workflow_file_path": None,
            "has_active_flow": False,
        }

        try:
            # Import here to avoid circular import
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

            context_manager = GriptapeNodes.ContextManager()

            # Check if there's an active workflow
            if context_manager.has_current_workflow():
                workflow_name = context_manager.get_current_workflow_name()
                workflow_info["current_workflow"] = workflow_name
                workflow_info["has_active_flow"] = context_manager.has_current_flow()

                # Get workflow file path from registry
                if WorkflowRegistry.has_workflow_with_name(workflow_name):
                    workflow = WorkflowRegistry.get_workflow_by_name(workflow_name)
                    absolute_path = WorkflowRegistry.get_complete_file_path(workflow.file_path)
                    workflow_info["workflow_file_path"] = absolute_path

        except Exception as err:
            logger.warning("Failed to get current workflow info: %s", err)

        return workflow_info
