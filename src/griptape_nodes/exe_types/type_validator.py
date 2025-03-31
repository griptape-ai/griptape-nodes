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


class TypeValidationError(Exception):
    """Exception raised for errors in type validation."""


class TypeResolutionError(Exception):
    """Exception raised when a type cannot be resolved."""


class TypeConversionError(Exception):
    """Exception raised when a type string cannot be converted to a Python type."""


class ContainerTypeError(Exception):
    """Exception raised for issues with container types."""


class TypeValidator(SingletonMixin):
    """A type string validator that checks against known types.

    Implemented as a singleton to ensure consistent behavior across an application.
    """

    def __init__(self, allow_dynamic_imports=False, namespace=None) -> None:  # noqa: FBT002
        """Initialize the TypeValidator.

        Args:
            allow_dynamic_imports: Whether to allow dynamically importing modules
                                  to resolve types (default: False)
            namespace: Optional dict or module to use as an additional lookup source
                      for type resolution
        """
        # Skip re-initialization if instance already exists
        if hasattr(self, "initialized") and self.initialized:
            return

        # Whether to allow dynamic imports
        self.allow_dynamic_imports = allow_dynamic_imports

        # Store additional namespace for lookups
        self.namespace = namespace

        # Known primitive types
        self.builtin_types = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "tuple": tuple,
            "dict": dict,
            "set": set,
            "frozenset": frozenset,
            "bytes": bytes,
            "bytearray": bytearray,
            "complex": complex,
            "None": type(None),
            "NoneType": type(None),
            "any": object,
            "Any": object,
            "object": object,
        }

        # Map of container type string patterns to validation functions
        self.container_types = {
            "list[": list,
            "List[": list,
            "dict[": dict,
            "Dict[": dict,
            "set[": set,
            "Set[": set,
            "tuple[": tuple,
            "Tuple[": tuple,
            "Union[": None,  # Special handling for Union
            "Optional[": None,  # Special handling for Optional
        }

        # Python 3.10+ pipe operator for union types
        self.union_pipe_pattern = "|"

        # Type aliases from typing module
        self._add_typing_aliases()

        # Cache for resolved types to improve performance
        self.type_cache = {}

        # Mark as initialized
        self.initialized = True

    def _add_typing_aliases(self) -> None:
        """Add common type aliases from the typing module."""
        # Add common typing aliases
        for name in dir(typing):
            if name[0].isupper() and not name.startswith("_"):
                attr = getattr(typing, name)
                if isinstance(attr, type) or hasattr(attr, "__origin__"):
                    self.builtin_types[name] = attr

    @classmethod
    def configure(cls, allow_dynamic_imports=False, namespace=None) -> TypeValidator:  # noqa: FBT002
        """Configure the TypeValidator singleton instance.

        Args:
            allow_dynamic_imports: Whether to allow dynamically importing modules
                                 to resolve types
            namespace: Optional dict or module to use as an additional lookup source
                      for type resolution

        Returns:
            The configured TypeValidator instance
        """
        instance = cls(allow_dynamic_imports, namespace)
        return instance

    @classmethod
    def register_type(cls, type_name, type_obj) -> bool:
        """Explicitly register a type with the validator.

        Args:
            type_name: The name of the type as a string
            type_obj: The actual type object

        Returns:
            True if successfully registered, False otherwise
        """
        if not isinstance(type_obj, type):
            return False

        instance = cls.get_instance()
        instance.builtin_types[type_name] = type_obj
        instance.type_cache[type_name] = type_obj
        return True

    @classmethod
    def get_instance(cls) -> TypeValidator:
        """Get the TypeValidator singleton instance.

        Returns:
            The TypeValidator instance
        """
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def resolve_type(cls, type_str: str) -> type | None:  # noqa: PLR0911, C901, PLR0912, PLR0915 TODO(griptape): resolve
        """Attempt to resolve a type string to an actual type.

        Args:
            type_str: The type string to resolve

        Returns:
            The type object if resolved, None otherwise
        """
        instance = cls.get_instance()

        # Check cache first
        if type_str in instance.type_cache:
            return instance.type_cache[type_str]

        # Check builtin types
        if type_str in instance.builtin_types:
            instance.type_cache[type_str] = instance.builtin_types[type_str]
            return instance.builtin_types[type_str]

        # Check for container types (just validate the prefix)
        for prefix in instance.container_types:
            if type_str.startswith(prefix):
                instance.type_cache[type_str] = instance.container_types[prefix]
                return instance.container_types[prefix]

        # Try special case for fully qualified import paths first
        if instance.allow_dynamic_imports and "." in type_str:
            try:
                # Direct import approach for fully qualified names
                module_path, class_name = type_str.rsplit(".", 1)
                module = importlib.import_module(module_path)
                if hasattr(module, class_name):
                    type_obj = getattr(module, class_name)
                    if isinstance(type_obj, type):
                        instance.type_cache[type_str] = type_obj
                        return type_obj
            except (ImportError, AttributeError, ValueError):
                pass

        # Check all loaded modules for the type
        for _, module in list(sys.modules.items()):
            try:
                if hasattr(module, type_str):
                    type_obj = getattr(module, type_str)
                    if isinstance(type_obj, type):
                        instance.type_cache[type_str] = type_obj
                        return type_obj
            except (AttributeError, TypeError):
                # Skip modules that raise errors when accessing attributes
                continue

        # Try to find the type in the current scope using frame inspection
        frame = inspect.currentframe()
        if frame:
            try:
                # Start with current frame and work backwards
                current_frame = frame
                max_frames = 10  # Increase from 3 to 10 for deeper inspection

                while current_frame and max_frames > 0:
                    # Check locals
                    if type_str in current_frame.f_locals:
                        obj = current_frame.f_locals[type_str]
                        if isinstance(obj, type):
                            instance.type_cache[type_str] = obj
                            return obj

                    # Check globals
                    if type_str in current_frame.f_globals:
                        obj = current_frame.f_globals[type_str]
                        if isinstance(obj, type):
                            instance.type_cache[type_str] = obj
                            return obj

                    # Move to parent frame
                    current_frame = current_frame.f_back
                    max_frames -= 1

                # Check builtins
                if hasattr(__builtins__, type_str):
                    type_obj = getattr(__builtins__, type_str)
                    instance.type_cache[type_str] = type_obj
                    return type_obj

                # If we're allowing dynamic imports, try a more comprehensive approach
                if instance.allow_dynamic_imports and "." in type_str:
                    # Multi-level approach for complex imports
                    parts = type_str.split(".")
                    for i in range(1, len(parts)):
                        module_path = ".".join(parts[:i])
                        try:
                            module = importlib.import_module(module_path)
                            obj = module
                            for part in parts[i:]:
                                if hasattr(obj, part):
                                    obj = getattr(obj, part)
                                else:
                                    obj = None
                                    break

                            if isinstance(obj, type):
                                instance.type_cache[type_str] = obj
                                return obj
                        except ImportError:
                            continue

                # Try common modules that might be imported but not checked yet
                common_modules = [
                    "datetime",
                    "collections",
                    "decimal",
                    "pathlib",
                    "uuid",
                    "json",
                    "re",
                    "os",
                    "sys",
                    "io",
                    "time",
                    "math",
                    "random",
                    "itertools",
                    "functools",
                ]
                for module_name in common_modules:
                    if module_name in sys.modules:
                        module = sys.modules[module_name]
                        if hasattr(module, type_str):
                            type_obj = getattr(module, type_str)
                            if isinstance(type_obj, type):
                                instance.type_cache[type_str] = type_obj
                                return type_obj
            finally:
                del frame  # Avoid reference cycles

        # Check the custom namespace if provided
        if instance.namespace:
            try:
                if hasattr(instance.namespace, type_str):
                    obj = getattr(instance.namespace, type_str)
                    if isinstance(obj, type):
                        instance.type_cache[type_str] = obj
                        return obj
                elif hasattr(instance.namespace, "__getitem__") and type_str in instance.namespace:
                    obj = instance.namespace[type_str]
                    if isinstance(obj, type):
                        instance.type_cache[type_str] = obj
                        return obj
            except (AttributeError, KeyError, TypeError):
                pass

        # Could not resolve the type
        instance.type_cache[type_str] = None
        return None

    @classmethod
    def _handle_pipe_union(cls, type_str: str) -> tuple[bool, list[str]]:
        """Handle Python 3.10+ union type syntax using pipe operator (e.g., 'int | str').

        Args:
            type_str: Type string to process

        Returns:
            Tuple of (is_pipe_union, list of type strings)
        """
        instance = cls.get_instance()

        # Only process if type_str contains the pipe character and isn't in quotes
        if instance.union_pipe_pattern not in type_str:
            return False, [type_str]

        # Handle nested bracketed expressions
        # We need to ensure we don't split inside parentheses or brackets
        result = []
        current = ""
        bracket_stack = []

        for char in type_str:
            if char in "[({":
                bracket_stack.append(char)
            elif (
                char in "})]"
                and bracket_stack
                and (
                    (char == "}" and bracket_stack[-1] == "{")
                    or (char == ")" and bracket_stack[-1] == "(")
                    or (char == "]" and bracket_stack[-1] == "[")
                )
            ):
                bracket_stack.pop()

            if char == "|" and not bracket_stack:
                # We found a top-level pipe operator
                if current.strip():
                    result.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            result.append(current.strip())

        # Only consider it a pipe union if we found at least one pipe operator
        return len(result) > 1, result

    @classmethod
    def validate_type_spec(cls, type_str: str) -> bool:  # noqa: PLR0911, C901, PLR0912 TODO(griptape): resolve
        """Validate a single type string against known types and proper syntax.

        Args:
            type_str: Type string to validate

        Returns:
            Boolean indicating if the type string is valid
        """
        instance = cls.get_instance()
        type_str = type_str.strip()

        # Handle Python 3.10+ pipe union types
        is_pipe_union, union_types = cls._handle_pipe_union(type_str)
        if is_pipe_union:
            # Union is valid if at least one of the types is valid
            for union_type in union_types:
                if cls.validate_type_spec(union_type):
                    return True
            return False

        # First check if it's a known primitive type
        if type_str in instance.builtin_types:
            return True

        # Check if it's a container type
        is_container = False
        container_type = None

        for prefix in instance.container_types:
            if type_str.startswith(prefix):
                is_container = True
                container_type = prefix
                break

        if is_container:
            # Parse the container arguments
            try:
                args = cls._parse_container_args(type_str)

                # Check for syntax errors in arguments
                if not args or "" in args:
                    return False

                # Special handling for Union and Optional
                if container_type in ["Union[", "Optional["]:
                    # Union and Optional are valid if at least one argument is valid
                    args_valid = False
                    for arg in args:
                        if cls.validate_type_spec(arg):
                            args_valid = True
                            break

                    # For Optional, also check if None/NoneType is included explicitly or implicitly
                    if container_type == "Optional[" and len(args) == 1:
                        # Optional[T] is equivalent to Union[T, None]
                        args_valid = cls.validate_type_spec(args[0])

                    return args_valid
                # For other containers, all arguments must be valid
                args_valid = True
                for arg in args:
                    # Recursively validate the argument
                    if not cls.validate_type_spec(arg):
                        args_valid = False
                        break

                # For Dict, we need exactly two arguments: key and value types
                if container_type in ["dict[", "Dict["] and len(args) != ALLOWED_NUM_ARGS:
                    args_valid = False

            except Exception:
                # Invalid container syntax
                return False
            else:
                return args_valid

        # For custom types, try to resolve them
        resolved_type = cls.resolve_type(type_str)
        return resolved_type is not None

    @classmethod
    def validate_type_specs(cls, type_specs: list[str]) -> dict[str, bool]:
        """Validate multiple type strings against known types and proper syntax.

        Args:
            type_specs: List of type strings to validate

        Returns:
            Dictionary mapping each type string to a boolean indicating if it's valid
        """
        results = {}
        for type_str in type_specs:
            results[type_str] = cls.validate_type_spec(type_str)
        return results

    @classmethod
    def _parse_container_args(cls, type_str: str) -> list[str]:  # noqa: C901
        """Parse the arguments of a container type like List[int] or Dict[str, int].

        Args:
            type_str: String representation of a container type

        Returns:
            List of type strings for the container's arguments

        Raises:
            ContainerTypeError: If container type syntax is invalid
        """
        # Extract the content inside the square brackets
        try:
            start_idx = type_str.index("[")
        except ValueError as e:
            msg = f"Invalid container type format (missing opening bracket): '{type_str}'"
            raise ContainerTypeError(msg) from e

        # Find the matching closing bracket
        bracket_count = 1
        end_idx = None
        for i in range(start_idx + 1, len(type_str)):
            if type_str[i] == "[":
                bracket_count += 1
            elif type_str[i] == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i
                    break

        if bracket_count != 0 or end_idx is None:
            msg = f"Malformed container type (unbalanced brackets): '{type_str}'"
            raise ContainerTypeError(msg)

        content = type_str[start_idx + 1 : end_idx]

        # Split by commas, but respect nested containers
        args = []
        current_arg = ""
        bracket_count = 0

        for char in content:
            if char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
            elif char == "," and bracket_count == 0:
                args.append(current_arg.strip())
                current_arg = ""
                continue

            current_arg += char

        if current_arg:
            args.append(current_arg.strip())

        # Validate args
        if not args or "" in args:
            msg = f"Invalid container arguments (empty or missing): '{type_str}'"
            raise ContainerTypeError(msg)

        return args

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the type resolution cache."""
        instance = cls.get_instance()
        instance.type_cache = {}

    @classmethod
    def convert_to_type(cls, type_str: str) -> Any:  # noqa: PLR0911, C901, PLR0912, PLR0915 TODO(griptape): resolve
        """Convert a valid type string to its corresponding Python type object.

        Args:
            type_str: Type string to convert

        Returns:
            Python type object

        Raises:
            TypeValidationError: If the type string is invalid
            TypeConversionError: If conversion fails
        """
        instance = cls.get_instance()
        type_str = type_str.strip()

        # Handle Python 3.10+ pipe union types
        is_pipe_union, union_types = cls._handle_pipe_union(type_str)
        if is_pipe_union:
            # Convert each union type
            valid_arg_types = []
            for union_type in union_types:
                try:
                    arg_type = cls.convert_to_type(union_type)
                    valid_arg_types.append(arg_type)
                except Exception:
                    # Skip invalid types in union
                    logger.exception("Error converting union type %s", union_type)

            # Return the union type if we have valid arguments
            if valid_arg_types:
                if len(valid_arg_types) == 1:
                    return valid_arg_types[0]
                return typing.Union[tuple(valid_arg_types)]  # noqa: UP007
            msg = f"No valid types in union: '{type_str}'"
            raise TypeConversionError(msg)

        # Skip invalid types
        if not cls.validate_type_spec(type_str):
            msg = f"Invalid type specification: '{type_str}'"
            raise TypeValidationError(msg)

        # Handle primitive types
        if type_str in instance.builtin_types:
            return instance.builtin_types[type_str]

        # Handle container types
        for prefix in instance.container_types:
            if type_str.startswith(prefix):
                # For simple container types like List[int], we return the container type
                # For complex cases, we construct a type object where possible
                container_base = instance.container_types[prefix]

                # Special handling for common container types
                try:
                    args = cls._parse_container_args(type_str)

                    # Convert argument types recursively
                    arg_types = []
                    for arg in args:
                        try:
                            arg_type = cls.convert_to_type(arg)
                            arg_types.append(arg_type)
                        except Exception as e:
                            msg = f"Failed to convert argument '{arg}' in container type '{type_str}': {e!s}"
                            raise TypeConversionError(msg) from e

                    # Handle different container types
                    if prefix in ["List[", "list["]:
                        if all(arg_types):
                            return list[arg_types[0]]
                        return list

                    if prefix in ["Dict[", "dict["] and len(args) == ALLOWED_NUM_ARGS:
                        if all(arg_types):
                            return dict[arg_types[0], arg_types[1]]
                        return dict

                    if prefix in ["Set[", "set["]:
                        if all(arg_types):
                            return set[arg_types[0]]
                        return set

                    if prefix in ["Tuple[", "tuple["]:
                        if all(arg_types):
                            # Convert args to a tuple of types
                            return tuple[tuple(arg_types)]
                        return tuple

                    if prefix == "Optional[":
                        if arg_types[0]:
                            return typing.Optional[arg_types[0]]  # noqa: UP007
                        return typing.Optional

                    if prefix == "Union[":
                        valid_arg_types = [t for t in arg_types if t is not None]
                        if valid_arg_types:
                            if len(valid_arg_types) == 1:
                                return valid_arg_types[0]
                            # Create a Union type with all valid argument types
                            return typing.Union[tuple(valid_arg_types)]  # noqa: UP007
                        return typing.Union
                except Exception as e:
                    if isinstance(
                        e,
                        (TypeValidationError, TypeConversionError, ContainerTypeError),
                    ):
                        raise
                    # Fall back to the base container type on error
                    msg = f"Error processing container type '{type_str}': {e!s}"
                    raise ContainerTypeError(msg) from e
                else:
                    # Default to the base container type
                    return container_base

                break
        else:
            # Must be a custom type or a fully qualified type
            resolved_type = cls.resolve_type(type_str)
            if resolved_type is None:
                msg = f"Failed to resolve type: '{type_str}'"
                raise TypeResolutionError(msg)
            return resolved_type

    @classmethod
    def convert_to_types(cls, type_specs: list[str]) -> dict[str, Any]:
        """Convert valid type strings to their corresponding Python type objects.

        This method converts type strings to actual Python type objects.

        Args:
            type_specs: List of type strings to convert

        Returns:
            Dictionary mapping each type string to its Python type object

        Raises:
            TypeValidationError: If any type string is invalid
            TypeConversionError: If conversion fails
        """
        # Initialize result dictionary
        type_objects = {}

        for type_str in type_specs:
            try:
                type_objects[type_str] = cls.convert_to_type(type_str)
            except Exception as e:
                # Include the problematic type in the error message
                msg = f"Error converting '{type_str}': {e!s}"
                raise type(e)(msg) from e

        return type_objects

    @classmethod
    def is_instance(cls, value: Any, type_spec: str) -> bool:  # noqa: PLR0911, C901, PLR0912 TODO(griptape): resolve
        """Check if a value is an instance of the specified type.

        Args:
            value: The value to check
            type_spec: The type specification string

        Returns:
            True if the value is an instance of the specified type, False otherwise

        Raises:
            TypeValidationError: If the type string is invalid
            TypeConversionError: If conversion fails
        """
        # Handle Python 3.10+ pipe union types
        is_pipe_union, union_types = cls._handle_pipe_union(type_spec)
        if is_pipe_union:
            # Check if value is instance of any type in the union
            for union_type in union_types:
                try:
                    if cls.is_instance(value, union_type):
                        return True
                except Exception:
                    logger.exception("Error checking union type %s", union_type)
                    # Skip invalid types in the union
                    continue
            return False

        # Convert the type string to a Python type object
        type_obj = cls.convert_to_type(type_spec)

        # Special handling for container types with typing annotations
        if hasattr(type_obj, "__origin__"):
            origin = type_obj.__origin__

            # Handle Optional (Union[T, None])
            if origin is typing.Union:
                # Check if value is instance of any of the types in the Union
                for arg in type_obj.__args__:
                    if arg is type(None) and value is None:
                        return True
                    try:
                        if isinstance(value, arg):
                            return True
                    except TypeError:
                        # Some complex types might not work with isinstance
                        pass
                return False

            # Handle List, Dict, Set, Tuple
            if origin in (list, list):
                if not isinstance(value, list):
                    return False
                # Empty list passes any List type validation
                if not value:
                    return True
                # Check if all items in the list match the element type
                elem_type = type_obj.__args__[0]
                return all(isinstance(item, elem_type) for item in value)

            if origin in (dict, dict):
                if not isinstance(value, dict):
                    return False
                # Empty dict passes any Dict type validation
                if not value:
                    return True
                # Check if all keys and values match their respective types
                key_type, val_type = type_obj.__args__
                return all(isinstance(k, key_type) and isinstance(v, val_type) for k, v in value.items())

            if origin in (set, set):
                if not isinstance(value, set):
                    return False
                # Empty set passes any Set type validation
                if not value:
                    return True
                # Check if all items in the set match the element type
                elem_type = type_obj.__args__[0]
                return all(isinstance(item, elem_type) for item in value)

            if origin in (tuple, tuple):
                if not isinstance(value, tuple):
                    return False
                # Check if tuple elements match their types
                if len(value) != len(type_obj.__args__):
                    return False
                return all(isinstance(v, t) for v, t in zip(value, type_obj.__args__, strict=False))

            # For other container types, fall back to basic isinstance
            return isinstance(value, origin)

        # Standard isinstance check for non-container types
        return isinstance(value, type_obj)

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
            logger.exception("Error serializing object: %s", obj)
        else:
            return obj_dict
        try:
            import pickle

            pickle.dumps(obj)
        except Exception:
            if hasattr(obj, "id"):
                return {f"{type(obj).__name__} Object: {obj.id}"}
        else:
            return obj
        return f"{type(obj).__name__} Object"
