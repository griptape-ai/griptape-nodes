from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterator

T = TypeVar("T")  # Generic type for component values


@dataclass
class PropertyArray(Generic[T]):
    components: list[T]
    _aliases: dict[str, str] = field(default_factory=dict)

    def __init__(self, *args: T) -> None:
        self.components = list(args)
        self._aliases = {}

        # Handle any dimension-specific default names (x, y, z, w)
        self._default_names = ["x", "y", "z", "w"]
        # Limit to actual dimensions
        self._default_names = self._default_names[: len(args)]

    def set_aliases(self, **kwargs) -> PropertyArray[T]:
        """Set custom aliases for components.

        Example: vec.set_aliases(x='width', y='height').
        """
        self._aliases.update(kwargs)
        return self

    # Add sequence protocol methods
    def __getitem__(self, index) -> T:
        return self.components[index]

    def __setitem__(self, index, value) -> None:
        self.components[index] = value

    def __len__(self) -> int:
        return len(self.components)

    def __iter__(self) -> Iterator[T]:
        return iter(self.components)

    def __getattr__(self, name) -> T:
        # Check if it's an alias
        if name in self._aliases:
            original_name = self._aliases[name]
            if original_name in self._default_names:
                index = self._default_names.index(original_name)
                return self.components[index]

        # Check if it's a default name
        if name in self._default_names:
            index = self._default_names.index(name)
            return self.components[index]

        # Check if it's a custom name that was set as an alias
        for default_name, alias in self._aliases.items():
            if alias == name and default_name in self._default_names:
                index = self._default_names.index(default_name)
                return self.components[index]

        msg = f"'{self.__class__.__name__}' has no attribute '{name}'"
        raise AttributeError(msg)

    def __setattr__(self, name, value) -> None:
        # Handle special attributes normally
        if name in ["components", "_aliases", "_default_names"]:
            super().__setattr__(name, value)
            return

        # Check if it's a default name
        if hasattr(self, "_default_names") and name in self._default_names:
            index = self._default_names.index(name)
            if 0 <= index < len(self.components):
                self.components[index] = value
                return

        # Check if it's an alias
        if hasattr(self, "_aliases") and name in self._aliases.values():
            # Find which default name this is an alias for
            for default_name, alias in self._aliases.items():
                if alias == name and default_name in self._default_names:
                    index = self._default_names.index(default_name)
                    self.components[index] = value
                    return

        super().__setattr__(name, value)

    def __repr__(self) -> str:
        components_str = ", ".join(str(c) for c in self.components)
        return f"{self.__class__.__name__}({components_str})"

    def to_dict(self) -> dict:
        """Convert PropertyArray to a dictionary for serialization."""
        # Convert components, handling Enum values appropriately
        serialized_components = []
        for comp in self.components:
            if isinstance(comp, Enum):
                serialized_components.append(comp.name)  # Use name for enums
            else:
                serialized_components.append(comp)

        result = {"components": serialized_components, "aliases": self._aliases}

        # Include named components
        for i, name in enumerate(self._default_names):
            if i < len(self.components):
                comp = self.components[i]
                if isinstance(comp, Enum):
                    result[name] = comp.name
                else:
                    result[name] = comp

        return result

    @classmethod
    def from_dict(cls, data: dict) -> PropertyArray[T]:
        """Create a PropertyArray from a dictionary."""
        # Extract components
        components = data.get("components", [])

        # Create instance
        instance = cls(*components)

        # Set aliases if provided
        aliases = data.get("aliases", {})
        if aliases:
            instance.set_aliases(**aliases)

        return instance


class EnumPropertyArray(PropertyArray[Enum]):
    """Base class for property arrays of Enum values."""

    # List of enum types for each component
    enum_types: ClassVar[list[type[Enum] | None]] = []

    def _process_enum_value(self, value, index) -> str | float | int:
        """Convert string to enum value if needed, using the enum type at the specified index."""
        if not self.enum_types or index >= len(self.enum_types) or self.enum_types[index] is None:
            return value

        enum_type = self.enum_types[index]

        if isinstance(value, enum_type):
            return value

        if isinstance(value, str):
            # Try to convert string to enum value
            try:
                # Try by name first
                return enum_type[value]
            except (KeyError, TypeError):
                # Try by value
                for enum_val in enum_type:
                    if enum_val.value == value:
                        return enum_val
        elif isinstance(value, (int, float)) and any(isinstance(e.value, (int, float)) for e in enum_type):
            # Try to match by value for numeric enums
            for enum_val in enum_type:
                if enum_val.value == value:
                    return enum_val

        return value

    def __init__(self, *args, **kwargs) -> None:
        # Process args to convert strings/values to enum values if possible
        processed_args = []
        for i, arg in enumerate(args):
            processed_args.append(self._process_enum_value(arg, i))

        super().__init__(*processed_args, **kwargs)

    @classmethod
    def from_dict(cls, data: dict) -> EnumPropertyArray:
        """Create a EnumPropertyArray from a dictionary, converting values to enum values."""
        # Get the components
        components = data.get("components", [])

        # Create a temporary instance to access enum_types and _process_enum_value
        temp_instance = cls()

        # Process components to convert values to enum values
        processed_components = [temp_instance._process_enum_value(comp, i) for i, comp in enumerate(components)]

        # Create the real instance
        instance = cls(*processed_components)

        # Set aliases if provided
        aliases = data.get("aliases", {})
        if aliases:
            instance.set_aliases(**aliases)

        return instance


