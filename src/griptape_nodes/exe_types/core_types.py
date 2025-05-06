from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Self, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

T = TypeVar("T", bound="Parameter")
N = TypeVar("N", bound="BaseNodeElement")


# Types of Modes provided for Parameters
class ParameterMode(Enum):
    OUTPUT = auto()
    INPUT = auto()
    PROPERTY = auto()


class ParameterTypeBuiltin(Enum):
    STR = "str"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ANY = "any"
    NONE = "none"
    CONTROL_TYPE = "parametercontroltype"
    ALL = "all"


class ParameterType:
    class KeyValueTypePair(NamedTuple):
        """A named tuple for storing a pair of types for key-value parameters.

        Fields:
            key_type: The type of the key
            value_type: The type of the value
        """

        key_type: str
        value_type: str

    _builtin_aliases: ClassVar[dict] = {
        "str": ParameterTypeBuiltin.STR,
        "string": ParameterTypeBuiltin.STR,
        "bool": ParameterTypeBuiltin.BOOL,
        "boolean": ParameterTypeBuiltin.BOOL,
        "int": ParameterTypeBuiltin.INT,
        "float": ParameterTypeBuiltin.FLOAT,
        "any": ParameterTypeBuiltin.ANY,
        "none": ParameterTypeBuiltin.NONE,
        "parametercontroltype": ParameterTypeBuiltin.CONTROL_TYPE,
        "all": ParameterTypeBuiltin.ALL,
    }

    @staticmethod
    def attempt_get_builtin(type_name: str) -> ParameterTypeBuiltin | None:
        ret_val = ParameterType._builtin_aliases.get(type_name.lower())
        return ret_val

    @staticmethod
    def are_types_compatible(source_type: str | None, target_type: str | None) -> bool:
        if source_type is None or target_type is None:
            return False

        ret_val = False
        source_type_lower = source_type.lower()
        target_type_lower = target_type.lower()

        # If either are None, bail.
        if ParameterTypeBuiltin.NONE.value in (source_type_lower, target_type_lower):
            ret_val = False
        elif target_type_lower == ParameterTypeBuiltin.ANY.value:
            # If the TARGET accepts Any, we're good. Not always true the other way 'round.
            ret_val = True
        else:
            # Do a compare.
            ret_val = source_type_lower == target_type_lower

        return ret_val

    @staticmethod
    def parse_kv_type_pair(type_str: str) -> KeyValueTypePair | None:  # noqa: C901
        """Parse a string that potentially defines a Key-Value Type Pair.

        Args:
            type_str: A string like "[str, int]" or "[dict[str, bool], list[float]]"

        Returns:
            A KeyValueTypePair object if valid KV pair format, or None if not a KV pair

        Raises:
            ValueError: If the string appears to be a KV pair but is malformed
        """
        # Remove any whitespace
        type_str = type_str.strip()

        # Check if it starts with '[' and ends with ']'
        if not (type_str.startswith("[") and type_str.endswith("]")):
            return None  # Not a KV pair, just a regular type

        # Remove the outer brackets
        inner_content = type_str[1:-1].strip()

        # Now we need to find the comma that separates key type from value type
        # This is tricky because we might have nested structures with commas

        # Keep track of nesting level with different brackets
        bracket_stack = []
        comma_positions = []

        for i, char in enumerate(inner_content):
            if char in "[{(":
                bracket_stack.append(char)
            elif char in "]})":
                if bracket_stack:  # Ensure stack isn't empty
                    bracket_stack.pop()
                else:
                    # Unmatched closing bracket
                    err_str = f"Unmatched closing bracket at position {i} in '{type_str}'."
                    raise ValueError(err_str)
            elif char == "," and not bracket_stack:
                # This is a top-level comma
                comma_positions.append(i)

        # Check for unclosed brackets
        if bracket_stack:
            err_str = f"Unclosed brackets in '{type_str}'."
            raise ValueError(err_str)

        # We should have exactly one top-level comma
        if len(comma_positions) != 1:
            err_str = (
                f"Missing comma separator in '{type_str}'."
                if len(comma_positions) == 0
                else f"Too many comma separators in '{type_str}'."
            )
            raise ValueError(err_str)

        # Split at the comma
        key_type = inner_content[: comma_positions[0]].strip()
        value_type = inner_content[comma_positions[0] + 1 :].strip()

        # Validate that both parts are not empty
        if not key_type:
            err_str = f"Empty key type in '{type_str}'."
            raise ValueError(err_str)
        if not value_type:
            err_str = f"Empty value type in '{type_str}'."
            raise ValueError(err_str)

        return ParameterType.KeyValueTypePair(key_type=key_type, value_type=value_type)


