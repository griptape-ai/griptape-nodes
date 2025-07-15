"""Manages engine identity state.

Centralizes engine identity management, providing a consistent interface for
engine ID and name operations.
"""

import logging
from pathlib import Path

from griptape_nodes.retained_mode.events.base_events import BaseEvent
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.utils.engine_identity import EngineIdentity

logger = logging.getLogger("griptape_nodes")


class EngineIdentityManager:
    """Manages engine identity and active engine state."""

    _active_engine_id: str | None = None

    def __init__(self, event_manager: EventManager | None = None) -> None:
        """Initialize the EngineIdentityManager.

        Args:
            event_manager: The EventManager instance to use for event handling.
        """
        if event_manager is not None:
            # Register event handlers here when engine events are defined
            pass

    @classmethod
    def get_active_engine_id(cls) -> str | None:
        """Get the active engine ID.

        Returns:
            str | None: The active engine ID or None if not set
        """
        return cls._active_engine_id

    @classmethod
    def set_active_engine_id(cls, engine_id: str) -> None:
        """Set the active engine ID.

        Args:
            engine_id: The engine ID to set as active
        """
        cls._active_engine_id = engine_id
        logger.debug("Set active engine ID to: %s", engine_id)

    @classmethod
    def initialize_engine_id(cls) -> str:
        """Initialize the engine ID if not already set."""
        if cls._active_engine_id is None:
            engine_id = EngineIdentity.get_engine_id()
            BaseEvent._engine_id = engine_id
            cls._active_engine_id = engine_id
            logger.debug("Initialized engine ID: %s", engine_id)

        return cls._active_engine_id

    @classmethod
    def get_engine_data(cls) -> dict:
        """Get the current engine data, creating default if it doesn't exist.

        Returns:
            dict: The current engine data
        """
        return EngineIdentity.get_engine_data()

    @classmethod
    def get_engine_name(cls) -> str:
        """Get the engine name.

        Returns:
            str: The engine name
        """
        return EngineIdentity.get_engine_name()

    @classmethod
    def set_engine_name(cls, engine_name: str) -> None:
        """Set and persist the current engine name.

        Args:
            engine_name: The new engine name to set
        """
        EngineIdentity.set_engine_name(engine_name)
        logger.info("Updated engine name to: %s", engine_name)

    @classmethod
    def get_all_engines(cls) -> list[dict]:
        """Get all registered engines.

        Returns:
            list[dict]: List of all engine data
        """
        return EngineIdentity.get_all_engines()

    @classmethod
    def get_default_engine_id(cls) -> str | None:
        """Get the default engine ID.

        Returns:
            str | None: The default engine ID or None if not set
        """
        return EngineIdentity.get_default_engine_id()

    @classmethod
    def set_default_engine_id(cls, engine_id: str) -> None:
        """Set the default engine ID.

        Args:
            engine_id: The engine ID to set as default

        Raises:
            ValueError: If engine_id is not found in registered engines
        """
        try:
            EngineIdentity.set_default_engine_id(engine_id)
            logger.info("Set default engine ID to: %s", engine_id)
        except ValueError as e:
            logger.error("Failed to set default engine ID: %s", e)
            raise

    @classmethod
    def get_engine_data_file_path(cls) -> Path:
        """Get the path where engine data is stored (for debugging/inspection).

        Returns:
            Path: The path to the engine data file
        """
        return EngineIdentity.get_engine_data_file_path()

    @classmethod
    def ensure_engine_initialized(cls) -> str:
        """Ensure engine is initialized and return the engine ID.

        Returns:
            str: The initialized engine ID
        """
        cls.initialize_engine_id()
        engine_id = cls.get_active_engine_id()
        if engine_id is None:
            msg = "Failed to initialize engine ID"
            raise RuntimeError(msg)
        return engine_id
