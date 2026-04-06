from __future__ import annotations

import logging
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from datetime import datetime
from typing import Any

from cattrs.gen import make_dict_structure_fn, make_dict_unstructure_fn, override
from cattrs.preconf.json import make_converter
from cattrs.strategies import use_class_methods
from griptape.mixins.serializable_mixin import SerializableMixin
from pydantic import BaseModel

logger = logging.getLogger(__name__)

converter = make_converter()


# --- Unstructure hooks (serialization) ---

# SerializableMixin subclasses (BaseArtifact, BaseTool, Structure, etc.)
converter.register_unstructure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, SerializableMixin),
    lambda obj: obj.to_dict(),
)

# Pydantic BaseModel subclasses (WorkflowMetadata, WorkflowShape, etc.)
# mode="json" ensures all values are JSON-serializable (e.g. datetime -> ISO string)
converter.register_unstructure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, BaseModel),
    lambda obj: obj.model_dump(mode="json"),
)

# datetime subclasses (e.g. pendulum.DateTime from griptape) -> ISO format string
converter.register_unstructure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, datetime) and cls is not datetime,
    lambda obj: obj.isoformat(),
)

# Exception -> string representation
converter.register_unstructure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, Exception),
    str,
)

# Bare `type` references (e.g. provider_class: type)
converter.register_unstructure_hook(type, lambda t: f"{t.__module__}.{t.__qualname__}")


# --- Structure hooks (deserialization) ---

# The JSON preset strict mode rejects ints for float fields, but JSON has
# no distinction between int and float, so coerce int -> float on input.
converter.register_structure_hook(float, lambda v, _: float(v))

# Pydantic BaseModel subclasses
converter.register_structure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, BaseModel),
    lambda obj, cls: cls.model_validate(obj),
)

# Exception <- string or dict
converter.register_structure_hook_func(
    lambda cls: isinstance(cls, type) and issubclass(cls, Exception),
    lambda obj, cls: cls(obj) if isinstance(obj, str) else cls(str(obj)),
)


# --- Class-specific (un)structuring methods ---
#
# Classes that need custom serialization can define `_cattrs_structure` (classmethod)
# and/or `_cattrs_unstructure` (instance method) instead of registering hooks here.

use_class_methods(converter, structure_method_name="_cattrs_structure", unstructure_method_name="_cattrs_unstructure")


# --- Hook factories for dataclasses ---
#
# Some event dataclasses have circular imports that force TYPE_CHECKING-only imports
# (e.g. flow_events <-> workflow_events). With `from __future__ import annotations`,
# cattrs' `get_type_hints()` can fail with NameError for those forward references.
# The factories below catch this and fall back to a simpler field-iteration approach.


def _fallback_unstructure(obj: Any) -> dict[str, Any]:
    """Fallback unstructure for dataclasses where get_type_hints() fails."""
    result = {}
    for f in dc_fields(obj):
        value = getattr(obj, f.name)
        try:
            result[f.name] = converter.unstructure(value)
        except Exception:
            logger.debug(
                "Failed to unstructure field '%s' (type=%s), using raw value",
                f.name,
                type(value).__name__,
                exc_info=True,
            )
            result[f.name] = value
    return result


def _make_fallback_structure_fn(cls: type) -> Any:
    """Fallback structure for dataclasses where get_type_hints() fails."""

    def structure_fn(data: dict[str, Any], _cls: type = cls) -> Any:
        init_fields = {f.name for f in dc_fields(_cls) if f.init}
        filtered = {k: v for k, v in data.items() if k in init_fields}
        return _cls(**filtered)

    return structure_fn


def _make_dataclass_unstructure_fn(cls: type) -> Any:
    """Generate an unstructure function that includes init=False fields."""
    try:
        return make_dict_unstructure_fn(cls, converter, _cattrs_include_init_false=True)
    except NameError:
        return _fallback_unstructure


def _make_dataclass_structure_fn(cls: type) -> Any:
    """Generate a structure function that omits init=False fields."""
    try:
        overrides = {}
        for f in dc_fields(cls):
            if not f.init:
                overrides[f.name] = override(omit=True)
        return make_dict_structure_fn(cls, converter, **overrides)
    except NameError:
        return _make_fallback_structure_fn(cls)


converter.register_unstructure_hook_factory(
    lambda cls: is_dataclass(cls) and isinstance(cls, type),
    _make_dataclass_unstructure_fn,
)

converter.register_structure_hook_factory(
    lambda cls: is_dataclass(cls) and isinstance(cls, type),
    _make_dataclass_structure_fn,
)


def safe_unstructure(obj: Any) -> Any:
    """Unstructure an arbitrary object into a JSON-serializable form.

    Wraps the cattrs converter with a fallback for dataclasses that tries
    each field individually, so a single bad field doesn't lose the entire
    object. Falls back to str() only as a last resort.
    """
    try:
        return converter.unstructure(obj)
    except Exception:
        logger.debug("Failed to unstructure object (type=%s), using fallback", type(obj).__name__, exc_info=True)
        if is_dataclass(obj) and not isinstance(obj, type):
            return _fallback_unstructure(obj)
        return str(obj)