@dataclass(kw_only=True)
class BaseNodeElement:
    element_id: str = field(default_factory=lambda: str(uuid.uuid4().hex))
    element_type: str = field(default_factory=lambda: BaseNodeElement.__name__)

    _children: list[BaseNodeElement] = field(default_factory=list)
    _stack: ClassVar[list[BaseNodeElement]] = []
    _parent: BaseNodeElement | None = field(default=None)

    @property
    def children(self) -> list[BaseNodeElement]:
        return self._children

    def __post_init__(self) -> None:
        # If there's currently an active element, add this new element as a child
        current = BaseNodeElement.get_current()
        if current is not None:
            current.add_child(self)

    def __enter__(self) -> Self:
        # Push this element onto the global stack
        BaseNodeElement._stack.append(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        # Pop this element off the global stack
        popped = BaseNodeElement._stack.pop()
        if popped is not self:
            msg = f"Expected to pop {self}, but got {popped}"
            raise RuntimeError(msg)

    def __repr__(self) -> str:
        return f"BaseNodeElement({self.children=})"

    def to_dict(self) -> dict[str, Any]:
        """Returns a nested dictionary representation of this node and its children.

        Example:
            {
              "element_id": "container-1",
              "element_type": "ParameterGroup",
              "group_name": "Group 1",
              "children": [
                {
                    "element_id": "A",
                    "element_type": "Parameter",
                    "children": []
                },
                ...
              ]
            }
        """
        return {
            "element_id": self.element_id,
            "element_type": self.__class__.__name__,
            "children": [child.to_dict() for child in self._children],
        }

    def add_child(self, child: BaseNodeElement) -> None:
        if child._parent is not None:
            child._parent.remove_child(child)
        child._parent = self
        self._children.append(child)

    def remove_child(self, child: BaseNodeElement | str) -> None:
        ui_elements: list[BaseNodeElement] = [self]
        for ui_element in ui_elements:
            if child in ui_element._children:
                child._parent = None
                ui_element._children.remove(child)
                break
            ui_elements.extend(ui_element._children)

    def find_element_by_id(self, element_id: str) -> BaseNodeElement | None:
        if self.element_id == element_id:
            return self

        for child in self._children:
            found = child.find_element_by_id(element_id)
            if found is not None:
                return found
        return None

    def find_elements_by_type(self, element_type: type[N], *, find_recursively: bool = True) -> list[N]:
        """Returns a list of child elements that are instances of type specified. Optionally do this recursively."""
        elements: list[N] = []
        for child in self._children:
            if isinstance(child, element_type):
                elements.append(child)
            if find_recursively:
                elements.extend(child.find_elements_by_type(element_type))
        return elements

    @classmethod
    def get_current(cls) -> BaseNodeElement | None:
        """Return the element on top of the stack, or None if no active element."""
        return cls._stack[-1] if cls._stack else None


@dataclass(kw_only=True)
class ParameterGroup(BaseNodeElement):
    """UI element for a group of parameters."""

    ui_options: dict = field(default_factory=dict)
    group_name: str

    def to_dict(self) -> dict[str, Any]:
        """Returns a nested dictionary representation of this node and its children.

        Example:
            {
              "element_id": "container-1",
              "element_type": "ParameterGroup",
              "group_name": "Group 1",
              "children": [
                {
                    "element_id": "A",
                    "element_type": "Parameter",
                    "children": []
                },
                ...
              ]
            }
        """
        # Get the parent's version first.
        our_dict = super().to_dict()
        # Add in our deltas.
        our_dict["group_name"] = self.group_name
        our_dict["ui_options"] = self.ui_options
        return our_dict

    def equals(self, other: ParameterGroup) -> dict:
        self_dict = {"group_name": self.group_name, "ui_options": self.ui_options}
        other_dict = {"group_name": other.group_name, "ui_options": other.ui_options}
        if self_dict == other_dict:
            return {}
        differences = {}
        for key, self_value in self_dict.items():
            other_value = other_dict.get(key)
            if self_value != other_value:
                differences[key] = other_value
        return differences


# TODO: https://github.com/griptape-ai/griptape-nodes/issues/856
class ParameterBase(BaseNodeElement, ABC):
    name: str  # must be unique from other parameters in Node

    @property
    @abstractmethod
    def tooltip(self) -> str | list[dict]:
        """Get the default tooltip for this Parameter-like object.

        Returns:
            str | list[dict]: Either the explicit tooltip string or a list of dicts for special UI handling.
        """

    @tooltip.setter
    @abstractmethod
    def tooltip(self, value: str | list[dict]) -> None:
        pass

    @abstractmethod
    def get_default_value(self) -> Any:
        """Get the default value that should be assigned to this Parameter-like object.

        Returns:
            Any: The default value to assign when initialized or reset.
        """

    @abstractmethod
    def get_input_types(self) -> list[str] | None:
        """Get the list of input types this Parameter-like object accepts, or None if it doesn't accept any.

        Returns:
            list[str] | None: List of user-defined types supported.
        """

    @abstractmethod
    def get_output_type(self) -> str | None:
        """Get the output type this Parameter-like object emits, or None if it doesn't output.

        Returns:
            str | None: User-defined type output.
        """

    @abstractmethod
    def get_type(self) -> str | None:
        pass

    @abstractmethod
    def get_tooltip_as_input(self) -> str | list[dict] | None:
        pass


class Parameter(BaseNodeElement):
    # This is the list of types that the Parameter can accept, either externally or when internally treated as a property.
    # Today, we can accept multiple types for input, but only a single output type.
    tooltip: str | list[dict]  # Default tooltip, can be string or list of dicts
    default_value: Any = None
    _input_types: list[str] | None
    _output_type: str | None
    _type: str | None
    tooltip_as_input: str | list[dict] | None = None
    tooltip_as_property: str | list[dict] | None = None
    tooltip_as_output: str | list[dict] | None = None
    settable: bool = True
    user_defined: bool = False
    allowed_modes: set = field(
        default_factory=lambda: {
            ParameterMode.OUTPUT,
            ParameterMode.INPUT,
            ParameterMode.PROPERTY,
        }
    )
    _converters: list[Callable[[Any], Any]]
    _validators: list[Callable[[Parameter, Any], None]]
    _ui_options: dict
    next: Parameter | None = None
    prev: Parameter | None = None
    parent_container_name: str | None = None

    def __init__(  # noqa: PLR0913,PLR0912
        self,
        name: str,
        tooltip: str | list[dict],
        type: str | None = None,  # noqa: A002
        input_types: list[str] | None = None,
        output_type: str | None = None,
        default_value: Any = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,  # We are going to make these children.
        ui_options: dict | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
        parent_container_name: str | None = None,
    ):
        if not element_id:
            element_id = str(uuid.uuid4().hex)
        if not element_type:
            element_type = BaseNodeElement.__name__
        super().__init__(element_id=element_id, element_type=element_type)
        self.name = name
        self.tooltip = tooltip
        self.default_value = default_value
        self.tooltip_as_input = tooltip_as_input
        self.tooltip_as_property = tooltip_as_property
        self.tooltip_as_output = tooltip_as_output
        self.settable = settable
        self.user_defined = user_defined
        if allowed_modes is None:
            self.allowed_modes = {ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY}
        else:
            self.allowed_modes = allowed_modes

        if converters is None:
            self._converters = []
        else:
            self._converters = converters

        if validators is None:
            self._validators = []
        else:
            self._validators = validators
        if ui_options is None:
            self._ui_options = {}
        else:
            self._ui_options = ui_options
        if traits:
            for trait in traits:
                if not isinstance(trait, Trait):
                    created = trait()
                else:
                    created = trait
                # Add a trait as a child
                # UI options are now traits! sorry!
                self.add_child(created)
        self.type = type
        self.input_types = input_types
        self.output_type = output_type
        self.parent_container_name = parent_container_name

    def to_dict(self) -> dict[str, Any]:
        """Returns a nested dictionary representation of this node and its children."""
        # Get the parent's version first.
        our_dict = super().to_dict()
        # Add in our deltas.
        our_dict["name"] = self.name
        our_dict["type"] = self.type
        our_dict["input_types"] = self.input_types
        our_dict["output_type"] = self.output_type
        our_dict["default_value"] = self.default_value
        our_dict["tooltip"] = self.tooltip
        our_dict["tooltip_as_input"] = self.tooltip_as_input
        our_dict["tooltip_as_output"] = self.tooltip_as_output
        our_dict["tooltip_as_property"] = self.tooltip_as_property

        our_dict["is_user_defined"] = self.user_defined
        our_dict["ui_options"] = self.ui_options

        # Let's bundle up the mode details.
        allows_input = ParameterMode.INPUT in self.allowed_modes
        allows_property = ParameterMode.PROPERTY in self.allowed_modes
        allows_output = ParameterMode.OUTPUT in self.allowed_modes
        our_dict["mode_allowed_input"] = allows_input
        our_dict["mode_allowed_property"] = allows_property
        our_dict["mode_allowed_output"] = allows_output
        our_dict["parent_container_name"] = self.parent_container_name

        return our_dict

    @property
    def type(self) -> str:
        return self._custom_getter_for_property_type()

    def _custom_getter_for_property_type(self) -> str:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if self._type:
            return self._type
        if self._input_types:
            return self._input_types[0]
        if self._output_type:
            return self._output_type
        return ParameterTypeBuiltin.STR.value

    @type.setter
    def type(self, value: str | None) -> None:
        self._custom_setter_for_property_type(value)

    def _custom_setter_for_property_type(self, value: str | None) -> None:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if value is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(value)
            if builtin is not None:
                self._type = builtin.value
            else:
                self._type = value
            return
        self._type = None

    @property
    def converters(self) -> list[Callable[[Any], Any]]:
        converters = []
        traits = self.find_elements_by_type(Trait)
        for trait in traits:
            converters += trait.converters_for_trait()
        converters += self._converters
        return converters

    @property
    def validators(self) -> list[Callable[[Parameter, Any], None]]:
        validators = []
        traits = self.find_elements_by_type(Trait)  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/857
        for trait in traits:
            validators += trait.validators_for_trait()
        validators += self._validators
        return validators

    @property
    def ui_options(self) -> dict:
        ui_options = {}
        traits = self.find_elements_by_type(Trait)
        for trait in traits:
            ui_options = ui_options | trait.ui_options_for_trait()
        ui_options = ui_options | self._ui_options
        if self._parent is not None and isinstance(self._parent, ParameterGroup):
            ui_options = ui_options | self._parent.ui_options
        return ui_options

    @ui_options.setter
    def ui_options(self, value: dict) -> None:
        self._ui_options = value

    @property
    def input_types(self) -> list[str]:
        return self._custom_getter_for_property_input_types()

    def _custom_getter_for_property_input_types(self) -> list[str]:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if self._input_types:
            return self._input_types
        if self._type:
            return [self._type]
        if self._output_type:
            return [self._output_type]
        return [ParameterTypeBuiltin.STR.value]

    @input_types.setter
    def input_types(self, value: list[str] | None) -> None:
        self._custom_setter_for_property_input_types(value)

    def _custom_setter_for_property_input_types(self, value: list[str] | None) -> None:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if value is None:
            self._input_types = None
        else:
            self._input_types = []
            for new_type in value:
                # See if it's an alias to a builtin first.
                builtin = ParameterType.attempt_get_builtin(new_type)
                if builtin is not None:
                    self._input_types.append(builtin.value)
                else:
                    self._input_types.append(new_type)

    @property
    def output_type(self) -> str:
        return self._custom_getter_for_property_output_type()

    def _custom_getter_for_property_output_type(self) -> str:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if self._output_type:
            # If an output type was specified, use that.
            return self._output_type
        if self._type:
            # Otherwise, see if we have a list of input_types. If so, use the first one.
            return self._type

        # Otherwise, see if we have a list of input_types. If so, use the first one.
        if self._input_types:
            return self._input_types[0]
        # Otherwise, return a string.
        return ParameterTypeBuiltin.STR.value

    @output_type.setter
    def output_type(self, value: str | None) -> None:
        self._custom_setter_for_property_output_type(value)

    def _custom_setter_for_property_output_type(self, value: str | None) -> None:
        """Derived classes may override this. Overriding property getter/setters is fraught with peril."""
        if value is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(value)
            if builtin is not None:
                self._output_type = builtin.value
            else:
                self._output_type = value
            return
        self._output_type = None

    def add_trait(self, trait: type[Trait] | Trait) -> None:
        if not isinstance(trait, Trait):
            created = trait()
        else:
            created = trait
        self.add_child(created)

    def remove_trait(self, trait_type: BaseNodeElement) -> None:
        # You are NOT ALLOWED TO ADD DUPLICATE TRAITS (kate)
        self.remove_child(trait_type)

    def is_incoming_type_allowed(self, incoming_type: str | None) -> bool:
        if incoming_type is None:
            return False

        if incoming_type.lower() == ParameterTypeBuiltin.ALL.value:
            return True

        ret_val = False

        if self.input_types:
            for test_type in self.input_types:
                if ParameterType.are_types_compatible(source_type=incoming_type, target_type=test_type):
                    ret_val = True
                    break
        else:
            # Customer feedback was to treat as a string by default.
            ret_val = ParameterType.are_types_compatible(
                source_type=incoming_type, target_type=ParameterTypeBuiltin.STR.value
            )

        return ret_val

    def is_outgoing_type_allowed(self, target_type: str | None) -> bool:
        return ParameterType.are_types_compatible(source_type=self.output_type, target_type=target_type)

    def set_default_value(self, value: Any) -> None:
        self.default_value = value

    def get_mode(self) -> set:
        return self.allowed_modes

    def add_mode(self, mode: ParameterMode) -> None:
        self.allowed_modes.add(mode)

    def remove_mode(self, mode: ParameterMode) -> None:
        self.allowed_modes.remove(mode)

    def copy(self) -> Parameter:
        param = deepcopy(self)
        param.next = None
        param.prev = None
        return param

    def check_list(self, self_value: Any, other_value: Any, differences: dict, key: Any) -> None:
        # Convert both to lists for index-based iteration
        self_list = list(self_value)
        other_list = list(other_value)
        # Check if they have different lengths
        if len(self_list) != len(other_list):
            differences[key] = other_value
            return
        # Compare each element
        list_differences = False
        for i, item in enumerate(self_list):
            if i >= len(other_list):
                list_differences = True
                break
            # If the element is a Parameter, use its equals method
            if isinstance(item, Parameter) and isinstance(other_list[i], Parameter):
                if item.equals(other_list[i]):  # If there are differences
                    list_differences = True
                    break
            elif isinstance(item, BaseNodeElement) and isinstance(other_list[i], BaseNodeElement):
                if item != other_list[i]:
                    list_differences = True
                    break
            # Otherwise use direct comparison
            elif item != other_list[i]:
                list_differences = True
                break
        if list_differences:
            differences[key] = other_value

    # intentionally not overwriting __eq__ because I want to return a dict not true or false
    def equals(self, other: Parameter) -> dict:
        self_dict = self.to_dict().copy()
        other_dict = other.to_dict().copy()
        self_dict.pop("next", None)
        self_dict.pop("prev", None)
        self_dict.pop("element_id", None)
        other_dict.pop("next", None)
        other_dict.pop("element_id", None)
        other_dict.pop("prev", None)
        if self_dict == other_dict:
            return {}
        differences = {}
        for key, self_value in self_dict.items():
            other_value = other_dict.get(key, None)
            # handle children here
            if isinstance(self_value, BaseNodeElement) and isinstance(other_value, BaseNodeElement):
                if self_value != other_value:
                    differences[key] = other_value
            elif isinstance(self_value, (list, set)) and isinstance(other_value, (list, set)):
                self.check_list(self_value, other_value, differences, key)
            elif self_value != other_value:
                differences[key] = other_value
        return differences


# Convenience classes to reduce boilerplate in node definitions
class ControlParameter(Parameter, ABC):
    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | list[dict],
        input_types: list[str] | None = None,
        output_type: str | None = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        user_defined: bool = False,
    ):
        # Call parent with a few explicit tweaks.
        super().__init__(
            type=ParameterTypeBuiltin.CONTROL_TYPE.value,
            default_value=None,
            settable=False,
            name=name,
            tooltip=tooltip,
            input_types=input_types,
            output_type=output_type,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            traits=traits,
            converters=converters,
            validators=validators,
            user_defined=user_defined,
            element_type=self.__class__.__name__,
        )


