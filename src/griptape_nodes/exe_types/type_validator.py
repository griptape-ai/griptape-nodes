from __future__ import annotations

import importlib
import inspect
import logging
import sys
import typing
from typing import Any

from griptape.mixins.singleton_mixin import SingletonMixin

logger = logging.getLogger(__name__)

ALLOWED_NUM_ARGS = 2



class TypeValidator(SingletonMixin):
    """A type string validator that checks against known types.

    Implemented as a singleton to ensure consistent behavior across an application.
    """

    @classmethod
    def safe_serialize(cls, obj: Any) -> Any:  # noqa: PLR0911 TODO(griptape): resolve
        if obj is None:
            return None
        if isinstance(obj, dict):
            return {k: cls.safe_serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [cls.safe_serialize(item) for item in list(obj)]
        if isinstance(obj, (str, int, float, bool, list, dict, type(None))):
            return obj
        try:
            obj_dict = obj.to_dict()
        except Exception:
            logger.warning("Error serializing object: Going to use type name.")
        else:
            return obj_dict
        if hasattr(obj, "id"):
            return {f"{type(obj).__name__} Object: {obj.id}"}
        return f"{type(obj).__name__} Object"
