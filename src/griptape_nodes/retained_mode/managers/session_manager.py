"""Manages session state and saving using XDG state directory.

Handles storing and retrieving multiple session information across engine restarts.
Sessions are tied to specific engines, with each engine maintaining its own session store.
Supports multiple concurrent sessions per engine with one active session managed through BaseEvent.
Storage structure: ~/.local/state/griptape_nodes/engines/{engine_id}/sessions.json
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from xdg_base_dirs import xdg_state_home

from griptape_nodes.retained_mode.events.base_events import BaseEvent
from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class SessionManager:
    """Manages session saving and active session state."""

    _active_session_id: str | None = None

    _SESSION_STATE_FILE = "sessions.json"

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the SessionManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        BaseEvent._session_id = self._active_session_id
        if event_manager is not None:
            # Register event handlers here when session events are defined
            pass

    @classmethod
    def _get_session_state_dir(cls, engine_id: str | None = None) -> Path:
        """Get the XDG state directory for session storage.

        Args:
            engine_id: Optional engine ID to create engine-specific directory
        """
        base_dir = xdg_state_home() / "griptape_nodes"
        if engine_id:
            return base_dir / "engines" / engine_id
        return base_dir

    @classmethod
    def _get_session_state_file(cls, engine_id: str | None = None) -> Path:
        """Get the path to the session state storage file.

        Args:
            engine_id: Optional engine ID to get engine-specific session file
        """
        return cls._get_session_state_dir(engine_id) / cls._SESSION_STATE_FILE

    @classmethod
    def _load_sessions_data(cls, engine_id: str | None = None) -> dict:
        """Load sessions data from storage.

        Args:
            engine_id: Optional engine ID to load engine-specific sessions

        Returns:
            dict: Sessions data structure with sessions array
        """
        session_state_file = cls._get_session_state_file(engine_id)

        if session_state_file.exists():
            try:
                with session_state_file.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "sessions" in data:
                        return {"sessions": data["sessions"]}
            except (json.JSONDecodeError, OSError):
                pass

        return {"sessions": []}

    @classmethod
    def _save_sessions_data(cls, sessions_data: dict, engine_id: str | None = None) -> None:
        """Save sessions data to storage.

        Args:
            sessions_data: Sessions data structure to save
            engine_id: Optional engine ID to save engine-specific sessions
        """
        session_state_dir = cls._get_session_state_dir(engine_id)
        session_state_dir.mkdir(parents=True, exist_ok=True)

        session_state_file = cls._get_session_state_file(engine_id)
        with session_state_file.open("w") as f:
            json.dump(sessions_data, f, indent=2)

    @classmethod
    def _get_current_engine_id(cls) -> str | None:
        """Get the current engine ID from EngineIdentityManager.

        Returns:
            str | None: The current engine ID or None if not set
        """
        # Import here to avoid circular imports
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        return GriptapeNodes.EngineIdentityManager().get_active_engine_id()

    @classmethod
    def _find_session_by_id(cls, sessions_data: dict, session_id: str) -> dict | None:
        """Find a session by ID in the sessions data.

        Args:
            sessions_data: The sessions data structure
            session_id: The session ID to find

        Returns:
            dict | None: The session data if found, None otherwise
        """
        for session in sessions_data.get("sessions", []):
            if session.get("session_id") == session_id:
                return session
        return None

    @classmethod
    def _add_or_update_session(cls, session_data: dict) -> None:
        """Add or update a session in the sessions data structure.

        Args:
            session_data: The session data to add or update
        """
        engine_id = cls._get_current_engine_id()
        sessions_data = cls._load_sessions_data(engine_id)

        # Find existing session
        session_id = session_data["session_id"]
        existing_session = cls._find_session_by_id(sessions_data, session_id)

        if existing_session:
            # Update existing session
            existing_session.update(session_data)
            existing_session["last_updated"] = datetime.now(tz=UTC).isoformat()
        else:
            # Add new session
            session_data["engine_id"] = engine_id
            sessions_data.setdefault("sessions", []).append(session_data)

        cls._save_sessions_data(sessions_data, engine_id)

    @classmethod
    def get_active_session_id(cls) -> str | None:
        """Get the active session ID.

        Returns:
            str | None: The active session ID or None if not set
        """
        return cls._active_session_id

    @classmethod
    def set_active_session_id(cls, session_id: str) -> None:
        """Set the active session ID.

        Args:
            session_id: The session ID to set as active

        Raises:
            ValueError: If session_id is not found in persisted sessions
        """
        engine_id = cls._get_current_engine_id()
        sessions_data = cls._load_sessions_data(engine_id)

        # Verify the session exists
        if cls._find_session_by_id(sessions_data, session_id):
            cls._active_session_id = session_id
            logger.debug("Set active session ID to: %s", session_id)
        else:
            msg = f"Session with ID {session_id} not found for engine {engine_id}"
            raise ValueError(msg)

    @classmethod
    def save_session(cls, session_id: str) -> None:
        """Save a session and make it the active session.

        Args:
            session_id: The session ID to save
        """
        engine_id = cls._get_current_engine_id()
        session_data = {
            "session_id": session_id,
            "engine_id": engine_id,
            "started_at": datetime.now(tz=UTC).isoformat(),
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }

        # Add or update the session
        cls._add_or_update_session(session_data)

        # Set as active session
        cls._active_session_id = session_id
        BaseEvent._session_id = session_id
        logger.info("Saved and activated session: %s for engine: %s", session_id, engine_id)

    @classmethod
    def get_saved_session_id(cls) -> str | None:
        """Get the active session ID if it exists.

        Returns:
            str | None: The active session ID or None if no active session
        """
        # Return active session if set
        if cls._active_session_id:
            return cls._active_session_id

        # Fall back to first session if available
        engine_id = cls._get_current_engine_id()
        sessions_data = cls._load_sessions_data(engine_id)
        sessions = sessions_data.get("sessions", [])
        if sessions:
            first_session_id = sessions[0].get("session_id")
            # Set as active for future calls
            BaseEvent._session_id = first_session_id
            cls._active_session_id = first_session_id
            logger.debug("Retrieved first saved session as active: %s for engine: %s", first_session_id, engine_id)
            return first_session_id

        return None

    @classmethod
    def clear_saved_session(cls) -> None:
        """Clear all saved session data for the current engine."""
        # Clear active session
        cls._active_session_id = None
        BaseEvent._session_id = None

        engine_id = cls._get_current_engine_id()
        session_state_file = cls._get_session_state_file(engine_id)
        if session_state_file.exists():
            try:
                session_state_file.unlink()
                logger.info("Cleared all saved session data for engine: %s", engine_id)
            except OSError:
                # If we can't delete the file, just clear its contents
                cls._save_sessions_data({"sessions": []}, engine_id)
                logger.warning("Could not delete session file for engine %s, cleared contents instead", engine_id)

    @classmethod
    def has_saved_session(cls) -> bool:
        """Check if there is a saved session.

        Returns:
            bool: True if there is a saved session, False otherwise
        """
        return cls.get_saved_session_id() is not None

    @classmethod
    def get_all_sessions(cls) -> list[dict]:
        """Get all registered sessions for the current engine.

        Returns:
            list[dict]: List of all session data for the current engine
        """
        engine_id = cls._get_current_engine_id()
        sessions_data = cls._load_sessions_data(engine_id)
        return sessions_data.get("sessions", [])

    @classmethod
    def remove_session(cls, session_id: str) -> None:
        """Remove a session from the sessions data for the current engine.

        Args:
            session_id: The session ID to remove
        """
        engine_id = cls._get_current_engine_id()
        sessions_data = cls._load_sessions_data(engine_id)

        # Remove the session
        sessions_data["sessions"] = [
            session for session in sessions_data.get("sessions", []) if session.get("session_id") != session_id
        ]

        # Clear active session if it was the removed session
        if cls._active_session_id == session_id:
            # Set to first remaining session or None
            remaining_sessions = sessions_data.get("sessions", [])
            cls._active_session_id = remaining_sessions[0].get("session_id") if remaining_sessions else None
            logger.info(
                "Removed active session %s for engine %s, set new active session to: %s",
                session_id,
                engine_id,
                cls._active_session_id,
            )

        cls._save_sessions_data(sessions_data, engine_id)
        logger.info("Removed session: %s from engine: %s", session_id, engine_id)

    @classmethod
    def get_sessions_for_engine(cls, engine_id: str) -> list[dict]:
        """Get all sessions for a specific engine.

        Args:
            engine_id: The engine ID to get sessions for

        Returns:
            list[dict]: List of session data for the specified engine
        """
        sessions_data = cls._load_sessions_data(engine_id)
        return sessions_data.get("sessions", [])

    @classmethod
    def get_all_sessions_across_engines(cls) -> dict[str, list[dict]]:
        """Get all sessions across all engines.

        Returns:
            dict[str, list[dict]]: Dictionary mapping engine IDs to their session lists
        """
        from griptape_nodes.retained_mode.utils.engine_identity import EngineIdentity

        all_engines = EngineIdentity.get_all_engines()
        result = {}

        for engine in all_engines:
            engine_id = engine.get("engine_id")
            if engine_id:
                result[engine_id] = cls.get_sessions_for_engine(engine_id)

        return result