class ControlParameterInput(ControlParameter):
    def __init__(  # noqa: PLR0913
        self,
        tooltip: str | list[dict] = "Connection from previous node in the execution chain",
        name: str = "exec_in",
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        user_defined: bool = False,
    ):
        allowed_modes = {ParameterMode.INPUT}
        input_types = [ParameterTypeBuiltin.CONTROL_TYPE.value]

        # Call parent with a few explicit tweaks.
        super().__init__(
            name=name,
            tooltip=tooltip,
            input_types=input_types,
            output_type=None,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            traits=traits,
            converters=converters,
            validators=validators,
            user_defined=user_defined,
        )


class ControlParameterOutput(ControlParameter):
    def __init__(  # noqa: PLR0913
        self,
        tooltip: str | list[dict] = "Connection to the next node in the execution chain",
        name: str = "exec_out",
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        user_defined: bool = False,
    ):
        allowed_modes = {ParameterMode.OUTPUT}
        output_type = ParameterTypeBuiltin.CONTROL_TYPE.value

        # Call parent with a few explicit tweaks.
        super().__init__(
            name=name,
            tooltip=tooltip,
            input_types=None,
            output_type=output_type,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            traits=traits,
            converters=converters,
            validators=validators,
            user_defined=user_defined,
        )


class ParameterContainer(Parameter, ABC):
    """Class managing a container (list/dict/tuple/etc.) of Parameters.

    It is, itself, a Parameter (so it can be the target of compatible Container connections, etc.)
    But it also has the ability to own and manage children and make them accessible by keys, etc.
    """

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | list[dict],
        type: str | None = None,  # noqa: A002
        input_types: list[str] | None = None,
        output_type: str | None = None,
        default_value: Any = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
    ):
        super().__init__(
            name=name,
            tooltip=tooltip,
            type=type,
            input_types=input_types,
            output_type=output_type,
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
            traits=traits,
            converters=converters,
            validators=validators,
            settable=settable,
            user_defined=user_defined,
            element_id=element_id,
            element_type=element_type,
        )

    @abstractmethod
    def add_child_parameter(self) -> Parameter:
        pass


