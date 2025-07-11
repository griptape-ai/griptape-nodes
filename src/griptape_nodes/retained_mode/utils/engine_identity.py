"""Manages engine identity for multiple engines per machine.

Handles engine ID, name storage, and generation for unique engine identification.
Supports multiple engines with selection via GTN_ENGINE_ID environment variable.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from xdg_base_dirs import xdg_data_home

from .name_generator import generate_engine_name


class EngineIdentity:
    """Manages engine identity for multiple engines per machine."""

    _ENGINE_DATA_FILE = "engines.json"

    @classmethod
    def _get_engine_data_dir(cls) -> Path:
        """Get the XDG data directory for engine identity storage."""
        return xdg_data_home() / "griptape_nodes"

    @classmethod
    def _get_engine_data_file(cls) -> Path:
        """Get the path to the engine data storage file."""
        return cls._get_engine_data_dir() / cls._ENGINE_DATA_FILE

    @classmethod
    def _load_engines_data(cls) -> dict:
        """Load engines data from storage.

        Returns:
            dict: Engines data structure with engines array and default_engine_id
        """
        engine_data_file = cls._get_engine_data_file()

        if engine_data_file.exists():
            try:
                with engine_data_file.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "engines" in data:
                        return data
            except (json.JSONDecodeError, OSError):
                pass

        return {"engines": [], "default_engine_id": None}

    @classmethod
    def _save_engines_data(cls, engines_data: dict) -> None:
        """Save engines data to storage.

        Args:
            engines_data: Engines data structure to save
        """
        engine_data_dir = cls._get_engine_data_dir()
        engine_data_dir.mkdir(parents=True, exist_ok=True)

        engine_data_file = cls._get_engine_data_file()
        with engine_data_file.open("w") as f:
            json.dump(engines_data, f, indent=2)

    @classmethod
    def _get_selected_engine_id(cls) -> str | None:
        """Get the selected engine ID from environment variable or default.

        Returns:
            str | None: The selected engine ID or None if not specified
        """
        return os.getenv("GTN_ENGINE_ID")

    @classmethod
    def _find_engine_by_id(cls, engines_data: dict, engine_id: str) -> dict | None:
        """Find an engine by ID in the engines data.

        Args:
            engines_data: The engines data structure
            engine_id: The engine ID to find

        Returns:
            dict | None: The engine data if found, None otherwise
        """
        for engine in engines_data.get("engines", []):
            if engine.get("id") == engine_id:
                return engine
        return None

    @classmethod
    def get_engine_data(cls) -> dict:
        """Get the current engine data, creating default if it doesn't exist.

        Returns:
            dict: The current engine data
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
            engine_data = {
                "id": selected_engine_id,
                "name": generate_engine_name(),
                "created_at": datetime.now(tz=UTC).isoformat(),
            }
        else:
            # Use default engine (first one) or create new one
            if engines_data.get("engines"):
                default_id = engines_data.get("default_engine_id")
                if default_id:
                    engine_data = cls._find_engine_by_id(engines_data, default_id)
                    if engine_data:
                        return engine_data
                # Fall back to first engine
                return engines_data["engines"][0]

            # Create new engine
            engine_data = {
                "id": str(uuid.uuid4()),
                "name": generate_engine_name(),
                "created_at": datetime.now(tz=UTC).isoformat(),
            }

        # Add or update engine in the data structure
        cls._add_or_update_engine(engine_data)
        return engine_data

    @classmethod
    def _add_or_update_engine(cls, engine_data: dict) -> None:
        """Add or update an engine in the engines data structure.

        Args:
            engine_data: The engine data to add or update
        """
        engines_data = cls._load_engines_data()

        # Find existing engine
        engine_id = engine_data["id"]
        existing_engine = cls._find_engine_by_id(engines_data, engine_id)

        if existing_engine:
            # Update existing engine
            existing_engine.update(engine_data)
            existing_engine["updated_at"] = datetime.now(tz=UTC).isoformat()
        else:
            # Add new engine
            engines_data.setdefault("engines", []).append(engine_data)

            # Set as default if it's the first engine
            if not engines_data.get("default_engine_id") and len(engines_data["engines"]) == 1:
                engines_data["default_engine_id"] = engine_id

        cls._save_engines_data(engines_data)

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
        """Set and persist the current engine name.

        Args:
            engine_name: The new engine name to set
        """
        # Get current engine data
        engine_data = cls.get_engine_data()

        # Update the name
        engine_data["name"] = engine_name
        engine_data["updated_at"] = datetime.now(tz=UTC).isoformat()

        # Save updated engine data
        cls._add_or_update_engine(engine_data)

    @classmethod
    def get_all_engines(cls) -> list[dict]:
        """Get all registered engines.

        Returns:
            list[dict]: List of all engine data
        """
        engines_data = cls._load_engines_data()
        return engines_data.get("engines", [])

    @classmethod
    def get_default_engine_id(cls) -> str | None:
        """Get the default engine ID.

        Returns:
            str | None: The default engine ID or None if not set
        """
        engines_data = cls._load_engines_data()
        return engines_data.get("default_engine_id")

    @classmethod
    def set_default_engine_id(cls, engine_id: str) -> None:
        """Set the default engine ID.

        Args:
            engine_id: The engine ID to set as default
        """
        engines_data = cls._load_engines_data()

        # Verify the engine exists
        if cls._find_engine_by_id(engines_data, engine_id):
            engines_data["default_engine_id"] = engine_id
            cls._save_engines_data(engines_data)
        else:
            msg = f"Engine with ID {engine_id} not found"
            raise ValueError(msg)

    @classmethod
    def get_engine_data_file_path(cls) -> Path:
        """Get the path where engine data is stored (for debugging/inspection).

        Returns:
            Path: The path to the engine data file
        """
        return cls._get_engine_data_file()
