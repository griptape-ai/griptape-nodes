from __future__ import annotations

from typing import Any


class BaseDraw:
    """A minimal drawable object with name and free-form metadata.

    Position and size are stored in metadata under keys:
      - x, y
      - width, height
    """

    name: str
    metadata: dict[str, Any]

    def __init__(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
        *,
        position: tuple[float, float] | None = None,
        size: tuple[float, float] | None = None,
    ) -> None:
        self.name = name
        self.metadata = {} if metadata is None else dict(metadata)
        # Optionally initialize position/size
        if position is not None:
            self.metadata["x"] = float(position[0])
            self.metadata["y"] = float(position[1])
        if size is not None:
            self.metadata["width"] = float(size[0])
            self.metadata["height"] = float(size[1])

    # Position
    def get_position(self) -> tuple[float, float] | None:
        x = self.metadata.get("x")
        y = self.metadata.get("y")
        if x is None or y is None:
            return None
        return float(x), float(y)

    def set_position(self, x: float, y: float) -> None:
        self.metadata["x"] = x
        self.metadata["y"] = y

    # Size
    def get_size(self) -> tuple[float, float] | None:
        width = self.metadata.get("width")
        height = self.metadata.get("height")
        if width is None or height is None:
            return None
        return float(width), float(height)

    def set_size(self, width: float, height: float) -> None:
        self.metadata["width"] = width
        self.metadata["height"] = height

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metadata": dict(self.metadata),
        }