class ParameterList(ParameterContainer):
    _original_traits: set[Trait.__class__ | Trait]

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | list[dict],
        type: str | None = None,  # noqa: A002
        input_types: list[str] | None = None,
        output_type: str | None = None,
        default_value: Any = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
    ):
        if traits:
            self._original_traits = traits
        else:
            self._original_traits = set()

        # Remember: we're a Parameter, too, just like everybody else.
        super().__init__(
            name=name,
            tooltip=tooltip,
            type=type,
            input_types=input_types,
            output_type=output_type,
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
            traits=traits,
            converters=converters,
            validators=validators,
            settable=settable,
            user_defined=user_defined,
            element_id=element_id,
            element_type=element_type,
        )

    def _custom_getter_for_property_type(self) -> str:
        base_type = super()._custom_getter_for_property_type()
        result = f"list[{base_type}]"
        return result

    def _custom_getter_for_property_input_types(self) -> list[str]:
        # For every valid input type, also accept a list variant of that for the CONTAINER Parameter only.
        # Children still use the input types given to them.
        base_input_types = super()._custom_getter_for_property_input_types()
        result = []
        for base_input_type in base_input_types:
            container_variant = f"list[{base_input_type}]"
            result.append(container_variant)

        return result

    def _custom_getter_for_property_output_type(self) -> str:
        base_type = super()._custom_getter_for_property_output_type()
        result = f"list[{base_type}]"
        return result

    def __len__(self) -> int:
        # Returns the number of child Parameters. Just do the top level.
        param_children = self.find_elements_by_type(element_type=Parameter, find_recursively=False)
        return len(param_children)

    def __getitem__(self, key: int) -> Parameter:
        count = 0
        for child in self._children:
            if isinstance(child, Parameter):
                if count == key:
                    # Found it.
                    return child
                count += 1

        # If we fell out of the for loop, we had a bad value.
        err_str = f"Attempted to get a Parameter List index {key}, which was out of range."
        raise KeyError(err_str)

    def add_child_parameter(self) -> Parameter:
        # Generate a name. This needs to be UNIQUE because children need
        # to be tracked as individuals and not as indices in the list.
        # Ex: a Connection is made to Parameter List[1]. List[0] gets deleted.
        # The OLD List[1] is now List[0], but we need to maintain the Connection
        # to the original entry.
        #
        # (No, we're not renaming it List[0] everywhere for you)
        name = f"{self.name}_ParameterListUniqueParamID_{uuid.uuid4().hex!s}"

        param = Parameter(
            name=name,
            tooltip=self.tooltip,
            type=self._type,
            input_types=self._input_types,
            output_type=self._output_type,
            default_value=self.default_value,
            tooltip_as_input=self.tooltip_as_input,
            tooltip_as_output=self.tooltip_as_output,
            tooltip_as_property=self.tooltip_as_property,
            allowed_modes=self.allowed_modes,
            ui_options=self.ui_options,
            traits=self._original_traits,
            converters=self.converters,
            validators=self.validators,
            settable=self.settable,
            user_defined=True,
            parent_container_name=self.name,
        )

        # Add at the end.
        self.add_child(param)

        return param


