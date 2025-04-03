from __future__ import annotations

import uuid
from abc import ABC
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeVar

#from griptape_nodes.exe_types.trait_types import Trait

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T", bound="Parameter")


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


class ParameterType:
    _builtin_aliases = {
        "str": ParameterTypeBuiltin.STR,
        "string": ParameterTypeBuiltin.STR,
        "bool": ParameterTypeBuiltin.BOOL,
        "boolean": ParameterTypeBuiltin.BOOL,
        "int": ParameterTypeBuiltin.INT,
        "float": ParameterTypeBuiltin.FLOAT,
        "any": ParameterTypeBuiltin.ANY,
        "none": ParameterTypeBuiltin.NONE,
        "parametercontroltype": ParameterTypeBuiltin.CONTROL_TYPE,
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


# Keys and values for the UI_Options schema.
@dataclass
class ParameterUIOptions:
    @dataclass
    class Option(ABC):  # noqa: B024
        def __eq__(self, other) -> bool:
            if not isinstance(other, type(self)):
                return False
            self_dict = self.__dict__
            other_dict = self.__dict__
            return self_dict == other_dict

    @dataclass
    class TypeOption(Option, ABC):
        pass

    @dataclass
    class ContainerOption(Option, ABC):
        pass

    @dataclass
    class StringType(TypeOption):
        multiline: bool | None = None
        markdown: bool | None = None
        placeholder_text: str | None = None

    @dataclass
    class BooleanType(TypeOption):
        on_label: str | None = None
        off_label: str | None = None

    @dataclass
    class SliderWidget:
        min_val: Any
        max_val: Any

    @dataclass
    class NumberType(TypeOption):
        slider: ParameterUIOptions.SliderWidget | None = None
        step: Any | None = None

    @dataclass
    class SimpleDropdown(Option):
        enum_choices: list[str] | None = None
        placeholder_text: str | None = None

    @dataclass
    class FancyDropdown(Option):
        enum_dict: dict[Any, Any] | None = None

    @dataclass
    class ImageType(TypeOption):
        clickable_file_browser: bool | None = None
        expander: bool | None = None

    @dataclass
    class VideoType(TypeOption):
        clickable_file_browser: bool | None = None
        play_button: bool | None = None
        playback_range: bool | None = None
        expander: bool | None = None

    @dataclass
    class AudioType(TypeOption):
        clickable_file_browser: bool | None = None

    @dataclass
    class PropertyArrayType(ContainerOption, TypeOption):
        property_type_option: ParameterUIOptions.TypeOption | None = None
        stacked: bool | None = None
        color: bool | None = None

    @dataclass
    class ListContainer(ContainerOption):
        element_type_option: ParameterUIOptions.TypeOption | None = None
        stacked: bool | None = None

    string_type_options: StringType | None = None
    boolean_type_options: BooleanType | None = None
    number_type_options: NumberType | None = None
    simple_dropdown_options: SimpleDropdown | None = None
    fancy_dropdown_options: FancyDropdown | None = None
    image_type_options: ImageType | None = None
    video_type_options: VideoType | None = None
    audio_type_options: AudioType | None = None
    property_array_type_options: PropertyArrayType | None = None
    list_container_options: ListContainer | None = None
    display: bool = True

    def __eq__(self, other) -> bool:
        if not isinstance(other, ParameterUIOptions):
            return False
        self_dict = self.__dict__
        other_dict = other.__dict__
        return self_dict == other_dict


@dataclass(kw_only=True)
class BaseNodeElement:
    element_id: str = field(default_factory=lambda: str(uuid.uuid4().hex))
    element_type: str = field(default_factory=lambda: BaseNodeElement.__name__)

    _children: list[BaseNodeElement] = field(default_factory=list)
    _stack: ClassVar[list[BaseNodeElement]] = []

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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
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
        self._children.append(child)

    def remove_child(self, child: BaseNodeElement | str) -> None:
        ui_elements: list[BaseNodeElement] = [self]
        for ui_element in ui_elements:
            if child in ui_element._children:
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

    def find_elements_by_type(self, element_type: type[T]) -> list[T]:
        elements: list[T] = []
        for child in self._children:
            if isinstance(child, element_type):
                elements.append(child)
            elements.extend(child.find_elements_by_type(element_type))
        return elements

    @classmethod
    def get_current(cls) -> BaseNodeElement | None:
        """Return the element on top of the stack, or None if no active element."""
        return cls._stack[-1] if cls._stack else None


@dataclass(kw_only=True)
class ParameterGroup(BaseNodeElement):
    """UI element for a group of parameters."""

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
        return {
            "element_id": self.element_id,
            "element_type": self.__class__.__name__,
            "group_name": self.group_name,
            "children": [child.to_dict() for child in self._children],
        }


class Parameter(BaseNodeElement):
    # This is the list of types that the Parameter can accept, either externally or when internally treated as a property.
    # Today, we can accept multiple types for input, but only a single output type.
    name: str  # must be unique from other parameters in Node
    tooltip: str | list[dict]  # Default tooltip, can be string or list of dicts
    default_value: Any = None
    _input_types: list[str] | None
    _output_type: str | None
    _type: str | None
    user_set_type: bool
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
    ui_options: ParameterUIOptions | None = None
    converters: list[Callable[[Any], Any]]
    validators: list[Callable[[Parameter, Any], None]]
    # Traits should be set? As values here, correct?
    # Traits will define UI options and convertors
    traits: list[Trait] | None = None # we need to store the trait objects as lists
    next: Parameter | None = None
    prev: Parameter | None = None

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
        ui_options: ParameterUIOptions | None = None,
        converters: list[Callable[[Any], Any]] | None = None,
        validators: list[Callable[[Parameter, Any], None]] | None = None,
        *,
        settable: bool = True,
        user_defined: bool = False,
        element_id: str | None = None,
        element_type: str | None = None,
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
        self.ui_options = ui_options
        if allowed_modes is None:
            self.allowed_modes = {ParameterMode.INPUT, ParameterMode.OUTPUT, ParameterMode.PROPERTY}
        else:
            self.allowed_modes = allowed_modes

        if converters is None:
            self.converters = []
        else:
            self.converters = converters

        if validators is None:
            self.validators = []
        else:
            self.validators = validators
        if type:
            self.user_set_type = True
        else:
            self.user_set_type = False
        self.type = type
        self.input_types = input_types
        self.output_type = output_type

    @property
    def type(self) -> str:
        if self._type:
            return self._type
        if self._input_types:
            return self._input_types[0]
        if self._output_type:
            return self._output_type
        return ParameterTypeBuiltin.STR.value

    @type.setter
    def type(self, value: str | None) -> None:
        if value is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(value)
            if builtin is not None:
                self._type = builtin.value
            else:
                self._type = value
            return
        self._type = None
        self.user_set_type = False

    @property
    def input_types(self) -> list[str]:
        if self._input_types:
            return self._input_types
        if self._type:
            return [self._type]
        if self._output_type:
            return [self._output_type]
        return [ParameterTypeBuiltin.STR.value]

    @input_types.setter
    def input_types(self, value: list[str] | None) -> None:
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
        if self._output_type:
            # If an output type was specified, use that.
            return self._output_type
        if self._type and self.user_set_type:
            # Otherwise, see if we have a list of input_types. If so, use the first one.
            return self._type
        if self._input_types:
            return self._input_types[0]
        # Otherwise, return a string.
        return ParameterTypeBuiltin.STR.value

    @output_type.setter
    def output_type(self, value: str | None) -> None:
        if value is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(value)
            if builtin is not None:
                self._output_type = builtin.value
                return
        self._output_type = value

    def is_incoming_type_allowed(self, incoming_type: str | None) -> bool:
        if incoming_type is None:
            return False

        ret_val = False

        if self._input_types:
            for test_type in self._input_types:
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

    # intentionally not overwriting __eq__ because I want to return a dict not true or false
    def equals(self, other: Parameter) -> dict:
        self_dict = self.__dict__
        other_dict = other.__dict__
        self_dict.pop("next", None)
        self_dict.pop("prev", None)
        other_dict.pop("next", None)
        other_dict.pop("prev", None)
        if self_dict == other_dict:
            return {}
        differences = {}
        for key, self_value in self_dict.items():
            other_value = other_dict.get(key)
            if isinstance(other_value, ParameterUIOptions) and other_value != self_value:
                # check if these two objects are equal
                differences["key"] = other_value
            if isinstance(self_value, (list, set)) and isinstance(other_value, (list, set)):
                if set(self_value) != set(other_value):
                    differences[key] = other_value
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
        ui_options: ParameterUIOptions | None = None,
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
            ui_options=ui_options,
            converters=converters,
            validators=validators,
            user_defined=user_defined,
        )


class ControlParameterInput(ControlParameter):
    def __init__(  # noqa: PLR0913
        self,
        tooltip: str | list[dict] = "Connection from previous node in the execution chain",
        name: str = "exec_in",
        tooltip_as_input: str | list[dict] | None = None,
        tooltip_as_property: str | list[dict] | None = None,
        tooltip_as_output: str | list[dict] | None = None,
        ui_options: ParameterUIOptions | None = None,
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
            ui_options=ui_options,
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
        ui_options: ParameterUIOptions | None = None,
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
            ui_options=ui_options,
            converters=converters,
            validators=validators,
            user_defined=user_defined,
        )
