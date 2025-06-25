"""Manages engine identity for a single engine per machine.

Handles engine ID, name storage, and generation for unique engine identification.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from xdg_base_dirs import xdg_data_home

from .name_generator import generate_engine_name


class EngineIdentity:
    """Manages engine identity for a single engine per machine."""

    _ENGINE_DATA_FILE = "engine.json"

    @classmethod
    def _get_engine_data_dir(cls) -> Path:
        """Get the XDG data directory for engine identity storage."""
        return xdg_data_home() / "griptape_nodes"

    @classmethod
    def _get_engine_data_file(cls) -> Path:
        """Get the path to the engine data storage file."""
        return cls._get_engine_data_dir() / cls._ENGINE_DATA_FILE

    @classmethod
    def _load_engine_data(cls) -> dict:
        """Load engine data from storage.

        Returns:
            dict: Engine data including id, name, timestamps
        """
        engine_data_file = cls._get_engine_data_file()

        if engine_data_file.exists():
            try:
                with engine_data_file.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, OSError):
                # If file is corrupted, return empty dict
                pass

        return {}

    @classmethod
    def _save_engine_data(cls, engine_data: dict) -> None:
        """Save engine data to storage.

        Args:
            engine_data: Engine data to save
        """
        engine_data_dir = cls._get_engine_data_dir()
        engine_data_dir.mkdir(parents=True, exist_ok=True)

        engine_data_file = cls._get_engine_data_file()
        with engine_data_file.open("w") as f:
            json.dump(engine_data, f, indent=2)

    @classmethod
    def get_engine_data(cls) -> dict:
        """Get the engine data, creating default if it doesn't exist.

        Returns:
            dict: The engine data
        """
        engine_data = cls._load_engine_data()

        if not engine_data or "id" not in engine_data:
            # Create default engine data
            engine_data = {
                "id": os.getenv("GTN_ENGINE_ID") or str(uuid.uuid4()),
                "name": generate_engine_name(),
                "created_at": datetime.now(tz=UTC).isoformat(),
            }
            cls._save_engine_data(engine_data)

        return engine_data

    @classmethod
    def get_engine_id(cls) -> str:
        """Get the engine ID.

        Returns:
            str: The engine ID (UUID)
        """
        engine_data = cls.get_engine_data()
        return engine_data["id"]

    @classmethod
    def get_engine_name(cls) -> str:
        """Get the engine name.

        Returns:
            str: The engine name
        """
        engine_data = cls.get_engine_data()
        return engine_data["name"]

    @classmethod
    def set_engine_name(cls, engine_name: str) -> None:
        """Set and persist the engine name.

        Args:
            engine_name: The new engine name to set
        """
        engine_data = cls._load_engine_data()

        # Ensure we have basic engine data
        if not engine_data or "id" not in engine_data:
            engine_data = cls.get_engine_data()

        engine_data["name"] = engine_name
        engine_data["updated_at"] = datetime.now(tz=UTC).isoformat()
        cls._save_engine_data(engine_data)

    @classmethod
    def get_engine_data_file_path(cls) -> Path:
        """Get the path where engine data is stored (for debugging/inspection).

        Returns:
            Path: The path to the engine data file
        """
        return cls._get_engine_data_file()
