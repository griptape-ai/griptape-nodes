from __future__ import annotations

from abc import ABC
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


# Types of Modes provided for Parameters
class ParameterMode(Enum):
    OUTPUT = auto()
    INPUT = auto()
    PROPERTY = auto()


# I'm a special way to say my Type is for Control flow.
class ParameterControlType:
    pass


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


@dataclass
class Parameter:
    name: str  # must be unique from other parameters in Node

    # This is the list of types that the Parameter can accept, either externally or when internally treated as a property.
    # Today, we can accept multiple types for input, but only a single output type.
    tooltip: str  # Default tooltip
    default_value: Any = None

    tooltip_as_input: str | None = None
    tooltip_as_property: str | None = None
    tooltip_as_output: str | None = None
    settable: bool = True
    user_defined: bool = False
    allowed_modes: set = field(
        default_factory=lambda: {
            ParameterMode.OUTPUT,
            ParameterMode.INPUT,
            ParameterMode.PROPERTY,
        }
    )
    options: list[Any] | None = None
    ui_options: ParameterUIOptions | None = None
    next: Parameter | None = None
    prev: Parameter | None = None
    converters: list[Callable[[Any], Any]] = field(default_factory=list)
    validators: list[Callable[[Parameter, Any], None]] = field(default_factory=list)

    # The types this Parameter accepts for inputs and for output.
    # The rules for this are a rather arcane combination; see the functions below for how these are interpreted.
    # We use @property getters/setters to access these with some arcanum.
    _type: str | None = None
    _types: list[str] | None = None
    _output_type: str | None = None

    @property
    def type(self) -> str | None:
        return self._type

    @type.setter
    def type(self, new_type) -> None:
        if new_type is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(new_type)
            if builtin is not None:
                self._type = builtin.value
                return
        self._type = new_type

    @property
    def types(self) -> list[str] | None:
        return self._types

    @types.setter
    def types(self, new_types) -> None:
        if new_types is None:
            self._types = None
        else:
            self._types = []
            for new_type in new_types:
                # See if it's an alias to a builtin first.
                builtin = ParameterType.attempt_get_builtin(new_type)
                if builtin is not None:
                    self._types.append(builtin.value)
                else:
                    self._types.append(new_type)

    @property
    def output_type(self) -> str | None:
        return self._output_type

    @output_type.setter
    def output_type(self, new_type) -> None:
        if new_type is not None:
            # See if it's an alias to a builtin first.
            builtin = ParameterType.attempt_get_builtin(new_type)
            if builtin is not None:
                self._output_type = builtin.value
                return
        self._output_type = new_type

    # Will this type be allowed as an input?
    def is_incoming_type_allowed(self, incoming_type: str | None) -> bool:
        if incoming_type is None:
            return False

        ret_val = False

        if self._type is not None:
            if self._types:
                # Case 1: Both type and types are specified. Check type first, then types.
                if ParameterType.are_types_compatible(source_type=incoming_type, target_type=self._type):
                    ret_val = True
                else:
                    for test_type in self._types:
                        if ParameterType.are_types_compatible(source_type=incoming_type, target_type=test_type):
                            ret_val = True
                            break
            else:
                # Case 2: type is set, but not types. Just check type.
                ret_val = ParameterType.are_types_compatible(source_type=incoming_type, target_type=self.type)
        elif self.types:
            # Case 3: types is specified, but not type. Just check types.
            for test_type in self.types:
                if ParameterType.are_types_compatible(source_type=incoming_type, target_type=test_type):
                    ret_val = True
                    break
        else:
            # Case 4: neither is set. Treat as a string.
            ret_val = ParameterType.are_types_compatible(
                source_type=incoming_type, target_type=ParameterTypeBuiltin.STR.value
            )

        return ret_val

    # What's the output type?
    def get_allowed_output_type(self) -> str | None:
        if ParameterMode.OUTPUT not in self.allowed_modes:
            return None

        if self.output_type:
            return self.output_type
        if self.types:
            return self.types[0]
        if self.type:
            return self.type
        # Otherwise, return a string.
        return ParameterTypeBuiltin.STR.value

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
@dataclass(kw_only=True)
class ControlParameter(Parameter, ABC):
    input_types: list[str] = field(default_factory=lambda: [ParameterControlType.__name__])
    _output_type: str | None = ParameterControlType.__name__
    default_value: Any = None
    settable: bool = False


@dataclass(kw_only=True)
class ControlParameter_Input(ControlParameter):
    name: str = "exec_in"
    tooltip: str = "Connection from previous node in the execution chain"
    allowed_modes: set = field(
        default_factory=lambda: {
            ParameterMode.INPUT,
        }
    )


@dataclass
class ControlParameter_Output(ControlParameter):
    name: str = "exec_out"
    tooltip: str = "Connection to the next node in the execution chain"
    allowed_modes: set = field(
        default_factory=lambda: {
            ParameterMode.OUTPUT,
        }
    )
