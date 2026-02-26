from typing import TypedDict


class WaypointDefinition(TypedDict):
    """Serialized waypoint definition for connection edge bend points."""

    x: float
    y: float
