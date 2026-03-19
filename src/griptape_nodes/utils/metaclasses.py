from typing import Any, ClassVar


class SingletonMeta(type):
    _instances: ClassVar[dict] = {}

    def __call__(cls, *args, **kwargs) -> Any:
        if cls not in cls._instances:
            # Register instance before __init__ to prevent infinite recursion
            # when __init__ re-enters cls() (e.g. GriptapeNodes -> StaticFilesManager
            # -> ProjectManager -> GriptapeNodes).
            instance = object.__new__(cls)
            cls._instances[cls] = instance
            instance.__init__(*args, **kwargs)
        return cls._instances[cls]
