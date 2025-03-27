from __future__ import annotations

import uuid
from abc import ABC
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

from griptape_nodes.exe_types.type_validator import TypeValidator

T = TypeVar("T", bound="Parameter")


# Types of Modes provided for Parameters
class ParameterMode(Enum):
    OUTPUT = auto()
    INPUT = auto()
    PROPERTY = auto()


# I'm a special way to say my Type is for Control flow.
class ParameterControlType:
    pass


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
              "name": "container-1",
              "children": [
                { "name": "A", "children": [] },
                ...
              ]
            }
        """
        return {
            "element_id": self.element_id,
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


@dataclass
class Parameter(BaseNodeElement):
    name: str  # must be unique from other parameters in Node
    allowed_types: list[str]
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

    def is_type_allowed(self, type_as_str: str) -> bool:
        # Original code continues here...
        # Can't just do a string compare as we'll whiff on things like "list" not matching "List"
        test_type = TypeValidator.convert_to_type(type_as_str)
        if test_type is Any:
            return True
        for allowed_type_str in self.allowed_types:
            allowed_type = TypeValidator.convert_to_type(allowed_type_str)
            if allowed_type is Any:
                return True
            if allowed_type == test_type:
                return True
        return False

    def is_value_allowed(self, value: Any) -> bool:
        for allowed_type_str in self.allowed_types:
            if TypeValidator.is_instance(value, allowed_type_str):
                return True
            try:
                print(f"Value not allowed {self.name}: {value=}, {allowed_type_str=}")
            except Exception:
                print(f"Value not allowed {self.name}: [error], {allowed_type_str=}")
        return False

    def set_default_value(self, value: Any) -> None:
        if self.is_value_allowed(value):
            self.default_value = value
        else:
            errormsg = "Type does not match allowed value types"
            raise TypeError(errormsg)

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
    allowed_types: list[str] = field(default_factory=lambda: [ParameterControlType.__name__])
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
