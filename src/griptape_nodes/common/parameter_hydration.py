"""Rehydrate serialized artifacts in parameter-value dicts.

Parameter values cross JSON boundaries between the orchestrator and worker
processes. SerializableMixin instances are unstructured via `to_dict()` on
send, producing dicts like ``{"type": "VideoUrlArtifact", "value": "..."}``.
The cattrs converter in ``event_converter.py`` has no matching structure
hook for SerializableMixin, and parameter_values/parameter_output_values
are typed ``dict[str, Any]``, so the reverse direction is a no-op without
this helper.
"""

from __future__ import annotations

import logging
from typing import Any

from griptape.artifacts import BaseArtifact

logger = logging.getLogger(__name__)


def hydrate_parameter_values(values: dict[str, Any]) -> dict[str, Any]:
    """Reconstitute serialized artifacts in a parameter-value dict.

    Walks the dict and replaces any value that looks like a serialized
    SerializableMixin (dict with a ``"type"`` key that resolves to an
    artifact subclass) with the reconstituted object. Lists are walked
    element-wise so parameters like ``list[VideoUrlArtifact]`` work.
    Non-matching values pass through unchanged.
    """
    return {name: _hydrate(value) for name, value in values.items()}


def _hydrate(value: Any) -> Any:
    if isinstance(value, dict) and "type" in value:
        try:
            return BaseArtifact.from_dict(value)
        except Exception:
            logger.debug("Could not hydrate value as artifact; passing through.", exc_info=True)
            return value
    if isinstance(value, list):
        return [_hydrate(item) for item in value]
    return value