class ParameterKeyValuePair(Parameter):
    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | list[dict],
        # Main parameter options
        type: str | None = None,  # noqa: A002
        default_value: Any = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        # Key and Value specific options
        key_default_value: Any = None,
        key_tooltip: str | list[dict] | None = None,
        key_ui_options: dict | None = None,
        key_traits: set[Trait.__class__ | Trait] | None = None,
        key_converters: list[Callable[[Any], Any]] | None = None,
        key_validators: list[Callable[[Parameter, Any], None]] | None = None,
        value_default_value: Any = None,
        value_tooltip: str | list[dict] | None = None,
        value_ui_options: dict | None = None,
        value_traits: set[Trait.__class__ | Trait] | None = None,
        value_converters: list[Callable[[Any], Any]] | None = None,
        value_validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
    ):
        # Remember: we're a Parameter, too, just like everybody else.
        super().__init__(
            name=name,
            tooltip=tooltip,
            type=type,
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
            traits=traits,
            converters=converters,
            validators=validators,
            settable=settable,
            user_defined=user_defined,
            element_id=element_id,
            element_type=element_type,
        )

        kvp_type = ParameterType.parse_kv_type_pair(self.type)
        if kvp_type is None:
            err_str = f"PropertyKeyValuePair type '{type}' was not a valid Key-Value Type Pair. Format should be: ['<key type>', '<value type>']"
            raise ValueError(err_str)

        # Create key parameter as a child
        key_param = Parameter(
            name=f"{name}.key",
            tooltip=key_tooltip or "Key for the key-value pair",
            type=kvp_type.key_type,
            default_value=key_default_value,
            ui_options=key_ui_options,
            traits=key_traits,
            converters=key_converters,
            validators=key_validators,
        )
        self.add_child(key_param)

        # Create value parameter as a child
        value_param = Parameter(
            name=f"{name}.value",
            tooltip=value_tooltip or "Value for the key-value pair",
            type=kvp_type.value_type,
            default_value=value_default_value,
            ui_options=value_ui_options,
            traits=value_traits,
            converters=value_converters,
            validators=value_validators,
        )
        self.add_child(value_param)

    def _custom_setter_for_property_type(self, value: Any) -> None:
        # Set it as normal.
        super()._custom_setter_for_property_type(value)

        # Ensure this is a valid Key-Value Pair
        base_type = super()._custom_getter_for_property_type()
        kvp_type = ParameterType.parse_kv_type_pair(base_type)
        if kvp_type is None:
            err_str = f"PropertyKeyValuePair type '{base_type}' was not a valid Key-Value Type Pair. Format should be: ['<key type>', '<value type>']"
            raise ValueError(err_str)

        # Update the key and value parameter types
        key_param = self.find_element_by_id(f"{self.name}.key")
        value_param = self.find_element_by_id(f"{self.name}.value")
        if isinstance(key_param, Parameter) and isinstance(value_param, Parameter):
            key_param.type = kvp_type.key_type
            value_param.type = kvp_type.value_type

    def get_key(self) -> Any:
        """Get the current value of the key parameter."""
        key_param = self.find_element_by_id(f"{self.name}.key")
        if isinstance(key_param, Parameter):
            return key_param.default_value
        return None

    def set_key(self, value: Any) -> None:
        """Set the value of the key parameter."""
        key_param = self.find_element_by_id(f"{self.name}.key")
        if isinstance(key_param, Parameter):
            key_param.default_value = value

    def get_value(self) -> Any:
        """Get the current value of the value parameter."""
        value_param = self.find_element_by_id(f"{self.name}.value")
        if isinstance(value_param, Parameter):
            return value_param.default_value
        return None

    def set_value(self, value: Any) -> None:
        """Set the value of the value parameter."""
        value_param = self.find_element_by_id(f"{self.name}.value")
        if isinstance(value_param, Parameter):
            value_param.default_value = value


