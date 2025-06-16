"""Manages session persistence using XDG state directory.

Handles storing and retrieving active session information across engine restarts.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from xdg_base_dirs import xdg_state_home


class SessionPersistence:
    """Manages session persistence for active session tracking."""

    _SESSION_STATE_FILE = "session.json"

    @classmethod
    def _get_session_state_dir(cls) -> Path:
        """Get the XDG state directory for session persistence."""
        return xdg_state_home() / "griptape_nodes"

    @classmethod
    def _get_session_state_file(cls) -> Path:
        """Get the path to the session state storage file."""
        return cls._get_session_state_dir() / cls._SESSION_STATE_FILE

    @classmethod
    def _load_session_data(cls) -> dict:
        """Load session data from storage.

        Returns:
            dict: Session data including id, timestamps
        """
        session_state_file = cls._get_session_state_file()

        if session_state_file.exists():
            try:
                with session_state_file.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, OSError):
                # If file is corrupted, return empty dict
                pass

        return {}

    @classmethod
    def _save_session_data(cls, session_data: dict) -> None:
        """Save session data to storage.

        Args:
            session_data: Session data to save
        """
        session_state_dir = cls._get_session_state_dir()
        session_state_dir.mkdir(parents=True, exist_ok=True)

        session_state_file = cls._get_session_state_file()
        with session_state_file.open("w") as f:
            json.dump(session_data, f, indent=2)

    @classmethod
    def persist_session(cls, session_id: str) -> None:
        """Persist the active session ID to storage.

        Args:
            session_id: The session ID to persist
        """
        session_data = {
            "session_id": session_id,
            "started_at": datetime.now(tz=UTC).isoformat(),
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }
        cls._save_session_data(session_data)

    @classmethod
    def get_persisted_session_id(cls) -> str | None:
        """Get the persisted session ID if it exists.

        Returns:
            str | None: The persisted session ID or None if no session is persisted
        """
        session_data = cls._load_session_data()
        return session_data.get("session_id")

    @classmethod
    def clear_persisted_session(cls) -> None:
        """Clear the persisted session data."""
        session_state_file = cls._get_session_state_file()
        if session_state_file.exists():
            try:
                session_state_file.unlink()
            except OSError:
                # If we can't delete the file, just clear its contents
                cls._save_session_data({})

    @classmethod
    def has_persisted_session(cls) -> bool:
        """Check if there is a persisted session.

        Returns:
            bool: True if there is a persisted session, False otherwise
        """
        return cls.get_persisted_session_id() is not None
