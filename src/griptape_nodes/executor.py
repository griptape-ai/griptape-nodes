from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable

from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
    from griptape_nodes.node_library.library_registry import Library

logger = logging.getLogger("griptape_nodes")


class ExecutorMethod:
    """Represents a method that can be executed by the Executor."""

    def __init__(
        self,
        name: str,
        method: Callable,
        library_name: str,
        source_type: str,
        description: str | None = None,
    ):
        self.name = name
        self.method = method
        self.library_name = library_name
        self.source_type = source_type  # 'node', 'advanced_library', 'engine'
        self.description = description or method.__doc__ or "No description available"
        self.signature = inspect.signature(method)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the method with given arguments."""
        return self.method(*args, **kwargs)

    def __repr__(self) -> str:
        return f"ExecutorMethod(name='{self.name}', library='{self.library_name}', source='{self.source_type}')"


class Executor(metaclass=SingletonMeta):
    """Simple Executor class that can draw methods from libraries.

    The Executor discovers and manages methods from:
    1. Node classes within libraries
    2. AdvancedNodeLibrary implementations
    3. Engine-native methods

    Methods are loaded dynamically from registered libraries and can be
    executed by name with parameters.
    """

    def __init__(self):
        self._methods: dict[str, ExecutorMethod] = {}
        self._method_priorities: dict[str, int] = {}  # For handling name conflicts
        self._loaded_libraries: set[str] = set()

    def refresh_methods(self) -> None:
        """Refresh all methods from currently registered libraries."""
        self._methods.clear()
        self._method_priorities.clear()
        self._loaded_libraries.clear()

        # Load methods from all registered libraries
        for library_name in LibraryRegistry.list_libraries():
            self.load_methods_from_library(library_name)

    def load_methods_from_library(self, library_name: str) -> None:
        """Load methods from a specific library."""
        if library_name in self._loaded_libraries:
            logger.debug(f"Library '{library_name}' methods already loaded")
            return

        try:
            library = LibraryRegistry.get_library(library_name)

            # Load methods from advanced library if available
            advanced_library = library.get_advanced_library()
            if advanced_library:
                self._load_methods_from_advanced_library(advanced_library, library_name)

            # Load static methods from node classes
            self._load_methods_from_node_classes(library, library_name)

            self._loaded_libraries.add(library_name)
            logger.info(f"Loaded methods from library: {library_name}")

        except KeyError:
            logger.error(f"Library '{library_name}' not found")
        except Exception as e:
            logger.error(f"Error loading methods from library '{library_name}': {e}")

    def _load_methods_from_advanced_library(
        self, advanced_library: AdvancedNodeLibrary, library_name: str
    ) -> None:
        """Load methods from an AdvancedNodeLibrary instance."""
        # Get all public methods that are not lifecycle callbacks
        excluded_methods = {'before_library_nodes_loaded', 'after_library_nodes_loaded'}

        for attr_name in dir(advanced_library):
            if attr_name.startswith('_') or attr_name in excluded_methods:
                continue

            attr = getattr(advanced_library, attr_name)
            if callable(attr):
                method = ExecutorMethod(
                    name=attr_name,
                    method=attr,
                    library_name=library_name,
                    source_type="advanced_library",
                    description=getattr(attr, '__doc__', None)
                )
                self._register_method(method, priority=2)  # Higher priority than node methods

    def _load_methods_from_node_classes(self, library: Library, library_name: str) -> None:
        """Load static and class methods from node classes in the library."""
        for node_type in library.get_registered_nodes():
            try:
                # Get the node class (not an instance)
                node_class = library._node_types[node_type]

                # Look for static methods and class methods marked for executor use
                for attr_name in dir(node_class):
                    if attr_name.startswith('_'):
                        continue

                    attr = getattr(node_class, attr_name)

                    # Check if it's a static method or class method
                    if (isinstance(attr, staticmethod) or
                        isinstance(attr, classmethod) or
                        (callable(attr) and hasattr(attr, '__self__') and attr.__self__ is node_class)):

                        # Only include methods marked with executor attribute or specific naming pattern
                        if (hasattr(attr, '_executor_method') or
                            attr_name.startswith('executor_') or
                            attr_name.endswith('_executor')):

                            method_name = attr_name
                            if attr_name.startswith('executor_'):
                                method_name = attr_name[9:]  # Remove 'executor_' prefix
                            elif attr_name.endswith('_executor'):
                                method_name = attr_name[:-9]  # Remove '_executor' suffix

                            method = ExecutorMethod(
                                name=method_name,
                                method=attr,
                                library_name=library_name,
                                source_type="node",
                                description=getattr(attr, '__doc__', None)
                            )
                            self._register_method(method, priority=1)  # Lower priority

            except Exception as e:
                logger.error(f"Error loading methods from node class '{node_type}': {e}")

    def _register_method(self, method: ExecutorMethod, priority: int) -> None:
        """Register a method, handling name conflicts with priority."""
        existing_method = self._methods.get(method.name)

        if existing_method:
            existing_priority = self._method_priorities.get(method.name, 0)

            if priority > existing_priority:
                # New method has higher priority, replace existing
                logger.info(f"Replacing method '{method.name}' from {existing_method.library_name} "
                           f"with version from {method.library_name} (higher priority)")
                self._methods[method.name] = method
                self._method_priorities[method.name] = priority
            else:
                # Keep existing method
                logger.debug(f"Keeping existing method '{method.name}' from {existing_method.library_name} "
                           f"over version from {method.library_name}")
        else:
            # No conflict, register method
            self._methods[method.name] = method
            self._method_priorities[method.name] = priority
            logger.debug(f"Registered method '{method.name}' from {method.library_name}")

    def execute(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a method by name with the given arguments.

        Args:
            method_name: Name of the method to execute
            *args: Positional arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            The result of the method execution

        Raises:
            KeyError: If the method name is not found
            Exception: Any exception raised by the executed method
        """
        if method_name not in self._methods:
            available_methods = list(self._methods.keys())
            raise KeyError(f"Method '{method_name}' not found. Available methods: {available_methods}")

        method = self._methods[method_name]
        logger.debug(f"Executing method '{method_name}' from {method.library_name}")

        try:
            return method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error executing method '{method_name}': {e}")
            raise

    def has_method(self, method_name: str) -> bool:
        """Check if a method with the given name is available."""
        return method_name in self._methods

    def get_method_info(self, method_name: str) -> ExecutorMethod | None:
        """Get information about a method."""
        return self._methods.get(method_name)

    def list_methods(self, library_name: str | None = None) -> list[ExecutorMethod]:
        """List all available methods, optionally filtered by library."""
        methods = list(self._methods.values())

        if library_name:
            methods = [m for m in methods if m.library_name == library_name]

        return sorted(methods, key=lambda m: (m.library_name, m.name))

    def get_method_signature(self, method_name: str) -> inspect.Signature | None:
        """Get the signature of a method."""
        method = self._methods.get(method_name)
        return method.signature if method else None


def executor_method(func: Callable) -> Callable:
    """Decorator to mark a method for inclusion in the Executor.

    Usage:
        @staticmethod
        @executor_method
        def my_utility_function(arg1, arg2):
            return arg1 + arg2
    """
    func._executor_method = True
    return func