class ParameterDictionary(ParameterContainer):
    _kvp_type: ParameterType.KeyValueTypePair
    _original_traits: set[Trait.__class__ | Trait]

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        tooltip: str | list[dict],
        type: str | None = None,  # noqa: A002
        default_value: Any = None,
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        ui_options: dict | None = None,
        traits: set[Trait.__class__ | Trait] | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
    ):
        # Remember: we're a Parameter, too, just like everybody else.
        super().__init__(
            name=name,
            tooltip=tooltip,
            type=type,
            default_value=default_value,
            tooltip_as_input=tooltip_as_input,
            tooltip_as_property=tooltip_as_property,
            tooltip_as_output=tooltip_as_output,
            allowed_modes=allowed_modes,
            ui_options=ui_options,
            traits=traits,
            converters=converters,
            validators=validators,
            settable=settable,
            user_defined=user_defined,
            element_id=element_id,
            element_type=element_type,
        )

        if traits:
            self._original_traits = traits
        else:
            self._original_traits = set()

    def _custom_getter_for_property_type(self) -> str:
        base_type = super()._custom_getter_for_property_type()
        # NOT A TYPO. Internally, we are representing the Dict as a List to preserve the order.
        result = f"list[{base_type}]"
        return result

    def _custom_setter_for_property_type(self, value: Any) -> None:
        # Set it as normal.
        super()._custom_setter_for_property_type(value)

        # We set the type value, now get it back.
        base_type = super()._custom_getter_for_property_type()

        # Ensure this is a valid Key-Value Pair
        base_type = super()._custom_getter_for_property_type()
        kvp_type = ParameterType.parse_kv_type_pair(base_type)
        if kvp_type is None:
            err_str = f"PropertyDictionary type '{base_type}' was not a valid Key-Value Type Pair. Format should be: ['<key type>', '<value type>']"
            raise ValueError(err_str)
        self._kvp_type = kvp_type

    def _custom_getter_for_property_input_types(self) -> list[str]:
        # For every valid input type, also accept a list variant of that for the CONTAINER Parameter only.
        # Children still use the input types given to them.
        base_input_types = super()._custom_getter_for_property_input_types()
        result = []
        for base_input_type in base_input_types:
            container_variant = f"dict[{base_input_type}]"
            result.append(container_variant)

        return result

    def _custom_getter_for_property_output_type(self) -> str:
        base_type = super()._custom_getter_for_property_output_type()
        result = f"dict[{base_type}]"
        return result

    def __len__(self) -> int:
        # Returns the number of child Parameters. Just do the top level.
        param_children = self.find_elements_by_type(element_type=ParameterKeyValuePair, find_recursively=False)
        return len(param_children)

    def __getitem__(self, key: int) -> ParameterKeyValuePair:
        count = 0
        for child in self._children:
            if isinstance(child, ParameterKeyValuePair):
                if count == key:
                    # Found it.
                    return child
                count += 1

        # If we fell out of the for loop, we had a bad value.
        err_str = f"Attempted to get a Parameter Dictionary index {key}, which was out of range."
        raise KeyError(err_str)

    def add_key_value_pair(self) -> ParameterKeyValuePair:
        # Generate a name. This needs to be UNIQUE because children need
        # to be tracked as individuals and not as indices/keys in the dict.
        name = f"{self.name}_ParameterDictUniqueParamID_{uuid.uuid4().hex!s}"

        param = ParameterKeyValuePair(
            name=name,
            tooltip=self.tooltip,
            type=self._type,
            default_value=self.default_value,
            tooltip_as_input=self.tooltip_as_input,
            tooltip_as_output=self.tooltip_as_output,
            tooltip_as_property=self.tooltip_as_property,
            allowed_modes=self.allowed_modes,
            ui_options=self.ui_options,
            traits=self._original_traits,
            converters=self.converters,
            validators=self.validators,
            settable=self.settable,
            user_defined=self.user_defined,
        )

        # Add at the end.
        self.add_child(param)

        return param