# Create specialized types for convenience
class Int2(PropertyArray[int]):
    def __init__(self, x=0, y=0) -> None:
        super().__init__(x, y)


class Int3(PropertyArray[int]):
    def __init__(self, x=0, y=0, z=0) -> None:
        super().__init__(x, y, z)


class Int4(PropertyArray[int]):
    def __init__(self, x=0, y=0, z=0, w=0) -> None:
        super().__init__(x, y, z, w)


class Float2(PropertyArray[float]):
    def __init__(self, x=0.0, y=0.0) -> None:
        super().__init__(x, y)


class Float3(PropertyArray[float]):
    def __init__(self, x=0.0, y=0.0, z=0.0) -> None:
        super().__init__(x, y, z)


class Float4(PropertyArray[float]):
    def __init__(self, x=0.0, y=0.0, z=0.0, w=0.0) -> None:
        super().__init__(x, y, z, w)


class Str2(PropertyArray[str]):
    def __init__(self, x="", y="") -> None:
        super().__init__(x, y)


class Str3(PropertyArray[str]):
    def __init__(self, x="", y="", z="") -> None:
        super().__init__(x, y, z)


class Str4(PropertyArray[str]):
    def __init__(self, x="", y="", z="", w="") -> None:
        super().__init__(x, y, z, w)


class Enum2(EnumPropertyArray):
    """A 2D property array for Enum values."""

    enum_types: ClassVar[list] = [None, None]  # Placeholder, to be set by subclassing

    def __init__(self, x=None, y=None) -> None:
        # Set defaults based on enum types
        if x is None and self.enum_types[0] is not None:
            enum_values = list(self.enum_types[0])
            if enum_values:
                x = enum_values[0]

        if y is None and self.enum_types[1] is not None:
            enum_values = list(self.enum_types[1])
            if enum_values:
                y = enum_values[0]

        super().__init__(x, y)


class Enum3(EnumPropertyArray):
    """A 3D property array for Enum values."""

    enum_types: ClassVar[list] = [None, None, None]

    def __init__(self, x=None, y=None, z=None) -> None:
        # Set defaults based on enum types
        defaults: list = [None, None, None]

        for i, enum_type in enumerate([self.enum_types[0], self.enum_types[1], self.enum_types[2]]):
            if enum_type is not None:
                enum_values = list(enum_type)
                if enum_values:
                    defaults[i] = enum_values[0]

        if x is None:
            x = defaults[0]
        if y is None:
            y = defaults[1]
        if z is None:
            z = defaults[2]

        super().__init__(x, y, z)


class Enum4(EnumPropertyArray):
    """A 4D property array for Enum values."""

    enum_types: ClassVar[list] = [None, None, None, None]

    def __init__(self, x=None, y=None, z=None, w=None) -> None:
        # Set defaults based on enum types
        defaults: list = [None, None, None, None]

        for i, enum_type in enumerate(self.enum_types):
            if enum_type is not None:
                enum_values = list(enum_type)
                if enum_values:
                    defaults[i] = enum_values[0]

        if x is None:
            x = defaults[0]
        if y is None:
            y = defaults[1]
        if z is None:
            z = defaults[2]
        if w is None:
            w = defaults[3]

        super().__init__(x, y, z, w)


# Helper function to create Enum arrays for specific enum types
def create_enum_array(enum_types, dimension=None) -> type:
    """Create a EnumPropertyArray subclass with the specified enum types.

    Args:
        enum_types: List of Enum classes, one for each component
        dimension: Optional dimension (if not provided, derived from len(enum_types))

    Returns:
        A subclass of EnumPropertyArray configured for the specified enum types
    """
    if dimension is None:
        dimension = len(enum_types)
    # Ensure enum_types matches the requested dimension
    elif len(enum_types) < dimension:
        # Pad with None for unspecified types
        enum_types = list(enum_types) + [None] * (dimension - len(enum_types))
    elif len(enum_types) > dimension:
        # Truncate if too many types provided
        enum_types = enum_types[:dimension]

    if dimension == 2:  # noqa: PLR2004
        base_class = Enum2
    elif dimension == 3:  # noqa: PLR2004
        base_class = Enum3
    elif dimension == 4:  # noqa: PLR2004
        base_class = Enum4
    else:
        msg = f"Unsupported dimension: {dimension}"
        raise ValueError(msg)

    # Generate a descriptive class name
    type_names = []
    for et in enum_types:
        if et is None:
            type_names.append("None")
        else:
            type_names.append(et.__name__)

    class_name = f"Enum{dimension}_{'-'.join(type_names)}"

    # Create a new class with the enum_types set
    return type(class_name, (base_class,), {"enum_types": list(enum_types)})