# TODO: https://github.com/griptape-ai/griptape-nodes/issues/858


@dataclass(eq=False)
class Trait(ABC, BaseNodeElement):
    def __hash__(self) -> int:
        # Use a unique, immutable attribute for hashing
        return hash(self.element_id)

    def __eq__(self, other: object) -> bool:
        if not (isinstance(other, Trait)):
            return False
        return self.to_dict() == other.to_dict()

    def to_dict(self) -> dict[str, Any]:
        updated = super().to_dict()
        updated["trait_ui_options"] = self.ui_options_for_trait()
        updated["trait_name"] = self.__class__.__name__
        updated["trait_display_options"] = self.display_options_for_trait()
        return updated

    @classmethod
    @abstractmethod
    def get_trait_keys(cls) -> list[str]:
        """This will return keys that trigger this trait."""

    def ui_options_for_trait(self) -> dict:
        """Returns a list of UI options for the parameter as a list of strings or dictionaries."""
        return {}

    def display_options_for_trait(self) -> dict:
        """Returns a list of display options for the parameter as a dictionary."""
        return {}

    def converters_for_trait(self) -> list[Callable[[Any], Any]]:
        """Returns a list of methods to be applied as a convertor."""
        return []

    def validators_for_trait(self) -> list[Callable[[Parameter, Any]]]:
        """Returns a list of methods to be applied as a validator."""
        return []
